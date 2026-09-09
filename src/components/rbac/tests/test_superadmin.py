"""Unit tests for the superadmin (cross-partner) helper.

No DB/Redis/gRPC: request state and grpc client are faked. Covers the
fail-closed contract — denials must never depend on infrastructure.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.rbac.superadmin import (
    TalkoSuperadminDenied,
    is_superadmin,
    resolve_effective_partner_id,
    resolve_talko_permission,
)


def make_request(user):
    return SimpleNamespace(state=SimpleNamespace(user=user))


def make_grpc(hierarchy=None, explode=False):
    grpc_client = MagicMock()
    if explode:
        grpc_client.get_user_roles = AsyncMock(side_effect=RuntimeError("grpc down"))
    else:
        grpc_client.get_user_roles = AsyncMock(return_value={"hierarchy": hierarchy})
    return grpc_client


def make_logger():
    return MagicMock()


class TestIsSuperadmin:
    @pytest.mark.asyncio
    async def test_admin_hierarchy_is_superadmin(self):
        req = make_request({"user_id": 7, "partner_id": 2})
        assert await is_superadmin(req, make_grpc(hierarchy=1), make_logger()) is True

    @pytest.mark.asyncio
    async def test_non_admin_hierarchy_denied(self):
        req = make_request({"user_id": 7, "partner_id": 2})
        assert await is_superadmin(req, make_grpc(hierarchy=4), make_logger()) is False

    @pytest.mark.asyncio
    async def test_api_key_auth_never_superadmin(self):
        req = make_request({"partner_id": 2, "is_api_key_auth": True})
        grpc_client = make_grpc(hierarchy=1)
        assert await is_superadmin(req, grpc_client, make_logger()) is False
        grpc_client.get_user_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_grpc_failure_fails_closed(self):
        req = make_request({"user_id": 7, "partner_id": 2})
        assert await is_superadmin(req, make_grpc(explode=True), make_logger()) is False

    @pytest.mark.asyncio
    async def test_missing_user_id_denied(self):
        req = make_request({"partner_id": 2})
        assert await is_superadmin(req, make_grpc(hierarchy=1), make_logger()) is False


class TestResolveEffectivePartnerId:
    @pytest.mark.asyncio
    async def test_no_override_returns_own_scope(self):
        req = make_request({"user_id": 7, "partner_id": 2})
        assert await resolve_effective_partner_id(req, make_grpc(), make_logger()) == 2

    @pytest.mark.asyncio
    async def test_same_partner_override_allowed_without_admin(self):
        req = make_request({"user_id": 7, "partner_id": 2})
        grpc_client = make_grpc(hierarchy=8)
        assert await resolve_effective_partner_id(req, grpc_client, make_logger(), 2) == 2
        grpc_client.get_user_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_superadmin_may_act_on_other_partner(self):
        req = make_request({"user_id": 7, "partner_id": 2})
        assert (
            await resolve_effective_partner_id(req, make_grpc(hierarchy=1), make_logger(), 9)
            == 9
        )

    @pytest.mark.asyncio
    async def test_non_admin_cross_partner_denied(self):
        req = make_request({"user_id": 7, "partner_id": 2})
        with pytest.raises(TalkoSuperadminDenied):
            await resolve_effective_partner_id(req, make_grpc(hierarchy=4), make_logger(), 9)

    @pytest.mark.asyncio
    async def test_api_key_cross_partner_denied(self):
        req = make_request({"partner_id": 2, "is_api_key_auth": True})
        with pytest.raises(TalkoSuperadminDenied):
            await resolve_effective_partner_id(req, make_grpc(hierarchy=1), make_logger(), 9)

    @pytest.mark.asyncio
    async def test_talko_jwt_flag_trusted_without_grpc(self):
        req = make_request({"user_id": "abc", "is_superadmin": True, "is_talko_auth": True})
        grpc_client = make_grpc(hierarchy=8)
        assert await is_superadmin(req, grpc_client, make_logger()) is True
        grpc_client.get_user_roles.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_scope_raises(self):
        req = make_request({"user_id": 7})
        with pytest.raises(ValueError):
            await resolve_effective_partner_id(req, make_grpc(), make_logger())

    @pytest.mark.asyncio
    async def test_scopeless_superadmin_with_override(self):
        req = make_request({"user_id": "abc", "is_superadmin": True})
        assert (
            await resolve_effective_partner_id(req, make_grpc(), make_logger(), 9) == 9
        )


class TestResolveTalkoPermission:
    def test_superadmin_allows_everything(self):
        assert (
            resolve_talko_permission(
                role="superadmin",
                route_name="create_vendor",
                http_method="POST",
                is_superadmin=True,
            )
            is True
        )

    def test_maintainer_reads_and_own_scope_writes(self):
        assert (
            resolve_talko_permission(
                role="maintainer",
                route_name="get_all_vendors",
                http_method="GET",
                is_superadmin=False,
            )
            is True
        )
        assert (
            resolve_talko_permission(
                role="maintainer",
                route_name="assign_dids_available_for_assignment",
                http_method="POST",
                is_superadmin=False,
            )
            is True
        )

    def test_maintainer_denied_admin_only_routes(self):
        for route in ("create_partner_config", "create_api_key", "create_vendor"):
            assert (
                resolve_talko_permission(
                    role="maintainer",
                    route_name=route,
                    http_method="POST",
                    is_superadmin=False,
                )
                is False
            )

    def test_viewer_read_only(self):
        assert (
            resolve_talko_permission(
                role="viewer",
                route_name="get_all_vendors",
                http_method="GET",
                is_superadmin=False,
            )
            is True
        )
        assert (
            resolve_talko_permission(
                role="viewer",
                route_name="get_all_vendors",
                http_method="POST",
                is_superadmin=False,
            )
            is False
        )
