from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.partner_config.repository import PartnerConfigRepository
from src.components.vendor_config.services import VendorConfigService


@pytest.fixture
def repo():
    db_manager = MagicMock()
    logger = MagicMock()
    repo = PartnerConfigRepository(db_manager, logger)

    # Shared mock collection
    collection = MagicMock()

    # make collection.find() return a cursor with async to_list
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock()
    collection.find.return_value = mock_cursor

    # patch insert_one etc. as async
    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()
    collection.find_one_and_update = AsyncMock()

    class DummyCM:
        async def __aenter__(self):
            return collection

        async def __aexit__(self, exc_type, exc, tb):
            return False

    repo.db_manager.collection.return_value = DummyCM()
    return repo, collection, logger


@pytest.mark.asyncio
class TestPartnerConfigRepository:
    async def test_insert_partner_config_success(self, repo):
        repo, collection, logger = repo
        collection.insert_one.return_value.inserted_id = "abc123"

        result = await repo.insert_partner_config({"partner_id": 1})

        assert result == "abc123"
        logger.info.assert_called_once()

    async def test_insert_partner_config_failure(self, repo):
        repo, collection, logger = repo
        collection.insert_one.side_effect = Exception("DB error")

        with pytest.raises(Exception, match="DB error"):
            await repo.insert_partner_config({"partner_id": 1})
        logger.error.assert_called_once()

    async def test_find_all_partner_configs_success(self, repo):
        repo, collection, _ = repo
        collection.find.return_value.to_list = AsyncMock(return_value=[{"_id": "1"}])

        result = await repo.find_all_partner_configs()
        assert result == [{"_id": "1"}]

    async def test_find_all_partner_configs_failure(self, repo):
        repo, collection, logger = repo
        collection.find.side_effect = Exception("DB error")

        with pytest.raises(Exception):
            await repo.find_all_partner_configs()
        logger.error.assert_called_once()

    async def test_find_partner_config_by_id_success(self, repo):
        repo, collection, _ = repo
        collection.find_one.return_value = {"_id": "1"}

        result = await repo.find_partner_config_by_id("1")
        assert result == {"_id": "1"}

    async def test_find_partner_config_by_id_failure(self, repo):
        repo, collection, logger = repo
        collection.find_one.side_effect = Exception("DB error")

        with pytest.raises(Exception):
            await repo.find_partner_config_by_id("1")
        logger.error.assert_called_once()

    async def test_find_partner_config_by_partner_id_success(self, repo):
        repo, collection, _ = repo
        collection.find_one.return_value = {"partner_id": 42}

        result = await repo.find_partner_config_by_partner_id(42)
        assert result == {"partner_id": 42}

    async def test_update_partner_config_success(self, repo):
        repo, collection, logger = repo
        collection.find_one_and_update.return_value = {"_id": "1", "partner_id": 42}

        result = await repo.update_partner_config("1", {"field": "value"})
        assert result == {"_id": "1", "partner_id": 42}
        logger.info.assert_called_once()

    async def test_update_partner_config_not_found(self, repo):
        repo, collection, logger = repo
        collection.find_one_and_update.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await repo.update_partner_config("1", {"field": "value"})
        logger.error.assert_called()

    async def test_assign_did_to_partner_success(self, repo):
        repo, collection, logger = repo
        collection.find_one_and_update.return_value = {"_id": "1", "did": "123"}

        result = await repo.assign_did_to_partner("1", "123", 999)
        assert result["did"] == "123"
        logger.info.assert_called_once()

    async def test_assign_did_to_partner_not_found(self, repo):
        repo, collection, logger = repo
        collection.find_one_and_update.return_value = None

        with pytest.raises(ValueError):
            await repo.assign_did_to_partner("1", "123", 999)
        logger.error.assert_called()

    async def test_remove_did_from_partner_success(self, repo):
        repo, collection, logger = repo
        collection.find_one_and_update.return_value = {"_id": "1", "did": None}

        result = await repo.remove_did_from_partner("1", 999)
        assert result["did"] is None
        logger.info.assert_called_once()

    async def test_remove_did_from_partner_not_found(self, repo):
        repo, collection, logger = repo
        collection.find_one_and_update.return_value = None

        with pytest.raises(ValueError):
            await repo.remove_did_from_partner("1", 999)
        logger.error.assert_called()

    async def test_find_partner_config_by_partner_id_raises_and_logs(self):
        # Arrange
        db_manager = MagicMock()
        logger = MagicMock()
        repo = PartnerConfigRepository(db_manager=db_manager, logger=logger)

        # Mock the collection context manager
        collection = AsyncMock()
        collection.find_one.side_effect = Exception("DB error")

        class DummyCM:
            async def __aenter__(self):
                return collection

            async def __aexit__(self, exc_type, exc, tb):
                return False

        db_manager.collection.return_value = DummyCM()

        # Act + Assert
        with pytest.raises(Exception, match="DB error"):
            await repo.find_partner_config_by_partner_id(123)

        logger.error.assert_called_once()
        log_msg = logger.error.call_args[0][0]
        assert "Failed to find partner config by partner_id" in log_msg
        assert "123" in log_msg
