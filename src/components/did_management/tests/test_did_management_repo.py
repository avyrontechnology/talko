from unittest.mock import AsyncMock, Mock

import pytest
from bson import ObjectId

from src.components.did_management.constants import DIDStatus
from src.components.did_management.repositories import DidRepository
from src.core.doc_db import DocDatabaseSessionManager
from src.loggers.holler_service_logger import HollerServiceLogger


class AsyncContextManagerMock:
    def __init__(self, collection):
        self.collection = collection

    async def __aenter__(self):
        return self.collection

    async def __aexit__(self, exc_type, exc, tb):
        pass


class AsyncIteratorMock:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


class FailingAsyncIterator:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise Exception("Database error")


@pytest.fixture
def mock_db_manager():
    return Mock(spec=DocDatabaseSessionManager)


@pytest.fixture
def mock_logger():
    return Mock(spec=HollerServiceLogger)


@pytest.fixture
def did_repository(mock_db_manager, mock_logger):
    return DidRepository(db_manager=mock_db_manager, logger=mock_logger)


def _wire(mock_db_manager, col):
    mock_db_manager.collection.return_value = AsyncContextManagerMock(col)


class TestInsertDidDefaultAttendance:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        did_data = {"did_number": "12345", "partner_id": 1, "vendor_id": ObjectId()}
        inserted_id = ObjectId("507f1f77bcf86cd799439011")
        col = AsyncMock()
        col.insert_one = AsyncMock(return_value=Mock(inserted_id=inserted_id))
        _wire(mock_db_manager, col)

        result = await did_repository.insert_did_default_attendance(did_data)

        col.insert_one.assert_awaited_once_with(did_data)
        assert result["did_number"] == did_data["did_number"]
        assert result["partner_id"] == did_data["partner_id"]
        assert result["_id"] == inserted_id
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.insert_one = AsyncMock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.insert_did_default_attendance({"did_number": "x"})

        mock_logger.error.assert_called_once_with(
            "Failed to insert DID attendance: Database error"
        )


class TestInsertDidHistory:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        history_data = {"did_number": "919876543210", "partner_id": 1}
        inserted_id = ObjectId("507f1f77bcf86cd799439011")
        col = AsyncMock()
        col.insert_one = AsyncMock(return_value=Mock(inserted_id=inserted_id))
        _wire(mock_db_manager, col)

        # snapshot before call — insert_one mutates did_data in-place
        expected_insert_arg = dict(history_data)

        result = await did_repository.insert_did_history(history_data)

        col.insert_one.assert_awaited_once_with(expected_insert_arg)
        assert result["did_number"] == expected_insert_arg["did_number"]
        assert result["_id"] == inserted_id
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.insert_one = AsyncMock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.insert_did_history({"did_number": "x"})

        mock_logger.error.assert_called_once_with(
            "Failed to insert DID history: Database error"
        )


class TestFindDidAttendance:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        did_number, partner_id = "12345", 1
        expected = {"did_number": did_number, "partner_id": partner_id}
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=expected)
        _wire(mock_db_manager, col)

        result = await did_repository.find_did_attendance(did_number, partner_id)

        col.find_one.assert_awaited_once_with(
            {"did_number": did_number, "partner_id": partner_id}
        )
        assert result == expected
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_found(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=None)
        _wire(mock_db_manager, col)

        result = await did_repository.find_did_attendance("99999", 99)
        assert result is None

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find_one = AsyncMock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.find_did_attendance("12345", 1)

        mock_logger.error.assert_called_once_with(
            "Failed to find DID attendance: Database error"
        )


class TestDeleteDidDefaultAttendance:

    @pytest.mark.asyncio
    async def test_deleted(self, did_repository, mock_db_manager, mock_logger):
        did_number, partner_id = "12345", 1
        col = AsyncMock()
        col.delete_one = AsyncMock(return_value=Mock(deleted_count=1))
        _wire(mock_db_manager, col)

        result = await did_repository.delete_did_default_attendance(
            did_number, partner_id
        )

        col.delete_one.assert_awaited_once_with(
            {"did_number": did_number, "partner_id": partner_id}
        )
        assert result is True
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_nothing_deleted(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.delete_one = AsyncMock(return_value=Mock(deleted_count=0))
        _wire(mock_db_manager, col)

        result = await did_repository.delete_did_default_attendance("00000", 0)
        assert result is False

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.delete_one = AsyncMock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.delete_did_default_attendance("12345", 1)

        mock_logger.error.assert_called_once_with(
            "Failed to delete DID attendance: Database error"
        )


class TestUpdateDidHistory:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        did_number, partner_id = "12345", 1
        update_dict = {"status": "updated"}
        expected = {
            "did_number": did_number,
            "partner_id": partner_id,
            "status": "updated",
        }
        col = AsyncMock()
        col.find_one_and_update = AsyncMock(return_value=expected)
        _wire(mock_db_manager, col)

        result = await did_repository.update_did_history(
            did_number, partner_id, update_dict
        )

        col.find_one_and_update.assert_awaited_once_with(
            {"did_number": did_number, "partner_id": partner_id},
            {"$set": update_dict},
            return_document=True,
        )
        assert result == expected
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_found_returns_none(
        self, did_repository, mock_db_manager, mock_logger
    ):
        col = AsyncMock()
        col.find_one_and_update = AsyncMock(return_value=None)
        _wire(mock_db_manager, col)

        result = await did_repository.update_did_history("12345", 1, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find_one_and_update = AsyncMock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.update_did_history("12345", 1, {})

        mock_logger.error.assert_called_once_with(
            "Failed to update DID history: Database error"
        )


class TestGetAssignedDids:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        vendor_id = ObjectId()
        docs = [{"did_number": "12345"}, {"did_number": "67890"}]
        col = AsyncMock()
        col.find = Mock(return_value=AsyncIteratorMock(docs))
        _wire(mock_db_manager, col)

        result = await did_repository.get_assigned_dids(vendor_id)

        col.find.assert_called_once_with(
            {"vendor_id": vendor_id, "partner_id": {"$ne": 0}}
        )
        assert result == ["12345", "67890"]
        mock_logger.info.assert_called_with("Fetched assigned DIDs: ['12345', '67890']")
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_result(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find = Mock(return_value=AsyncIteratorMock([]))
        _wire(mock_db_manager, col)

        result = await did_repository.get_assigned_dids(ObjectId())
        assert result == []

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find = Mock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.get_assigned_dids(ObjectId())

        mock_logger.error.assert_called_once_with(
            "Failed to fetch assigned DIDs: Database error"
        )


class TestGetAvailableDids:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        """
        FIX 1: the real query always includes vendor_config_id and status.
        vendor_config_id defaults to None when not supplied by the caller.
        """
        vendor_id = ObjectId()
        docs = [{"did_number": "12345"}, {"did_number": "67890"}]
        col = AsyncMock()
        col.find = Mock(return_value=AsyncIteratorMock(docs))
        _wire(mock_db_manager, col)

        result = await did_repository.get_available_dids(vendor_id)

        col.find.assert_called_once_with(
            {
                "vendor_id": vendor_id,
                "partner_id": 0,
                "vendor_config_id": None,
                "status": DIDStatus.AVAILABLE.value,
            }
        )
        assert result == ["12345", "67890"]
        mock_logger.info.assert_called_with(
            "Fetched available DIDs: ['12345', '67890']"
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_with_vendor_config_id(
        self, did_repository, mock_db_manager, mock_logger
    ):
        vendor_id = ObjectId()
        vendor_config_id = ObjectId()
        col = AsyncMock()
        col.find = Mock(return_value=AsyncIteratorMock([{"did_number": "11111"}]))
        _wire(mock_db_manager, col)

        result = await did_repository.get_available_dids(vendor_id, vendor_config_id)

        col.find.assert_called_once_with(
            {
                "vendor_id": vendor_id,
                "partner_id": 0,
                "vendor_config_id": vendor_config_id,
                "status": DIDStatus.AVAILABLE.value,
            }
        )
        assert result == ["11111"]

    @pytest.mark.asyncio
    async def test_empty_result(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find = Mock(return_value=AsyncIteratorMock([]))
        _wire(mock_db_manager, col)

        result = await did_repository.get_available_dids(ObjectId())
        assert result == []

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find = Mock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.get_available_dids(ObjectId())

        mock_logger.error.assert_called_once_with(
            "Failed to fetch available DIDs: Database error"
        )


class TestFindDidByDidNumberAndVendorId:

    @pytest.mark.asyncio
    async def test_found(self, did_repository, mock_db_manager, mock_logger):
        did_number, vendor_id = "12345", ObjectId()
        expected = {"did_number": did_number, "vendor_id": vendor_id}
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=expected)
        _wire(mock_db_manager, col)

        result = await did_repository.find_did_by_did_number_and_vendor_id(
            did_number, vendor_id
        )

        col.find_one.assert_awaited_once_with(
            {"did_number": did_number, "vendor_id": vendor_id}
        )
        assert result == expected
        mock_logger.debug.assert_any_call(
            "Found DID {} for vendor {}".format(did_number, vendor_id)
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_found(self, did_repository, mock_db_manager, mock_logger):
        did_number, vendor_id = "12345", ObjectId()
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=None)
        _wire(mock_db_manager, col)

        result = await did_repository.find_did_by_did_number_and_vendor_id(
            did_number, vendor_id
        )

        assert result is None
        mock_logger.warning.assert_called_once_with(
            "DID {} not found for vendor {} with query {}".format(
                did_number,
                vendor_id,
                {"did_number": did_number, "vendor_id": vendor_id},
            )
        )

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        did_number, vendor_id = "12345", ObjectId()
        col = AsyncMock()
        col.find_one = AsyncMock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.find_did_by_did_number_and_vendor_id(
                did_number, vendor_id
            )

        mock_logger.error.assert_called_once_with(
            "Unexpected error finding DID {}: Database error".format(did_number)
        )


class TestUpdateDidAttendance:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        did_number, partner_id = "12345", 1
        update_data = {"status": "assigned"}
        existing = {"did_number": did_number, "partner_id": 0}
        updated = {
            "did_number": did_number,
            "partner_id": partner_id,
            "status": "assigned",
        }
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=existing)
        col.find_one_and_update = AsyncMock(return_value=updated)
        _wire(mock_db_manager, col)

        result = await did_repository.update_did_attendance(
            did_number, partner_id, update_data
        )

        col.find_one.assert_awaited_once_with(
            {"did_number": did_number, "partner_id": 0}
        )
        assert result == updated
        mock_logger.info.assert_called_with(
            "Successfully updated DID {} to partner {}".format(did_number, partner_id)
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_available(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=None)
        _wire(mock_db_manager, col)

        result = await did_repository.update_did_attendance("12345", 1, {})

        assert result is None
        mock_logger.warning.assert_called_once_with(
            "DID 12345 not available (partner_id != 0)"
        )

    @pytest.mark.asyncio
    async def test_update_returns_none(
        self, did_repository, mock_db_manager, mock_logger
    ):
        col = AsyncMock()
        col.find_one = AsyncMock(return_value={"did_number": "12345", "partner_id": 0})
        col.find_one_and_update = AsyncMock(return_value=None)
        _wire(mock_db_manager, col)

        result = await did_repository.update_did_attendance("12345", 1, {})

        assert result is None
        mock_logger.warning.assert_called_with(
            "Failed to update DID 12345 to partner 1"
        )

    @pytest.mark.asyncio
    async def test_exception(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find_one = AsyncMock(return_value={"did_number": "12345", "partner_id": 0})
        col.find_one_and_update = AsyncMock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.update_did_attendance("12345", 1, {})

        mock_logger.error.assert_called_once_with(
            "Unexpected error updating DID 12345: Database error"
        )


class TestGetDidsByPartnerAndVendor:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        partner_id, vendor_id = 1, ObjectId()
        docs = [{"did_number": "12345"}, {"did_number": "67890"}]
        col = AsyncMock()
        col.find = Mock(return_value=AsyncIteratorMock(docs))
        _wire(mock_db_manager, col)

        result = await did_repository.get_dids_by_partner_and_vendor(
            partner_id, vendor_id
        )

        col.find.assert_called_once_with(
            {"partner_id": partner_id, "vendor_id": vendor_id}
        )
        assert result == ["12345", "67890"]
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find = Mock(return_value=AsyncIteratorMock([]))
        _wire(mock_db_manager, col)

        result = await did_repository.get_dids_by_partner_and_vendor(1, ObjectId())
        assert result == []

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find = Mock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.get_dids_by_partner_and_vendor(1, ObjectId())

        mock_logger.error.assert_called_once_with(
            "Failed to fetch DIDs for partner 1: Database error"
        )


class TestGetDidsByPartnerServiceBoardAndVendor:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        partner_id, service_board_id, vendor_id = 1, 100, ObjectId()
        docs = [{"did_number": "12345"}, {"did_number": "67890"}]
        col = AsyncMock()
        col.find = Mock(return_value=AsyncIteratorMock(docs))
        _wire(mock_db_manager, col)

        result = await did_repository.get_dids_by_partner_service_board_and_vendor(
            partner_id, service_board_id, vendor_id
        )

        col.find.assert_called_once_with(
            {
                "partner_id": partner_id,
                "service_board_id": service_board_id,
                "vendor_id": vendor_id,
            }
        )
        assert result == ["12345", "67890"]
        mock_logger.info.assert_called_with(
            "Fetched DIDs get did by partner service board and vendor: ['12345', '67890']"
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find = Mock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.get_dids_by_partner_service_board_and_vendor(
                1, 100, ObjectId()
            )

        mock_logger.error.assert_called_once_with(
            "Failed to fetch DIDs for partner 1, service_board 100: Database error"
        )


class TestGetDidsByPartnerAgentServiceBoardAndVendor:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        partner_id, user_id, service_board_id, vendor_id = 1, 200, 100, ObjectId()
        docs = [{"did_number": "12345"}, {"did_number": "67890"}]
        col = AsyncMock()
        col.find = Mock(return_value=AsyncIteratorMock(docs))
        _wire(mock_db_manager, col)

        result = (
            await did_repository.get_dids_by_partner_agent_service_board_and_vendor(
                partner_id, user_id, service_board_id, vendor_id
            )
        )

        col.find.assert_called_once_with(
            {
                "partner_id": partner_id,
                "agent_id": user_id,
                "service_board_id": service_board_id,
                "vendor_id": vendor_id,
            }
        )
        assert result == ["12345", "67890"]
        mock_logger.info.assert_called_with(
            "Fetched DIDs get did by partner agent service board and vendor: "
            "['12345', '67890']"
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find = Mock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.get_dids_by_partner_agent_service_board_and_vendor(
                1, 200, 100, ObjectId()
            )

        mock_logger.error.assert_called_once_with(
            "Failed to fetch DIDs for partner 1, agent 200, service_board 100: "
            "Database error"
        )


class TestGetDidByNumber:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        # 12-digit number starting with 91 → normalize keeps as-is: "919876543210"
        call_to_number = "919876543210"
        normalized = "919876543210"
        did_record = {"_id": ObjectId(), "did_number": normalized}
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=did_record)
        _wire(mock_db_manager, col)

        result = await did_repository.get_did_by_number(call_to_number)

        col.find_one.assert_called_once_with({"did_number": normalized})
        assert result == did_record
        mock_logger.debug.assert_any_call(f"Searching DID for number: {call_to_number}")
        mock_logger.debug.assert_any_call(f"Found DID record: {did_record}")
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_record(self, did_repository, mock_db_manager, mock_logger):
        call_to_number = "917654321098"
        normalized = "917654321098"  # 12 digits starting with 91 → kept as-is
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=None)
        _wire(mock_db_manager, col)

        result = await did_repository.get_did_by_number(call_to_number)

        col.find_one.assert_called_once_with({"did_number": normalized})
        assert result is None

    @pytest.mark.asyncio
    async def test_not_found_logged_as_info(
        self, did_repository, mock_db_manager, mock_logger
    ):
        call_to_number = "+911234567890"
        normalized = (
            "911234567890"  # + stripped by normalize_phone_number with_plus=False
        )
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=None)
        _wire(mock_db_manager, col)

        result = await did_repository.get_did_by_number(call_to_number)

        # query uses normalized (no +), not raw input
        col.find_one.assert_awaited_once_with({"did_number": normalized})
        assert result is None
        mock_logger.debug.assert_any_call(f"Searching DID for number: {call_to_number}")
        mock_logger.info.assert_any_call("No DID record found for given number")
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_partner_id(self, did_repository, mock_db_manager, mock_logger):
        call_to_number = "1234567890"
        normalized = "911234567890"  # 10-digit → prepend 91
        partner_id = 5
        did_record = {"did_number": normalized, "partner_id": partner_id}
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=did_record)
        _wire(mock_db_manager, col)

        result = await did_repository.get_did_by_number(call_to_number, partner_id)

        col.find_one.assert_called_once_with(
            {"did_number": normalized, "partner_id": partner_id}
        )
        assert result == did_record

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find_one = AsyncMock(side_effect=Exception("DB error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="DB error"):
            await did_repository.get_did_by_number("917000012345")

        mock_logger.error.assert_called_once_with(
            "Error finding DID by number: DB error"
        )


class TestGetDidsByServiceBoard:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        service_board_id = 100
        records = [
            {"did_number": "12345", "service_board_id": service_board_id},
            {"did_number": "67890", "service_board_id": service_board_id},
        ]
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=records)
        col = AsyncMock()
        col.find = Mock(return_value=mock_cursor)
        _wire(mock_db_manager, col)

        result = await did_repository.get_dids_by_service_board(service_board_id)

        col.find.assert_called_once_with(
            {
                "service_board_id": service_board_id,
                "status": DIDStatus.AVAILABLE.value,
            }
        )
        mock_cursor.to_list.assert_awaited_once_with(length=None)
        assert result == records
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_result(self, did_repository, mock_db_manager, mock_logger):
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        col = AsyncMock()
        col.find = Mock(return_value=mock_cursor)
        _wire(mock_db_manager, col)

        result = await did_repository.get_dids_by_service_board(999)
        assert result == []

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(side_effect=Exception("Database error"))
        col = AsyncMock()
        col.find = Mock(return_value=mock_cursor)
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.get_dids_by_service_board(100)

        mock_logger.error.assert_called_once_with(
            "Failed to fetch DIDs for service_board_id=100: Database error"
        )


class TestGetDetailsByDids:

    @pytest.mark.asyncio
    async def test_success_multiple(self, did_repository, mock_db_manager, mock_logger):
        oid1 = ObjectId("507f1f77bcf86cd799439011")
        oid2 = ObjectId("507f191e810c19729de860ea")
        did_numbers = ["12345", "67890"]
        docs = [
            {"did_number": "12345", "_id": oid1},
            {"did_number": "67890", "_id": oid2},
        ]
        col = AsyncMock()
        col.find = Mock(return_value=AsyncIteratorMock(docs))
        _wire(mock_db_manager, col)

        result = await did_repository.get_details_by_dids(did_numbers)

        expected = [
            {"did_number": "12345", "instance_id": str(oid1)},
            {"did_number": "67890", "instance_id": str(oid2)},
        ]
        assert result == expected
        mock_logger.info.assert_any_call(
            f"Fetching instance IDs for DIDs: {did_numbers}"
        )
        mock_logger.info.assert_any_call(
            "Fetched DID instance details: {}".format(expected)
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_list(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find = Mock(return_value=AsyncIteratorMock([]))
        _wire(mock_db_manager, col)

        result = await did_repository.get_details_by_dids([])
        assert result == []

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find = Mock(return_value=FailingAsyncIterator())
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.get_details_by_dids(["12345", "67890"])

        mock_logger.error.assert_called_once_with(
            "Failed to fetch instance_id for DIDs ['12345', '67890']: Database error"
        )


class TestUnassignDidToPartner:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        did_number, partner_id = "1234567890", 10
        col = AsyncMock()
        col.update_one = AsyncMock(return_value=Mock(modified_count=1))
        _wire(mock_db_manager, col)

        result = await did_repository.unassign_did_to_partner(did_number, partner_id)

        col.update_one.assert_awaited_once_with(
            {"did_number": did_number},
            {
                "$set": {
                    "partner_id": 0,
                    "agent_id": None,
                    "service_board_id": None,
                }
            },
        )
        assert result is True
        mock_logger.info.assert_any_call(
            "Unassigning DiD {} to partner_id: {}".format(did_number, partner_id)
        )
        mock_logger.info.assert_any_call(
            "Successfully unassigned DID {}".format(did_number)
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_update(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.update_one = AsyncMock(return_value=Mock(modified_count=0))
        _wire(mock_db_manager, col)

        result = await did_repository.unassign_did_to_partner("1234567890", 10)

        assert result is False
        mock_logger.warning.assert_called_once_with(
            "No records updated for DID 1234567890"
        )

    @pytest.mark.asyncio
    async def test_exception(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.update_one = AsyncMock(side_effect=Exception("DB error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="DB error"):
            await did_repository.unassign_did_to_partner("1234567890", 10)

        mock_logger.error.assert_called_once_with(
            "Failed to fetch instance_id for DIDs 1234567890: DB error"
        )


class TestUpdateDidStatus:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        did_number, partner_id = "9876543210", 1
        normalized = "919876543210"  # 10-digit → normalize adds 91
        update_data = {"status": "suspended"}
        existing = {"did_number": normalized, "partner_id": partner_id}
        updated = {
            "did_number": normalized,
            "partner_id": partner_id,
            "status": "suspended",
        }
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=existing)
        col.find_one_and_update = AsyncMock(return_value=updated)
        _wire(mock_db_manager, col)

        result = await did_repository.update_did_status(
            did_number, partner_id, update_data
        )

        # find_one uses normalized number
        col.find_one.assert_awaited_once_with(
            {"did_number": normalized, "partner_id": partner_id}
        )
        assert result == updated
        mock_logger.info.assert_called_with(
            "Successfully updated DID {} to partner {}".format(did_number, partner_id)
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_did_not_found(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.find_one = AsyncMock(return_value=None)
        _wire(mock_db_manager, col)

        result = await did_repository.update_did_status(
            "9876543210", 1, {"status": "x"}
        )

        assert result is None
        mock_logger.warning.assert_called_once_with(
            "DID 9876543210 not available (partner_id != 0)"
        )

    @pytest.mark.asyncio
    async def test_update_returns_none(
        self, did_repository, mock_db_manager, mock_logger
    ):
        normalized = "919876543210"
        col = AsyncMock()
        col.find_one = AsyncMock(
            return_value={"did_number": normalized, "partner_id": 1}
        )
        col.find_one_and_update = AsyncMock(return_value=None)
        _wire(mock_db_manager, col)

        result = await did_repository.update_did_status("9876543210", 1, {})

        assert result is None
        mock_logger.warning.assert_called_with(
            "Failed to update DID 9876543210 to partner 1"
        )

    @pytest.mark.asyncio
    async def test_exception(self, did_repository, mock_db_manager, mock_logger):
        normalized = "919876543210"
        col = AsyncMock()
        col.find_one = AsyncMock(
            return_value={"did_number": normalized, "partner_id": 1}
        )
        col.find_one_and_update = AsyncMock(side_effect=Exception("Database error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.update_did_status("9876543210", 1, {})

        mock_logger.error.assert_called_once_with(
            "Unexpected error updating DID 9876543210: Database error"
        )


class TestIncrementSpamCount:

    @pytest.mark.asyncio
    async def test_success(self, did_repository, mock_db_manager, mock_logger):
        did_number = "12345"
        col = AsyncMock()
        col.update_one = AsyncMock(return_value=Mock(modified_count=1))
        _wire(mock_db_manager, col)

        result = await did_repository.increment_spam_count(did_number)

        col.update_one.assert_awaited_once_with(
            {"did_number": did_number}, {"$inc": {"spam_count": 1}}
        )
        assert result is True
        mock_logger.info.assert_called_with(
            "Successfully incremented spam_count for DID {}".format(did_number)
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_found(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.update_one = AsyncMock(return_value=Mock(modified_count=0))
        _wire(mock_db_manager, col)

        result = await did_repository.increment_spam_count("00000")

        assert result is False
        mock_logger.warning.assert_called_once_with(
            "No document found to increment spam_count for DID 00000"
        )

    @pytest.mark.asyncio
    async def test_exception(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.update_one = AsyncMock(side_effect=Exception("DB error"))
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="DB error"):
            await did_repository.increment_spam_count("12345")

        mock_logger.error.assert_called_once_with(
            "Failed to increment spam_count for DID 12345: DB error"
        )


class TestGetDidsByPartner:

    def _cursor(self, docs):
        items = list(docs)

        class ChainableCursor(AsyncIteratorMock):
            def __init__(self):
                super().__init__(items)
                self.sort = Mock(return_value=self)
                self.skip = Mock(return_value=self)
                self.limit = Mock(return_value=self)

        return ChainableCursor()

    @pytest.mark.asyncio
    async def test_success_no_pagination(
        self, did_repository, mock_db_manager, mock_logger
    ):
        partner_id = 1
        docs = [
            {"did_number": "11111", "partner_id": partner_id, "is_active": True},
            {"did_number": "22222", "partner_id": partner_id, "is_active": True},
        ]
        cursor = self._cursor(docs)
        col = AsyncMock()
        col.count_documents = AsyncMock(return_value=2)
        col.find = Mock(return_value=cursor)
        _wire(mock_db_manager, col)

        result_docs, total = await did_repository.get_dids_by_partner(partner_id)

        expected_query = {"partner_id": partner_id, "is_active": True}
        col.count_documents.assert_awaited_once_with(expected_query)
        col.find.assert_called_once_with(expected_query)
        cursor.sort.assert_called_once_with("status_changed_at", -1)
        cursor.skip.assert_not_called()
        cursor.limit.assert_not_called()
        assert total == 2
        assert len(result_docs) == 2
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_with_pagination(
        self, did_repository, mock_db_manager, mock_logger
    ):
        partner_id, offset, limit = 1, 2, 5
        cursor = self._cursor([{"did_number": "33333"}])
        col = AsyncMock()
        col.count_documents = AsyncMock(return_value=6)
        col.find = Mock(return_value=cursor)
        _wire(mock_db_manager, col)

        result_docs, total = await did_repository.get_dids_by_partner(
            partner_id, offset=offset, limit=limit
        )

        cursor.skip.assert_called_once_with(5)
        cursor.limit.assert_called_once_with(5)
        assert total == 6
        assert len(result_docs) == 1

    @pytest.mark.asyncio
    async def test_success_all_optional_filters(
        self, did_repository, mock_db_manager, mock_logger
    ):
        partner_id = 1
        user_id = 200
        service_board_id = 100
        vendor_id = ObjectId()
        vendor_config_id = ObjectId()
        status = "active"
        cursor = self._cursor([{"did_number": "44444"}])
        col = AsyncMock()
        col.count_documents = AsyncMock(return_value=1)
        col.find = Mock(return_value=cursor)
        _wire(mock_db_manager, col)

        _, total = await did_repository.get_dids_by_partner(
            partner_id,
            user_id=user_id,
            service_board_id=service_board_id,
            vendor_id=vendor_id,
            vendor_config_id=vendor_config_id,
            status=status,
        )

        expected_query = {
            "partner_id": partner_id,
            "is_active": True,
            "agent_id": user_id,
            "service_board_id": service_board_id,
            "vendor_id": vendor_id,
            "vendor_config_id": vendor_config_id,
            "status": status,
        }
        col.count_documents.assert_awaited_once_with(expected_query)
        col.find.assert_called_once_with(expected_query)
        assert total == 1

    @pytest.mark.asyncio
    async def test_none_optional_filters_excluded(
        self, did_repository, mock_db_manager, mock_logger
    ):
        cursor = self._cursor([])
        col = AsyncMock()
        col.count_documents = AsyncMock(return_value=0)
        col.find = Mock(return_value=cursor)
        _wire(mock_db_manager, col)

        await did_repository.get_dids_by_partner(
            1, user_id=None, vendor_id=None, service_board_id=None
        )

        call_query = col.count_documents.call_args[0][0]
        assert "agent_id" not in call_query
        assert "vendor_id" not in call_query
        assert "service_board_id" not in call_query

    @pytest.mark.asyncio
    async def test_failure(self, did_repository, mock_db_manager, mock_logger):
        col = AsyncMock()
        col.count_documents = AsyncMock(side_effect=Exception("Database error"))
        col.find = Mock()
        _wire(mock_db_manager, col)

        with pytest.raises(Exception, match="Database error"):
            await did_repository.get_dids_by_partner(1)

        mock_logger.error.assert_called_once()
        err_msg = mock_logger.error.call_args[0][0]
        assert "partner=1" in err_msg
        assert "Database error" in err_msg
