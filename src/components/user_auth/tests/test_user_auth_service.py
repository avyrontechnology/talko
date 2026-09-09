"""Unit tests for Talko-native signup/login (no DB, no network)."""

from unittest.mock import MagicMock

import pytest

from src.components.user_auth.dto import TalkoContract
from src.components.user_auth.services import (
    TalkoInactiveUserError,
    TalkoInvalidCredentialsError,
    TalkoUserAuthService,
)


class FakeRepo:
    def __init__(self):
        self.docs = {}

    async def count_users(self):
        return len(self.docs)

    async def insert_user(self, doc):
        user_id = "user-{}".format(len(self.docs) + 1)
        self.docs[user_id] = {**doc, "_id": user_id}
        return user_id

    async def find_by_email(self, email):
        lowered = email.strip().lower()
        return next((d for d in self.docs.values() if d["email"] == lowered), None)

    async def find_by_id(self, user_id):
        doc = self.docs.get(user_id)
        return dict(doc) if doc else None

    async def list_users(self, limit=100):
        return list(self.docs.values())[:limit]

    async def update_user(self, user_id, patch):
        if user_id not in self.docs:
            return False
        self.docs[user_id].update(patch)
        return True


def make_service():
    return TalkoUserAuthService(repository=FakeRepo(), logger=MagicMock())


@pytest.fixture(autouse=True)
def test_jwt_secret(monkeypatch):
    monkeypatch.setattr("src.core.environment.TalkoENV.TALKO_JWT_SECRET", "test-secret")
    monkeypatch.setattr("src.core.environment.TalkoENV.TALKO_JWT_TTL_HOURS", 72)


def signup_payload(**overrides):
    data = {
        "name": "Aarav Sharma",
        "email": "aarav@example.com",
        "phone": "+919889560593",
        "password": "Str0ng!Pass",
    }
    data.update(overrides)
    return TalkoContract.Signup(**data)


def provision_payload(**overrides):
    data = {
        "name": "Aarav Sharma",
        "email": "aarav@example.com",
        "phone": "+919889560593",
        "password": "Str0ng!Pass",
        "role": "viewer",
        "partner_id": 2,
    }
    data.update(overrides)
    return TalkoContract.AdminCreateUser(**data)


class TestSignup:
    @pytest.mark.asyncio
    async def test_first_user_becomes_superadmin(self):
        service = make_service()
        user = await service.signup(signup_payload())
        assert user["role"] == "superadmin"
        assert user["partner_id"] is None
        assert user["is_active"] is True
        assert "password_hash" not in user

    @pytest.mark.asyncio
    async def test_later_signup_is_pending_inactive(self):
        service = make_service()
        await service.signup(signup_payload(email="first@example.com"))
        user = await service.signup(signup_payload())
        assert user["role"] == "viewer"
        assert user["partner_id"] is None
        assert user["is_active"] is False

    @pytest.mark.asyncio
    async def test_duplicate_email_rejected(self):
        from src.components.user_auth.services import TalkoUserExistsError

        service = make_service()
        await service.signup(signup_payload())
        with pytest.raises(TalkoUserExistsError):
            await service.signup(signup_payload())


class TestProvisioning:
    @pytest.mark.asyncio
    async def test_provision_scoped_viewer(self):
        service = make_service()
        await service.signup(signup_payload(email="root@example.com"))
        user = await service.create_user(provision_payload())
        assert user["role"] == "viewer"
        assert user["partner_id"] == 2
        assert user["is_active"] is True

    @pytest.mark.asyncio
    async def test_provision_duplicate_rejected(self):
        from src.components.user_auth.services import TalkoUserExistsError

        service = make_service()
        await service.signup(signup_payload(email="root@example.com"))
        await service.create_user(provision_payload())
        with pytest.raises(TalkoUserExistsError):
            await service.create_user(provision_payload())

    @pytest.mark.asyncio
    async def test_provision_non_admin_needs_partner(self):
        service = make_service()
        await service.signup(signup_payload(email="root@example.com"))
        with pytest.raises(ValueError):
            await service.create_user(provision_payload(partner_id=None))


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_mints_token(self):
        service = make_service()
        await service.signup(signup_payload(email="root@example.com"))
        await service.create_user(provision_payload())
        out = await service.login(
            TalkoContract.Login(credential="AARAV@EXAMPLE.COM", password="Str0ng!Pass")
        )
        assert out["token"]
        assert out["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_pending_signup_cannot_login(self):
        service = make_service()
        await service.signup(signup_payload(email="root@example.com"))
        await service.signup(signup_payload())
        with pytest.raises(TalkoInactiveUserError):
            await service.login(
                TalkoContract.Login(credential="aarav@example.com", password="Str0ng!Pass")
            )

    @pytest.mark.asyncio
    async def test_wrong_password_rejected_without_hint(self):
        service = make_service()
        await service.signup(signup_payload(email="root@example.com"))
        await service.create_user(provision_payload())
        with pytest.raises(TalkoInvalidCredentialsError):
            await service.login(
                TalkoContract.Login(credential="aarav@example.com", password="Wr0ng!Pass")
            )
        with pytest.raises(TalkoInvalidCredentialsError):
            await service.login(
                TalkoContract.Login(credential="nobody@example.com", password="Str0ng!Pass")
            )

    @pytest.mark.asyncio
    async def test_inactive_user_cannot_login(self):
        service = make_service()
        await service.signup(signup_payload(email="root@example.com"))
        user = await service.create_user(provision_payload())
        await service.update_user(user["id"], TalkoContract.UpdateUser(is_active=False))
        with pytest.raises(TalkoInactiveUserError):
            await service.login(
                TalkoContract.Login(credential="aarav@example.com", password="Str0ng!Pass")
            )


class TestUserManagement:
    @pytest.mark.asyncio
    async def test_promote_and_scope(self):
        service = make_service()
        await service.signup(signup_payload(email="root@example.com"))
        user = await service.create_user(provision_payload())
        updated = await service.update_user(
            user["id"],
            TalkoContract.UpdateUser(role="superadmin", partner_id=None),
        )
        assert updated["role"] == "superadmin"
        assert updated["partner_id"] is None

    @pytest.mark.asyncio
    async def test_non_admin_must_keep_scope(self):
        service = make_service()
        await service.signup(signup_payload(email="root@example.com"))
        user = await service.create_user(provision_payload())
        with pytest.raises(ValueError):
            await service.update_user(
                user["id"],
                TalkoContract.UpdateUser(role="viewer", partner_id=None),
            )

    @pytest.mark.asyncio
    async def test_activate_pending_signup_with_scope(self):
        service = make_service()
        await service.signup(signup_payload(email="root@example.com"))
        pending = await service.signup(signup_payload())
        assert pending["is_active"] is False
        updated = await service.update_user(
            pending["id"],
            TalkoContract.UpdateUser(role="viewer", partner_id=9, is_active=True),
        )
        assert updated["is_active"] is True
        assert updated["partner_id"] == 9
        out = await service.login(
            TalkoContract.Login(credential="aarav@example.com", password="Str0ng!Pass")
        )
        assert out["token"]

    @pytest.mark.asyncio
    async def test_unknown_user_returns_none(self):
        service = make_service()
        assert (
            await service.update_user("missing", TalkoContract.UpdateUser(role="viewer"))
            is None
        )

    @pytest.mark.asyncio
    async def test_password_roundtrip_and_token_claims(self):
        from src.components.user_auth.passwords import (
            hash_password,
            verify_password,
            verify_talko_token,
        )
        from src.core.environment import TalkoENV

        service = make_service()
        await service.signup(signup_payload(email="root@example.com"))
        await service.create_user(provision_payload())
        stored = service._TalkoUserAuthService__repository.docs["user-2"]
        assert stored["password_hash"] != "Str0ng!Pass"
        assert verify_password("Str0ng!Pass", stored["password_hash"]) is True
        assert verify_password("Wr0ng!Pass", stored["password_hash"]) is False
        out = await service.login(
            TalkoContract.Login(credential="aarav@example.com", password="Str0ng!Pass")
        )
        claims = verify_talko_token(TalkoENV.TALKO_JWT_SECRET, out["token"])
        assert claims is not None
        assert claims["iss"] == "talko"
        assert claims["partner_id"] == 2
        assert claims["is_superadmin"] is False
        assert hash_password("x") != hash_password("x")  # random salt
