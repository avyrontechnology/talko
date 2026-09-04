from typing import List, Optional

from bson import ObjectId

from src.components.partner_auth.dto import TalkoContract
from src.components.partner_auth.models import TalkoPartnerApiKeyModel
from src.components.partner_auth.rate_limiter import TalkoPartnerApiKeyRateLimiter
from src.components.partner_auth.repository import TalkoPartnerApiKeyRepository
from src.components.partner_auth.validation import TalkoPartnerApiKeyValidator
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil
from src.utils.token_utils import TalkoApiKeyGenerator


class TalkoPartnerApiKeyService:
    def __init__(
        self,
        repository: TalkoPartnerApiKeyRepository,
        validator: TalkoPartnerApiKeyValidator,
        rate_limiter: TalkoPartnerApiKeyRateLimiter,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
    ):
        self.repository = repository
        self.validator = validator
        self.rate_limiter = rate_limiter
        self.logger = logger
        self.datetime_util = datetime_util

    async def create_api_key(
        self, data: TalkoContract.ApiKeyCreate, created_by_user_id: Optional[int]
    ) -> TalkoContract.ApiKeyCreateResponse:
        self.logger.info(
            "Creating partner api key for partner_id: {}".format(data.partner_id)
        )
        raw_key, key_prefix, key_hash = TalkoApiKeyGenerator.generate()
        now = self.datetime_util.get_current_time()
        model = TalkoPartnerApiKeyModel(
            partner_id=data.partner_id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            label=data.label,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        doc = model.model_dump(exclude_unset=False)
        api_key_id = await self.repository.insert_api_key(doc)
        self.logger.info(
            "Created partner api key {} for partner_id: {}".format(
                api_key_id, data.partner_id
            )
        )
        return TalkoContract.ApiKeyCreateResponse(
            id=api_key_id,
            key=raw_key,
            key_prefix=key_prefix,
            partner_id=data.partner_id,
            label=data.label,
            created_at=now,
        )

    async def list_api_keys(
        self, partner_id: int
    ) -> List[TalkoContract.ApiKeyListItem]:
        self.logger.info(
            "Listing partner api keys for partner_id: {}".format(partner_id)
        )
        keys = await self.repository.find_all_by_partner_id(partner_id)
        return [
            TalkoContract.ApiKeyListItem(
                id=str(key["_id"]),
                key_prefix=key["key_prefix"],
                partner_id=key["partner_id"],
                label=key.get("label"),
                is_active=key["is_active"],
                created_at=key["created_at"],
                last_used_at=key.get("last_used_at"),
                revoked_at=key.get("revoked_at"),
            )
            for key in keys
        ]

    async def revoke_api_key(self, id: str) -> TalkoContract.ApiKeyRevokeResponse:
        self.logger.info("Revoking partner api key {}".format(id))
        await self.validator.validate_key_exists(ObjectId(id))
        revoked_at = self.datetime_util.get_current_time()
        result = await self.repository.revoke(ObjectId(id), revoked_at)
        return TalkoContract.ApiKeyRevokeResponse(
            id=id, is_active=result["is_active"], revoked_at=result["revoked_at"]
        )

    async def validate_and_get_partner(self, raw_key: str) -> Optional[dict]:
        key_hash = TalkoApiKeyGenerator.hash_key(raw_key)
        api_key = await self.repository.find_by_key_hash(key_hash)
        if not api_key or not api_key.get("is_active"):
            return None
        await self.repository.touch_last_used(
            api_key["_id"], self.datetime_util.get_current_time()
        )
        return {
            "partner_id": api_key["partner_id"],
            "api_key_id": str(api_key["_id"]),
        }

    async def check_rate_limit(self, partner_id: int) -> bool:
        return await self.rate_limiter.check(partner_id)
