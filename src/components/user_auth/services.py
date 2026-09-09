from typing import Optional

from src.components.user_auth.dto import TalkoContract
from src.components.user_auth.models import TalkoUserModel, TalkoUserRole
from src.components.user_auth.passwords import (
    hash_password,
    mint_talko_token,
    verify_password,
)
from src.components.user_auth.repository import TalkoUserRepository
from src.core.environment import TalkoENV
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoUserExistsError(ValueError):
    pass


class TalkoInvalidCredentialsError(ValueError):
    pass


class TalkoInactiveUserError(ValueError):
    pass


def _public_user(doc: dict) -> dict:
    return {
        "id": str(doc.get("_id")),
        "email": doc.get("email"),
        "name": doc.get("name"),
        "phone": doc.get("phone"),
        "role": doc.get("role", TalkoUserRole.VIEWER),
        "partner_id": doc.get("partner_id"),
        "is_active": bool(doc.get("is_active", True)),
    }


class TalkoUserAuthService:
    """Talko-native accounts: signup, login (Talko JWT), admin user mgmt."""

    def __init__(self, repository: TalkoUserRepository, logger: TalkoServiceLogger):
        self.__repository = repository
        self.__logger = logger

    async def signup(self, payload: TalkoContract.Signup) -> dict:
        """Create a user. The first user ever becomes superadmin (bootstrap).

        Later signups default to viewer scoped to their partner_id. Non-first
        signups without a partner_id are rejected — only a cross-partner
        superadmin may exist without one.
        """
        existing = await self.__repository.find_by_email(payload.email)
        if existing:
            raise TalkoUserExistsError("Email already registered")
        total = await self.__repository.count_users()
        if total == 0:
            role = TalkoUserRole.SUPERADMIN
            partner_id = payload.partner_id  # may stay None: cross-partner
        else:
            role = TalkoUserRole.VIEWER
            partner_id = payload.partner_id
            if partner_id is None:
                raise ValueError(
                    "partner_id is required (only the first superadmin may omit it)"
                )
        doc = TalkoUserModel(
            email=payload.email,
            name=payload.name.strip(),
            phone=(payload.phone or "").strip() or None,
            password_hash=hash_password(payload.password),
            role=role,
            partner_id=partner_id,
            is_active=True,
        ).model_dump()
        user_id = await self.__repository.insert_user(doc)
        doc["_id"] = user_id
        self.__logger.info(
            "Talko user signed up email={} role={} partner_id={}".format(
                payload.email, role, partner_id
            )
        )
        return _public_user(doc)

    async def login(self, payload: TalkoContract.Login) -> dict:
        """Verify credentials and mint a Talko JWT. Never reveals which half failed."""
        if not TalkoENV.TALKO_JWT_SECRET:
            raise RuntimeError("TALKO_JWT_SECRET is not provisioned")
        doc = await self.__repository.find_by_email(payload.credential)
        if doc is None or not verify_password(
            payload.password, doc.get("password_hash") or ""
        ):
            raise TalkoInvalidCredentialsError("Invalid email or password")
        if not doc.get("is_active", True):
            raise TalkoInactiveUserError("Account is disabled")
        token = mint_talko_token(
            secret=TalkoENV.TALKO_JWT_SECRET,
            user_id=str(doc.get("_id")),
            email=doc.get("email"),
            role=doc.get("role", TalkoUserRole.VIEWER),
            partner_id=doc.get("partner_id"),
            ttl_hours=TalkoENV.TALKO_JWT_TTL_HOURS,
        )
        self.__logger.info("Talko user logged in email={}".format(doc.get("email")))
        return {"token": token, "token_type": "bearer"}

    async def list_users(self, limit: int = 100) -> list[dict]:
        docs = await self.__repository.list_users(limit=min(max(limit, 1), 500))
        return [_public_user(doc) for doc in docs]

    async def update_user(
        self, target_user_id: str, patch: TalkoContract.UpdateUser
    ) -> Optional[dict]:
        """Superadmin role/partner/active management. Returns updated user or None."""
        doc = await self.__repository.find_by_id(target_user_id)
        if doc is None:
            return None
        fields_set = patch.model_fields_set
        role = patch.role if "role" in fields_set else doc.get("role")
        partner_id = patch.partner_id if "partner_id" in fields_set else doc.get("partner_id")
        if role != TalkoUserRole.SUPERADMIN and partner_id is None:
            raise ValueError("Non-superadmin users require a partner_id")
        update: dict = {}
        if "role" in fields_set:
            update["role"] = role
        if "partner_id" in fields_set:
            update["partner_id"] = partner_id
        if "is_active" in fields_set:
            update["is_active"] = patch.is_active
        if update:
            await self.__repository.update_user(target_user_id, update)
            doc = await self.__repository.find_by_id(target_user_id)
        return _public_user(doc) if doc else None
