from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.partner_auth.dto import TalkoContract
from src.components.partner_auth.services import TalkoPartnerApiKeyService
from src.utils.token_utils import TalkoApiKeyGenerator


@pytest.mark.asyncio
class TestPartnerApiKeyService:
    @pytest.fixture
    def service(self):
        datetime_util = MagicMock()
        datetime_util.get_current_time.return_value = 1735689600
        return TalkoPartnerApiKeyService(
            repository=AsyncMock(),
            validator=AsyncMock(),
            rate_limiter=AsyncMock(),
            logger=MagicMock(),
            datetime_util=datetime_util,
        )

    async def test_create_api_key_returns_raw_key_once(self, service):
        service.repository.insert_api_key.return_value = str(ObjectId())

        result = await service.create_api_key(
            TalkoContract.ApiKeyCreate(partner_id=1, label="Acme"), created_by_user_id=9
        )

        assert result.key.startswith(TalkoApiKeyGenerator.PREFIX)
        assert result.key_prefix in result.key
        assert result.partner_id == 1
        assert result.label == "Acme"

        # The response model has no way to re-derive the raw key from what
        # gets persisted — only a hash goes to the repository.
        inserted_doc = service.repository.insert_api_key.call_args[0][0]
        assert "key" not in inserted_doc
        assert inserted_doc["key_hash"] == TalkoApiKeyGenerator.hash_key(result.key)

    async def test_list_api_keys_never_exposes_hash(self, service):
        service.repository.find_all_by_partner_id.return_value = [
            {
                "_id": ObjectId(),
                "partner_id": 1,
                "key_prefix": "tkp_live_ab12cd34",
                "key_hash": "should-not-appear",
                "label": "Acme",
                "is_active": True,
                "created_at": 1735689600,
                "last_used_at": None,
                "revoked_at": None,
            }
        ]

        results = await service.list_api_keys(partner_id=1)

        assert len(results) == 1
        assert not hasattr(results[0], "key_hash")
        assert not hasattr(results[0], "key")

    async def test_revoke_api_key_success(self, service):
        key_id = ObjectId()
        service.validator.validate_key_exists.return_value = {"_id": key_id}
        service.repository.revoke.return_value = {
            "is_active": False,
            "revoked_at": 1735689600,
        }

        result = await service.revoke_api_key(str(key_id))
        assert result.is_active is False

    async def test_validate_and_get_partner_valid_active_key(self, service):
        raw_key, _prefix, key_hash = TalkoApiKeyGenerator.generate()
        key_id = ObjectId()
        service.repository.find_by_key_hash.return_value = {
            "_id": key_id,
            "partner_id": 42,
            "is_active": True,
        }

        result = await service.validate_and_get_partner(raw_key)

        service.repository.find_by_key_hash.assert_awaited_once_with(key_hash)
        assert result == {"partner_id": 42, "api_key_id": str(key_id)}
        service.repository.touch_last_used.assert_awaited_once()

    async def test_validate_and_get_partner_unknown_key(self, service):
        service.repository.find_by_key_hash.return_value = None
        result = await service.validate_and_get_partner("tkp_live_nonexistent")
        assert result is None

    async def test_validate_and_get_partner_inactive_key(self, service):
        service.repository.find_by_key_hash.return_value = {
            "_id": ObjectId(),
            "partner_id": 42,
            "is_active": False,
        }
        result = await service.validate_and_get_partner("tkp_live_revoked")
        assert result is None

    async def test_check_rate_limit_delegates(self, service):
        service.rate_limiter.check.return_value = True
        assert await service.check_rate_limit(partner_id=1) is True
        service.rate_limiter.check.assert_awaited_once_with(1)
