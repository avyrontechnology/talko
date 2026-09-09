"""Superadmin (cross-partner) access for Talko.

Talko scopes every partner-facing endpoint to the ``partner_id`` in auth
state. A superadmin is a console user at the top of the existing role
hierarchy (``TalkoUserRoleHierarchy.ADMIN``) signing in with a JWT — API
keys are always partner-bound and can never be superadmin.

A superadmin acts cross-partner by sending the target partner id in the
``X-Partner-Scope`` header. Endpoints opt in explicitly via
:func:`resolve_effective_partner_id`; anything else keeps the caller's own
scope. Denials fail closed (403); role lookups fail closed (False).
"""

from typing import Optional

from fastapi import Request

from src.components.common.constants import TalkoCurrentUserMap
from src.utils.enums import TalkoUserRoleHierarchy

#: Request header carrying the target partner for superadmin calls.
SUPERADMIN_SCOPE_HEADER = "X-Partner-Scope"


class TalkoSuperadminDenied(PermissionError):
    """Raised when a non-superadmin requests another partner's scope."""


async def is_superadmin(request: Request, grpc_client, logger) -> bool:
    """True when the caller is a JWT user with ADMIN hierarchy level.

    API-key callers are partner-scoped by construction and never qualify.
    Any lookup failure denies (fail closed).
    """
    user = getattr(request.state, "user", None) or {}
    if user.get("is_api_key_auth"):
        return False
    user_id = user.get(TalkoCurrentUserMap.USER_ID)
    if not user_id:
        return False
    try:
        roles = await grpc_client.get_user_roles(user_id)
    except Exception as exc:
        logger.warning(
            "Superadmin check failed closed for user_id={}: {}".format(user_id, exc)
        )
        return False
    return (roles or {}).get("hierarchy") == TalkoUserRoleHierarchy.ADMIN.value


async def resolve_effective_partner_id(
    request: Request,
    grpc_client,
    logger,
    scope_override: Optional[int] = None,
) -> int:
    """Partner id the request acts on: own scope, or the override for admins.

    Raises:
        TalkoSuperadminDenied: override targets another partner and the
            caller is not a superadmin.
        ValueError: no partner scope on the request at all.
    """
    user = getattr(request.state, "user", None) or {}
    own_partner_id = user.get(TalkoCurrentUserMap.PARTNER_ID)
    if own_partner_id is None:
        raise ValueError("No partner scope on request")
    if scope_override is None or int(scope_override) == int(own_partner_id):
        return int(own_partner_id)
    if await is_superadmin(request, grpc_client, logger):
        logger.info(
            "Superadmin user_id={} acting on partner_id={} (own={})".format(
                user.get(TalkoCurrentUserMap.USER_ID), scope_override, own_partner_id
            )
        )
        return int(scope_override)
    raise TalkoSuperadminDenied(
        "Cross-partner scope requires superadmin (ADMIN) role"
    )
