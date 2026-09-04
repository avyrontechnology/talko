from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.partner_auth.repository import TalkoPartnerApiKeyRepository
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


@pytest.mark.asyncio
class TestPartnerApiKeyRepository:
    @pytest.fixture
    def mock_db_manager(self):
        return MagicMock(spec=TalkoDocDatabaseSessionManager)

    @pytest.fixture
    def mock_logger(self):
        return MagicMock(spec=TalkoServiceLogger)

    @pytest.fixture
    def repository(self, mock_db_manager, mock_logger):
        return TalkoPartnerApiKeyRepository(mock_db_manager, mock_logger)

    async def test_insert_api_key_success(self, repository, mock_db_manager, mock_logger):
        doc = {"partner_id": 1, "key_hash": "abc"}
        mock_collection = AsyncMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id=ObjectId())
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        result = await repository.insert_api_key(doc)

        mock_collection.insert_one.assert_called_once_with(doc)
        assert isinstance(result, str)

    async def test_find_by_key_hash_hit(self, repository, mock_db_manager):
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {"_id": ObjectId(), "key_hash": "abc"}
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        result = await repository.find_by_key_hash("abc")

        mock_collection.find_one.assert_called_once_with({"key_hash": "abc"})
        assert result["key_hash"] == "abc"

    async def test_find_by_key_hash_miss(self, repository, mock_db_manager):
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        result = await repository.find_by_key_hash("nope")
        assert result is None

    async def test_revoke_not_found_raises(self, repository, mock_db_manager, mock_logger):
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        with pytest.raises(ValueError):
            await repository.revoke(ObjectId(), 123)
        mock_logger.error.assert_called()

    async def test_revoke_success(self, repository, mock_db_manager):
        api_key_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = {
            "_id": api_key_id,
            "is_active": False,
            "revoked_at": 123,
        }
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        result = await repository.revoke(api_key_id, 123)
        assert result["is_active"] is False
        assert result["revoked_at"] == 123

    async def test_touch_last_used_swallows_errors(
        self, repository, mock_db_manager, mock_logger
    ):
        mock_collection = AsyncMock()
        mock_collection.update_one.side_effect = Exception("DB down")
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        # Must not raise — best-effort only.
        await repository.touch_last_used(ObjectId(), 123)
        mock_logger.error.assert_called_once()
