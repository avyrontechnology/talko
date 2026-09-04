from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.call_management.repository import TalkoCallRepository
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


@pytest.mark.asyncio
class TestCallRepository:
    @pytest.fixture
    def mock_db_manager(self):
        return MagicMock(spec=TalkoDocDatabaseSessionManager)

    @pytest.fixture
    def mock_logger(self):
        return MagicMock(spec=TalkoServiceLogger)

    @pytest.fixture
    def repository(self, mock_db_manager, mock_logger):
        return TalkoCallRepository(mock_db_manager, mock_logger)

    async def test_get_vendor_config_success(
        self, repository, mock_db_manager, mock_logger
    ):
        vendor_id = str(ObjectId())
        vendor_config_data = {"vendor_id": vendor_id}
        vendor_data = {"vendor_type": "acefhone"}

        mock_vendor_config_collection = AsyncMock()
        mock_vendor_config_collection.find_one.return_value = vendor_config_data
        mock_vendor_collection = AsyncMock()
        mock_vendor_collection.find_one.return_value = vendor_data

        mock_db_manager.collection.side_effect = [
            MagicMock(__aenter__=AsyncMock(return_value=mock_vendor_config_collection)),
            MagicMock(__aenter__=AsyncMock(return_value=mock_vendor_collection)),
        ]

        result = await repository.get_vendor_config(vendor_id)

        assert result["vendor_type"] == "acefhone"
        mock_logger.error.assert_not_called()

    async def test_get_vendor_config_vendor_not_found(
        self, repository, mock_db_manager, mock_logger
    ):
        vendor_id = str(ObjectId())
        mock_vendor_config_collection = AsyncMock()
        mock_vendor_config_collection.find_one.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_vendor_config_collection
        )

        result = await repository.get_vendor_config(vendor_id)
        assert result is None
        mock_logger.error.assert_called_once()

    async def test_get_vendor_config_vendor_type_missing(
        self, repository, mock_db_manager, mock_logger
    ):
        vendor_id = str(ObjectId())
        vendor_config_data = {"vendor_id": vendor_id}

        mock_vendor_config_collection = AsyncMock()
        mock_vendor_config_collection.find_one.return_value = vendor_config_data
        mock_vendor_collection = AsyncMock()
        mock_vendor_collection.find_one.return_value = {}

        mock_db_manager.collection.side_effect = [
            MagicMock(__aenter__=AsyncMock(return_value=mock_vendor_config_collection)),
            MagicMock(__aenter__=AsyncMock(return_value=mock_vendor_collection)),
        ]

        result = await repository.get_vendor_config(vendor_id)
        assert result["vendor_type"] is None
        mock_logger.warning.assert_called_once()

    async def test_get_partner_config_by_partner_id_success(
        self, repository, mock_db_manager
    ):
        partner_id = 123
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {"partner_id": partner_id}
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        result = await repository.get_partner_config_by_partner_id(partner_id)
        assert result["partner_id"] == partner_id

    async def test_get_partner_config_by_partner_id_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        partner_id = 123
        mock_collection = AsyncMock()
        mock_collection.find_one.side_effect = Exception("Failed to find")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        with pytest.raises(Exception, match="Failed to find"):
            await repository.get_partner_config_by_partner_id(partner_id)
        mock_logger.error.assert_called_once()

    async def test_update_partner_config_did_indices_success(
        self, repository, mock_db_manager, mock_logger
    ):
        partner_id = 123
        did_indices = {"round_robin": 1, 456: 2}
        updated_at = 1234567890
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = {
            "partner_id": partner_id,
            "did_indices": did_indices,
            "updated_at": updated_at,
        }
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        result = await repository.update_partner_config_did_indices(
            partner_id, did_indices, updated_at
        )
        assert result["did_indices"] == did_indices
        assert result["updated_at"] == updated_at
        mock_logger.info.assert_called_with(
            "Updated partner config did_indices for partner_id {}".format(partner_id)
        )

    async def test_update_partner_config_did_indices_no_document(
        self, repository, mock_db_manager, mock_logger
    ):
        partner_id = 123
        did_indices = {"round_robin": 1, 456: 2}
        updated_at = 1234567890
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        result = await repository.update_partner_config_did_indices(
            partner_id, did_indices, updated_at
        )
        assert result is None
        mock_logger.error.assert_called_with(
            "No partner config found to update did_indices for partner_id {}".format(
                partner_id
            )
        )

    async def test_update_partner_config_did_indices_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        partner_id = 123
        did_indices = {"round_robin": 1, 456: 2}
        updated_at = 1234567890
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.side_effect = Exception("Update error")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        with pytest.raises(Exception, match="Update error"):
            await repository.update_partner_config_did_indices(
                partner_id, did_indices, updated_at
            )
        mock_logger.error.assert_called_with(
            "Failed to update partner config did_indices for partner_id {}: {}".format(
                partner_id, "Update error"
            )
        )

    async def test_update_partner_config_inbound_round_robin_index_success(
        self, repository, mock_db_manager, mock_logger
    ):
        partner_id = 123
        inbound_round_robin_index = 2
        updated_at = 1234567890
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = {
            "partner_id": partner_id,
            "inbound_round_robin_index": inbound_round_robin_index,
            "updated_at": updated_at,
        }
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        result = await repository.update_partner_config_inbound_round_robin_index(
            partner_id, inbound_round_robin_index, updated_at
        )
        assert result["inbound_round_robin_index"] == inbound_round_robin_index
        assert result["updated_at"] == updated_at
        mock_logger.info.assert_called_with(
            "Updated partner config inbound_round_robin_index for partner_id {}".format(
                partner_id
            )
        )

    async def test_update_partner_config_inbound_round_robin_index_no_document(
        self, repository, mock_db_manager, mock_logger
    ):
        partner_id = 123
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        result = await repository.update_partner_config_inbound_round_robin_index(
            partner_id, 1, 1234567890
        )
        assert result is None
        mock_logger.error.assert_called_with(
            "No partner config found to update inbound_round_robin_index for partner_id {}".format(
                partner_id
            )
        )

    async def test_update_partner_config_inbound_round_robin_index_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        partner_id = 123
        mock_collection = AsyncMock()
        mock_collection.find_one_and_update.side_effect = Exception("Update error")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        with pytest.raises(Exception, match="Update error"):
            await repository.update_partner_config_inbound_round_robin_index(
                partner_id, 1, 1234567890
            )
        mock_logger.error.assert_called_with(
            "Failed to update partner config inbound_round_robin_index for partner_id {}: {}".format(
                partner_id, "Update error"
            )
        )

    async def test_insert_cdr_success(self, repository, mock_db_manager, mock_logger):
        cdr_dict = {"call_id": "c123"}
        mock_collection = AsyncMock()
        mock_collection.insert_one.return_value.inserted_id = ObjectId()
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        result = await repository.insert_cdr(cdr_dict)
        assert isinstance(result, str)
        mock_logger.info.assert_called_once()

    async def test_insert_cdr_failure(self, repository, mock_db_manager, mock_logger):
        mock_collection = AsyncMock()
        mock_collection.insert_one.side_effect = Exception("Insert fail")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        with pytest.raises(Exception, match="Insert fail"):
            await repository.insert_cdr({})
        mock_logger.error.assert_called_once()

    async def test_get_cdr_by_call_id_success(self, repository, mock_db_manager):
        call_id = "c123"
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {"call_id": call_id}
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        result = await repository.get_cdr_by_call_id_or_uuid(call_id, None)
        assert result["call_id"] == call_id

    async def test_get_cdr_by_uuid_success(self, repository, mock_db_manager):
        call_uuid = "c123"
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {"call_uuid": call_uuid}
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        result = await repository.get_cdr_by_call_id_or_uuid(None, call_uuid)
        assert result["call_uuid"] == call_uuid

    async def test_get_cdr_by_call_id_or_uuid_none(self, repository):
        result = await repository.get_cdr_by_call_id_or_uuid(None, None)
        assert result is None

    async def test_get_cdr_by_call_id_or_uuid_failure(
        self, repository, mock_db_manager, mock_logger
    ):
        mock_collection = AsyncMock()
        mock_collection.find_one.side_effect = Exception("Fetch error")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        with pytest.raises(Exception, match="Fetch error"):
            await repository.get_cdr_by_call_id_or_uuid("c123", None)
        mock_logger.error.assert_called_once()

    async def test_update_cdr_success(self, repository, mock_db_manager):
        cdr_id = str(ObjectId())
        updates = {"status": "completed"}
        mock_collection = AsyncMock()
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        result = await repository.update_cdr(cdr_id, updates)
        assert result is True

    async def test_update_cdr_failure(self, repository, mock_db_manager, mock_logger):
        mock_collection = AsyncMock()
        mock_collection.update_one.side_effect = Exception("Update failed")
        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        with pytest.raises(Exception, match="Update failed"):
            await repository.update_cdr(str(ObjectId()), {})
        mock_logger.error.assert_called_once()

    async def test_get_vendor_config_exception(
        self, repository, mock_db_manager, mock_logger
    ):
        vendor_id = str(ObjectId())
        mock_collection = AsyncMock()
        mock_collection.find_one.side_effect = Exception("DB access error")

        mock_db_manager.collection.return_value.__aenter__.return_value = (
            mock_collection
        )

        with pytest.raises(Exception, match="DB access error"):
            await repository.get_vendor_config(vendor_id)

        mock_logger.error.assert_called_once()

    async def test_find_cdr_by_numbers_success(
        self, repository, mock_db_manager, mock_logger
    ):
        caller_id = "123456"
        call_to = "654321"
        mock_cdr = {"customer": caller_id, "did_number": call_to, "created_at": 1000}

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.to_list = AsyncMock(return_value=[mock_cdr])

        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor

        mock_db_manager.collection.return_value.__aenter__ = AsyncMock(
            return_value=mock_collection
        )

        result = await repository.find_cdr_by_numbers(caller_id, call_to)

        assert result == mock_cdr
        mock_collection.find.assert_called_once()

    async def test_find_cdr_by_numbers_exception(
        self, repository, mock_db_manager, mock_logger
    ):
        mock_collection = MagicMock()
        mock_collection.find.side_effect = Exception("Query failed")

        mock_db_manager.collection.return_value.__aenter__ = AsyncMock(
            return_value=mock_collection
        )

        with pytest.raises(Exception, match="Query failed"):
            await repository.find_cdr_by_numbers("123", "456")

        mock_logger.error.assert_called_with(
            "Error finding TalkoCDR by numbers: Query failed"
        )

    async def test_find_cdr_by_numbers_not_found(
        self, repository, mock_db_manager, mock_logger
    ):
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.to_list = AsyncMock(return_value=[])  # Empty list

        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor
        mock_db_manager.collection.return_value.__aenter__ = AsyncMock(
            return_value=mock_collection
        )

        result = await repository.find_cdr_by_numbers("123", "456")

        assert result is None
        mock_logger.debug.assert_any_call("No TalkoCDR found for given numbers")
