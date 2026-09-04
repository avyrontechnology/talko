from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.partner_webhook.repository import TalkoPartnerWebhookRepository
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


@pytest.mark.asyncio
class TestPartnerWebhookRepository:
    @pytest.fixture
    def mock_db_manager(self):
        return MagicMock(spec=TalkoDocDatabaseSessionManager)

    @pytest.fixture
    def mock_logger(self):
        return MagicMock(spec=TalkoServiceLogger)

    @pytest.fixture
    def repository(self, mock_db_manager, mock_logger):
        return TalkoPartnerWebhookRepository(mock_db_manager, mock_logger)

    async def test_insert_config_success(self, repository, mock_db_manager):
        doc = {"partner_id": 1, "url": "https://example.com"}
        mock_collection = AsyncMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id=ObjectId())
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        result = await repository.insert_config(doc)
        mock_collection.insert_one.assert_called_once_with(doc)
        assert isinstance(result, str)

    async def test_find_config_by_partner_id_hit(self, repository, mock_db_manager):
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {"partner_id": 1}
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        result = await repository.find_config_by_partner_id(1)
        assert result["partner_id"] == 1

    async def test_update_config_not_found_raises(
        self, repository, mock_db_manager, mock_logger
    ):
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        with pytest.raises(ValueError):
            await repository.update_config(1, {"is_active": False})
        mock_logger.error.assert_called()

    async def test_insert_delivery_attempt_success(self, repository, mock_db_manager):
        mock_collection = AsyncMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id=ObjectId())
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        result = await repository.insert_delivery_attempt({"partner_id": 1})
        assert isinstance(result, str)

    async def test_find_delivery_attempts_by_partner_id(self, repository, mock_db_manager):
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.to_list = AsyncMock(return_value=[{"partner_id": 1}])
        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        result = await repository.find_delivery_attempts_by_partner_id(1, limit=10)
        assert result == [{"partner_id": 1}]
