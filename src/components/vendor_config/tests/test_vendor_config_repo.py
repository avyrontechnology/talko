import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.vendor.models import VendorModel
from src.components.vendor_config.models import VendorConfigModel
from src.components.vendor_config.repository import VendorConfigRepository
from src.core.doc_db import DocDatabaseSessionManager
from src.loggers.holler_service_logger import HollerServiceLogger


# Helper class to simulate an async iterator for MongoDB cursor
class AsyncIterator:
    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index < len(self.items):
            item = self.items[self.index]
            self.index += 1
            return item
        raise StopAsyncIteration


@pytest.mark.asyncio
class TestVendorConfigRepository:
    @pytest.fixture
    def mock_db_manager(self):
        return MagicMock(spec=DocDatabaseSessionManager)

    @pytest.fixture
    def mock_logger(self):
        return MagicMock(spec=HollerServiceLogger)

    @pytest.fixture
    def repository(self, mock_db_manager, mock_logger):
        return VendorConfigRepository(mock_db_manager, mock_logger)

    async def test_insert_vendor_config_success(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_dict = {"vendor_id": ObjectId(), "data": "test"}
        mock_collection = AsyncMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id=ObjectId())
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.insert_vendor_config(config_dict)

        # Assert
        mock_collection.insert_one.assert_called_once_with(config_dict)
        mock_logger.info.assert_called_once()
        assert isinstance(result, str)

    async def test_insert_vendor_config_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_dict = {"vendor_id": ObjectId(), "data": "test"}
        mock_collection = AsyncMock()
        mock_collection.insert_one.side_effect = Exception("DB Error")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(Exception, match="DB Error"):
            await repository.insert_vendor_config(config_dict)
        mock_logger.error.assert_called_once()

    async def test_check_vendor_config_exists_for_existing_vendor_success(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {"_id": ObjectId()}
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.check_vendor_config_exists_for_existing_vendor(
            vendor_id
        )

        # Assert
        mock_collection.find_one.assert_called_once_with({"vendor_id": vendor_id})
        mock_logger.info.assert_called_once()
        assert result is True

    async def test_check_vendor_config_exists_for_existing_vendor_not_found(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.check_vendor_config_exists_for_existing_vendor(
            vendor_id
        )

        # Assert
        mock_collection.find_one.assert_called_once_with({"vendor_id": vendor_id})
        mock_logger.info.assert_called_once()
        assert result is False

    async def test_check_vendor_config_exists_for_existing_vendor_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.find_one.side_effect = Exception("DB Error")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(Exception, match="DB Error"):
            await repository.check_vendor_config_exists_for_existing_vendor(vendor_id)
        mock_logger.error.assert_called_once()

    async def test_find_all_configs_include_inactive(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        mock_collection = AsyncMock()
        mock_configs = [
            {
                "_id": ObjectId(),
                "vendor_id": ObjectId(),
                "vendor": {"name": "Vendor1", "is_active": True},
            },
            {
                "_id": ObjectId(),
                "vendor_id": ObjectId(),
                "vendor": {"name": "Vendor2", "is_active": False},
            },
        ]
        mock_collection.aggregate = MagicMock(
            return_value=AsyncIterator(mock_configs)
        )  # Use MagicMock instead of AsyncMock
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.find_all_configs(include_inactive_vendors=True)

        # Assert
        mock_collection.aggregate.assert_called_once()
        assert len(result) == 2
        mock_logger.error.assert_not_called()

    async def test_find_all_configs_exclude_inactive(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        mock_collection = AsyncMock()
        mock_configs = [
            {
                "_id": ObjectId(),
                "vendor_id": ObjectId(),
                "vendor": {"name": "Vendor1", "is_active": True},
            }
        ]
        mock_collection.aggregate = MagicMock(
            return_value=AsyncIterator(mock_configs)
        )  # Use MagicMock instead of AsyncMock
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.find_all_configs(include_inactive_vendors=False)

        # Assert
        mock_collection.aggregate.assert_called_once()
        assert len(result) == 1
        mock_logger.error.assert_not_called()

    async def test_find_config_by_id_success(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        mock_collection = AsyncMock()
        mock_config = {
            "_id": config_id,
            "vendor_id": ObjectId(),
            "vendor": {"name": "Vendor1", "is_active": True},
            "available_did": "did1",
            "assigned_did": "did2",
            "generic_url_handler": "url",
            "created_at": "2023-01-01",
            "updated_at": "2023-01-02",
        }
        mock_collection.aggregate = MagicMock(return_value=AsyncIterator([mock_config]))
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.find_config_by_id(config_id)

        # Assert
        mock_collection.aggregate.assert_called_once()
        assert result == mock_config
        mock_logger.error.assert_not_called()

    async def test_find_config_by_id_not_found(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.aggregate = MagicMock(
            return_value=AsyncIterator([])
        )  # Use MagicMock instead of AsyncMock
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.find_config_by_id(config_id)

        # Assert
        mock_collection.aggregate.assert_called_once()
        assert result is None
        mock_logger.error.assert_not_called()

    async def test_update_vendor_config_success(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        update_dict = {"data": "updated"}
        mock_collection = AsyncMock()
        mock_updated_config = {"_id": config_id, "data": "updated"}
        mock_collection.find_one_and_update.return_value = mock_updated_config
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.update_vendor_config(config_id, update_dict)

        # Assert
        mock_collection.find_one_and_update.assert_called_once_with(
            {"_id": config_id}, {"$set": update_dict}, return_document=True
        )
        mock_logger.info.assert_called_once()
        assert result == mock_updated_config

    async def test_update_vendor_config_not_found(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        update_dict = {"data": "updated"}
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(
            ValueError, match=f"Vendor config for vendor_id {config_id} not found"
        ):
            await repository.update_vendor_config(config_id, update_dict)
        assert (
            mock_logger.error.call_count == 2
        )  # Expect two error logs due to current implementation
        mock_collection.find_one_and_update.assert_called_once_with(
            {"_id": config_id}, {"$set": update_dict}, return_document=True
        )

    async def test_update_vendor_config_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        update_dict = {"data": "updated"}
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.side_effect = Exception("DB Error")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(Exception, match="DB Error"):
            await repository.update_vendor_config(config_id, update_dict)
        mock_logger.error.assert_called_once()

    async def test_check_vendor_config_exists_for_existing_vendor_using_pk_id_collection_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        mock_db_manager.collection.return_value.__aenter__.side_effect = Exception(
            "Collection Access Error"
        )

        # Act/Assert
        with pytest.raises(Exception, match="Collection Access Error"):
            await repository.check_vendor_config_exists_for_existing_vendor_using_pk_id(
                config_id
            )
        mock_logger.error.assert_called_once_with(
            f"Failed to check vendor config existence for vendor_id {config_id}: Collection Access Error"
        )

    async def test_check_vendor_config_exists_for_existing_vendor_using_pk_id_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.find_one.side_effect = Exception("DB Error")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(Exception, match="DB Error"):
            await repository.check_vendor_config_exists_for_existing_vendor_using_pk_id(
                config_id
            )
        mock_logger.error.assert_called_once_with(
            f"Failed to check vendor config existence for vendor_id {config_id}: DB Error"
        )

    async def test_check_vendor_config_exists_for_existing_vendor_using_pk_id_success(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {"_id": config_id}
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = (
            await repository.check_vendor_config_exists_for_existing_vendor_using_pk_id(
                config_id
            )
        )

        # Assert
        mock_collection.find_one.assert_called_once_with({"_id": config_id})
        mock_logger.info.assert_called_once_with(
            f"Vendor config exists for vendor_id {config_id}: True"
        )
        assert result is True

    async def test_check_vendor_config_exists_for_existing_vendor_using_pk_id_not_found(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = (
            await repository.check_vendor_config_exists_for_existing_vendor_using_pk_id(
                config_id
            )
        )

        # Assert
        mock_collection.find_one.assert_called_once_with({"_id": config_id})
        mock_logger.info.assert_called_once_with(
            f"Vendor config exists for vendor_id {config_id}: False"
        )
        assert result is False

    async def test_find_all_configs_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        mock_collection = AsyncMock()
        mock_collection.aggregate = MagicMock(side_effect=Exception("DB Error"))
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(Exception, match="DB Error"):
            await repository.find_all_configs(include_inactive_vendors=True)
        mock_logger.error.assert_called_once_with(
            "Failed to retrieve vendor configs: DB Error"
        )

    async def test_find_all_configs_db_error(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        mock_collection = AsyncMock()
        mock_collection.aggregate = MagicMock(
            side_effect=RuntimeError("Database Failure")
        )
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(RuntimeError, match="Database Failure"):
            await repository.find_all_configs(include_inactive_vendors=False)
        mock_logger.error.assert_called_once_with(
            "Failed to retrieve vendor configs: Database Failure"
        )

    async def test_find_all_configs_collection_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        mock_db_manager.collection.return_value.__aenter__.side_effect = Exception(
            "Collection Access Error"
        )

        # Act/Assert
        with pytest.raises(Exception, match="Collection Access Error"):
            await repository.find_all_configs(include_inactive_vendors=True)
        mock_logger.error.assert_called_once_with(
            "Failed to retrieve vendor configs: Collection Access Error"
        )

    async def test_find_config_by_id_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.aggregate = MagicMock(side_effect=Exception("DB Error"))
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(Exception, match="DB Error"):
            await repository.find_config_by_id(config_id)
        mock_logger.error.assert_called_once_with(
            f"Failed to find vendor config for config_id {config_id}: DB Error"
        )

    async def test_find_config_by_id_db_error(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.aggregate = MagicMock(
            side_effect=RuntimeError("Database Failure")
        )
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(RuntimeError, match="Database Failure"):
            await repository.find_config_by_id(config_id)
        mock_logger.error.assert_called_once_with(
            f"Failed to find vendor config for config_id {config_id}: Database Failure"
        )

    async def test_find_config_by_id_collection_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        config_id = ObjectId()
        mock_db_manager.collection.return_value.__aenter__.side_effect = Exception(
            "Collection Access Error"
        )

        # Act/Assert
        with pytest.raises(Exception, match="Collection Access Error"):
            await repository.find_config_by_id(config_id)
        mock_logger.error.assert_called_once_with(
            f"Failed to find vendor config for config_id {config_id}: Collection Access Error"
        )

    async def test_find_configs_by_vendor_id_success(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_id = ObjectId()
        mock_collection = AsyncMock()
        mock_configs = [
            {
                "_id": ObjectId(),
                "vendor_id": vendor_id,
                "available_did": ["did1"],
                "assigned_did": ["did2"],
            }
        ]
        mock_collection.aggregate = MagicMock(return_value=AsyncIterator(mock_configs))
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.find_configs_by_vendor_id(vendor_id)

        # Assert
        mock_collection.aggregate.assert_called_once()
        assert result == mock_configs
        mock_logger.error.assert_not_called()

    async def test_find_configs_by_vendor_id_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.aggregate = MagicMock(side_effect=Exception("DB Error"))
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(Exception, match="DB Error"):
            await repository.find_configs_by_vendor_id(vendor_id)
        mock_logger.error.assert_called_once_with(
            f"Failed to find vendor configs for vendor_id {vendor_id}: DB Error"
        )

    async def test_update_did_lists_success(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_id = ObjectId()
        mock_collection = AsyncMock()
        updated_document = {
            "vendor_id": vendor_id,
            "available_did": [],
            "assigned_did": [],
        }
        mock_collection.find_one_and_update.return_value = updated_document
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.update_did_lists(
            vendor_id,
            remove_from_available=["did1"],
            add_to_available=["did3"],
            remove_from_assigned=["did2"],
            add_to_assigned=["did4"],
            updated_at=1234567890,
        )

        # Assert
        assert result == updated_document
        mock_collection.find_one_and_update.assert_called_once()
        mock_logger.info.assert_called_once_with(
            f"Updated DID lists for vendor_id {vendor_id}"
        )

    async def test_update_did_lists_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.side_effect = Exception("DB Error")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(Exception, match="DB Error"):
            await repository.update_did_lists(
                vendor_id,
                remove_from_available=[],
                add_to_available=[],
                remove_from_assigned=[],
                add_to_assigned=[],
                updated_at=1234567890,
            )
        mock_logger.error.assert_called_once_with(
            f"Failed to update DID lists for vendor_id {vendor_id}: DB Error"
        )

    async def test_update_vendor_config_by_vendor_id_success(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_id = ObjectId()
        update_dict = {"$set": {"generic_url_handler": "https://new-url.com"}}
        mock_collection = AsyncMock()
        updated_doc = {
            "vendor_id": vendor_id,
            "generic_url_handler": "https://new-url.com",
        }
        mock_collection.find_one_and_update.return_value = updated_doc
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.update_vendor_config_by_vendor_id(
            vendor_id, update_dict
        )

        # Assert
        assert result == updated_doc
        mock_logger.info.assert_called_once_with(
            f"Updated vendor config for vendor_id: {vendor_id}"
        )

    async def test_update_vendor_config_by_vendor_id_not_found(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_id = ObjectId()
        update_dict = {"$set": {"generic_url_handler": "https://new-url.com"}}
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(ValueError, match="No vendor config found for vendor_id."):
            await repository.update_vendor_config_by_vendor_id(vendor_id, update_dict)

    async def test_update_vendor_config_by_vendor_id_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_id = ObjectId()
        update_dict = {"$set": {"generic_url_handler": "https://new-url.com"}}
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.side_effect = Exception("DB Error")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(Exception, match="DB Error"):
            await repository.update_vendor_config_by_vendor_id(vendor_id, update_dict)
        mock_logger.error.assert_called_once_with(
            f"Failed to update vendor config for vendor_id {vendor_id}: DB Error"
        )

    async def test_update_did_lists_not_found(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_id = ObjectId()
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(ValueError, match="Vendor config for vendor_id not found."):
            await repository.update_did_lists(
                vendor_id,
                remove_from_available=[],
                add_to_available=[],
                remove_from_assigned=[],
                add_to_assigned=[],
                updated_at=1234567890,
            )

        assert mock_logger.error.call_count == 2
        mock_logger.error.assert_any_call(
            f"Vendor config for vendor_id {vendor_id} not found"
        )
        mock_logger.error.assert_any_call(
            f"Failed to update DID lists for vendor_id {vendor_id}: Vendor config for vendor_id not found."
        )

    async def test_get_vendor_config_by_vendor_type_success(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_type = "tata_tele"
        mock_collection = AsyncMock()
        mock_configs = [
            {
                "_id": ObjectId(),
                "vendor_id": ObjectId(),
                "generic_url_handler": "https://generic.com",
                "cdr_url_handler": "https://cdr.com",
                "created_at": "2025-09-22T12:00:00Z",
                "updated_at": "2025-09-22T12:01:00Z",
                "vendor_name": "Vendor1",
                "vendor_type": vendor_type,
            },
            {
                "_id": ObjectId(),
                "vendor_id": ObjectId(),
                "generic_url_handler": "https://generic2.com",
                "cdr_url_handler": "https://cdr2.com",
                "created_at": "2025-09-22T12:10:00Z",
                "updated_at": "2025-09-22T12:11:00Z",
                "vendor_name": "Vendor2",
                "vendor_type": vendor_type,
            },
        ]
        mock_collection.aggregate = MagicMock(return_value=AsyncIterator(mock_configs))
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act
        result = await repository.get_vendor_config_by_vendor_type(vendor_type)

        # Assert
        mock_collection.aggregate.assert_called_once()
        assert result == mock_configs
        mock_logger.error.assert_not_called()

    async def test_get_vendor_config_by_vendor_type_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        # Arrange
        vendor_type = "tata_tele"
        mock_collection = AsyncMock()
        mock_collection.aggregate = MagicMock(side_effect=Exception("DB Error"))
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        # Act/Assert
        with pytest.raises(Exception, match="DB Error"):
            await repository.get_vendor_config_by_vendor_type(vendor_type)
        mock_logger.error.assert_called_once_with(
            f"Failed to find vendor configs for vendor_type {vendor_type}: DB Error"
        )
