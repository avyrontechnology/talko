from unittest.mock import ANY, AsyncMock, Mock

import pydantic
import pytest
from bson import ObjectId

from src.components.common.responses import BadRequestResponse
from src.components.did_management.constants import DIDStatus
from src.components.did_management.dto import Contract
from src.components.did_management.helpers import DidStatusUpdateHelper
from src.components.did_management.messages import PARTNER_CONFIG_NOT_FOUND
from src.components.did_management.repositories import DidRepository
from src.components.did_management.services import DidManagementService
from src.components.did_management.validator import DidValidator
from src.components.partner_config.repository import PartnerConfigRepository
from src.exceptions import ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.datetime_util import DateTimeUtil


@pytest.fixture
def mock_did_repository():
    return Mock(spec=DidRepository)


@pytest.fixture
def mock_partner_config_repository():
    return Mock(spec=PartnerConfigRepository)


@pytest.fixture
def mock_logger():
    return Mock(spec=HollerServiceLogger)


@pytest.fixture
def mock_datetime_util():
    m = Mock(spec=DateTimeUtil)
    m.get_current_time.return_value = 1_631_234_567_890
    return m


@pytest.fixture
def mock_validator():
    return Mock(spec=DidValidator)


@pytest.fixture
def did_management_service(
    mock_did_repository,
    mock_logger,
    mock_datetime_util,
    mock_validator,
    mock_partner_config_repository,
):
    return DidManagementService(
        did_repository=mock_did_repository,
        logger=mock_logger,
        datetime_util=mock_datetime_util,
        validator=mock_validator,
        partner_config_repository=mock_partner_config_repository,
    )


def _make_svc(logger=None, datetime_util=None):
    logger = logger or Mock(spec=HollerServiceLogger)
    dt = datetime_util or Mock(spec=DateTimeUtil)
    dt.get_current_time.return_value = 1_234_567_890
    svc = DidManagementService(
        did_repository=AsyncMock(spec=DidRepository),
        logger=logger,
        datetime_util=dt,
        validator=Mock(spec=DidValidator),
        partner_config_repository=AsyncMock(spec=PartnerConfigRepository),
    )
    return svc, logger, dt


class TestAssignDid:

    @pytest.mark.asyncio
    async def test_assign_did_success(
        self,
        did_management_service,
        mock_did_repository,
        mock_logger,
        mock_datetime_util,
        mock_validator,
    ):
        did_number = "12345"
        partner_id = 1
        vendor_id = "507f1f77bcf86cd799439011"
        vendor_config_id = "507f1f77bcf86cd799439012"
        service_board_id = 100
        agent_id = 200

        vendor_id_obj = ObjectId(vendor_id)
        vendor_config_id_obj = ObjectId(vendor_config_id)
        ts = mock_datetime_util.get_current_time.return_value

        expected_did_data = {
            "service_board_id": service_board_id,
            "did_number": did_number,
            "partner_id": partner_id,
            "vendor_id": vendor_id_obj,
            "vendor_config_id": vendor_config_id_obj,
            "agent_id": agent_id,
            "assign_date": ts,
            "mapped_date": ts,
        }

        mock_validator.validate_did_assignment = AsyncMock(return_value=None)

        mock_did_repository.find_did_attendance = AsyncMock(return_value=None)
        mock_did_repository.insert_did_default_attendance = AsyncMock(
            return_value={
                **expected_did_data,
                "created_at": ANY,
                "updated_at": ANY,
                "status": DIDStatus.AVAILABLE.value,
                "status_changed_at": ANY,
                "cooldown_until": None,
                "spam_count": 0,
                "last_spam_detected_at": None,
                "is_active": True,
            }
        )

        mock_did_repository.insert_did_history = AsyncMock(return_value=None)

        await did_management_service.assign_did(
            service_board_id=service_board_id,
            did_number=did_number,
            partner_id=partner_id,
            vendor_id=vendor_id,
            vendor_config_id=vendor_config_id,
            agent_id=agent_id,
        )

        mock_validator.validate_did_assignment.assert_awaited_once()
        mock_validator.validate_did_assignment.assert_any_await(ANY)

        called_with = mock_validator.validate_did_assignment.await_args[0][0]
        assert called_with["did_number"] == did_number
        assert called_with["partner_id"] == partner_id
        assert called_with["vendor_id"] == vendor_id_obj
        assert called_with["vendor_config_id"] == vendor_config_id_obj
        assert called_with["service_board_id"] == service_board_id
        assert called_with["agent_id"] == agent_id
        assert called_with["assign_date"] == ts
        assert called_with["mapped_date"] == ts

        mock_did_repository.insert_did_default_attendance.assert_awaited_once()
        mock_did_repository.insert_did_history.assert_awaited_once()

        mock_logger.info.assert_any_call(f"DID {did_number} assigned successfully")
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_assign_did_already_exists(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        did_number = "12345"
        partner_id = 1
        vendor_id = "507f1f77bcf86cd799439011"
        vendor_config_id = "507f1f77bcf86cd799439012"
        existing = {
            "did_number": did_number,
            "partner_id": partner_id,
            "vendor_id": ObjectId(vendor_id),
        }
        mock_did_repository.find_did_attendance = AsyncMock(return_value=existing)

        with pytest.raises(ValueError, match="DID already exists"):
            await did_management_service.assign_did(
                100, did_number, partner_id, vendor_id, vendor_config_id
            )

        mock_logger.info.assert_any_call(
            "DID {} already assigned for vendor {} and partner {}".format(
                did_number, vendor_id, partner_id
            )
        )

    @pytest.mark.asyncio
    async def test_assign_did_failure(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        did_number = "12345"
        partner_id = 1
        vendor_id = "507f1f77bcf86cd799439011"
        vendor_config_id = "507f1f77bcf86cd799439012"
        mock_did_repository.find_did_attendance = AsyncMock(return_value=None)
        mock_did_repository.insert_did_default_attendance = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(Exception, match="Database error"):
            await did_management_service.assign_did(
                100, did_number, partner_id, vendor_id, vendor_config_id
            )

        mock_logger.error.assert_called_with(
            "Failed to assign DID {}: Database error".format(did_number)
        )


class TestUnassignDid:

    @pytest.mark.asyncio
    async def test_unassign_did_success(
        self,
        did_management_service,
        mock_did_repository,
        mock_logger,
        mock_datetime_util,
    ):
        did_number = "12345"
        partner_id = 1
        ts = mock_datetime_util.get_current_time.return_value
        mock_did_repository.find_did_attendance = AsyncMock(
            return_value={"did_number": did_number, "partner_id": partner_id}
        )
        mock_did_repository.delete_did_default_attendance = AsyncMock(return_value=True)
        updated = {
            "did_number": did_number,
            "partner_id": partner_id,
            "unassign_date": ts,
        }
        mock_did_repository.update_did_history = AsyncMock(return_value=updated)

        result = await did_management_service.unassign_did(did_number, partner_id)

        mock_did_repository.find_did_attendance.assert_awaited_with(
            did_number, partner_id
        )
        mock_did_repository.delete_did_default_attendance.assert_awaited_with(
            did_number, partner_id
        )
        mock_did_repository.update_did_history.assert_awaited_with(
            did_number, partner_id, {"unassign_date": ts}
        )
        assert result == updated
        mock_logger.info.assert_any_call(
            "Starting unassign_did with did_number: {}, partner_id: {}".format(
                did_number, partner_id
            )
        )
        mock_logger.info.assert_any_call(
            "DID {} unassigned successfully".format(did_number)
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_unassign_did_not_found(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        did_number = "12345"
        partner_id = 1
        mock_did_repository.find_did_attendance = AsyncMock(return_value=None)

        with pytest.raises(ResourceNotFound, match="DID attendance not found"):
            await did_management_service.unassign_did(did_number, partner_id)

        mock_logger.error.assert_called_with(
            "Failed to unassign DID {}: DID attendance not found".format(did_number)
        )

    @pytest.mark.asyncio
    async def test_unassign_did_failure(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        did_number = "12345"
        partner_id = 1
        mock_did_repository.find_did_attendance = AsyncMock(
            return_value={"did_number": did_number, "partner_id": partner_id}
        )
        mock_did_repository.delete_did_default_attendance = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(Exception, match="Database error"):
            await did_management_service.unassign_did(did_number, partner_id)

        mock_logger.error.assert_called_with(
            "Failed to unassign DID {}: Database error".format(did_number)
        )


class TestUpdateDidStatus:

    @pytest.mark.asyncio
    async def test_update_did_status_success(self, did_management_service, mock_logger):
        vendor_id = ObjectId()
        did_management_service.assign_did = AsyncMock(return_value={})
        did_management_service.unassign_did = AsyncMock(return_value={})

        await did_management_service.update_did_status(
            vendor_id, ["12345"], ["67890"], ["54321"], ["98765"], 1_631_234_567_890
        )

        did_management_service.assign_did.assert_awaited_once_with(
            0, "98765", 1, str(vendor_id)
        )
        did_management_service.unassign_did.assert_awaited_once_with("54321", 1)
        mock_logger.info.assert_any_call(
            "Starting update_did_status for vendor_id: {}".format(vendor_id)
        )
        mock_logger.info.assert_any_call(
            "DID status updated successfully for vendor {}".format(vendor_id)
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_did_status_failure(self, did_management_service, mock_logger):
        vendor_id = ObjectId()
        did_management_service.assign_did = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(Exception, match="Database error"):
            await did_management_service.update_did_status(
                vendor_id, [], [], [], ["98765"], 1_631_234_567_890
            )

        mock_logger.error.assert_called_with(
            "Failed to update DID status for vendor {}: Database error".format(
                vendor_id
            )
        )


class TestGetDids:

    @pytest.mark.asyncio
    async def test_get_assigned_dids_success(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        vendor_id = ObjectId()
        mock_did_repository.get_assigned_dids = AsyncMock(return_value=["12345"])
        result = await did_management_service.get_assigned_dids(vendor_id)
        mock_did_repository.get_assigned_dids.assert_awaited_with(vendor_id)
        assert result == ["12345"]
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_assigned_dids_failure(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        """Covers lines 235-241."""
        vendor_id = ObjectId()
        mock_did_repository.get_assigned_dids = AsyncMock(
            side_effect=Exception("DB error")
        )

        with pytest.raises(Exception, match="DB error"):
            await did_management_service.get_assigned_dids(vendor_id)

        mock_logger.error.assert_called_with(
            "Failed to retrieve assigned DIDs for vendor {}: DB error".format(vendor_id)
        )

    @pytest.mark.asyncio
    async def test_get_available_dids_success(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        vendor_id = ObjectId()
        mock_did_repository.get_available_dids = AsyncMock(return_value=["12345"])
        result = await did_management_service.get_available_dids(vendor_id)
        mock_did_repository.get_available_dids.assert_awaited_with(vendor_id, None)
        assert result == ["12345"]
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_available_dids_failure(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        """Covers lines 263-269."""
        vendor_id = ObjectId()
        mock_did_repository.get_available_dids = AsyncMock(
            side_effect=Exception("DB error")
        )

        with pytest.raises(Exception, match="DB error"):
            await did_management_service.get_available_dids(vendor_id)

        mock_logger.error.assert_called_with(
            "Failed to retrieve available DIDs for vendor {}: DB error".format(
                vendor_id
            )
        )


class TestUpdateDid:

    _did = "12345"
    _vid = "507f1f77bcf86cd799439011"
    _vcid = "507f1f77bcf86cd799439012"

    @pytest.mark.asyncio
    async def test_update_did_success(
        self,
        did_management_service,
        mock_did_repository,
        mock_logger,
        mock_datetime_util,
    ):
        """
        FIX A: the service logs:
          "Starting update_did for did_number: {}, partner_id: {}, vendor_id: {}, ..."
        not "Updating DID … for partner … and vendor …".

        existing_did.partner_id=None triggers partner_id + assign_date insertion.
        update_data is non-empty so updated_at is added. status=MAPPED always appended.
        """
        did_number = self._did
        vendor_id = self._vid
        vendor_id_obj = ObjectId(vendor_id)
        vendor_config_id_obj = ObjectId(self._vcid)
        partner_id = 1
        service_board_id = 100
        agent_id = 200
        ts = mock_datetime_util.get_current_time.return_value

        existing_did = {
            "did_number": did_number,
            "vendor_id": vendor_id_obj,
            "partner_id": None,
            "assign_date": None,
            "service_board_id": None,
            "agent_id": None,
        }
        expected_update_data = {
            "service_board_id": service_board_id,
            "agent_id": agent_id,
            "mapped_date": ts,
            "partner_id": partner_id,
            "assign_date": ts,
            "updated_at": ts,
            "status": DIDStatus.MAPPED.value,
        }
        updated_did = {**existing_did, **expected_update_data}
        history_data = {
            "did_number": did_number,
            "partner_id": partner_id,
            "vendor_id": vendor_id_obj,
            "vendor_config_id": vendor_config_id_obj,
            "agent_id": agent_id,
            "assign_date": ANY,
            "service_board_id": service_board_id,
            "created_at": ANY,
            "updated_at": ANY,
            "unassign_date": None,
        }
        mock_did_repository.find_did_by_did_number_and_vendor_id = AsyncMock(
            return_value=existing_did
        )
        mock_did_repository.update_did_attendance = AsyncMock(return_value=updated_did)
        mock_did_repository.insert_did_history = AsyncMock(return_value=None)

        result = await did_management_service.update_did(
            did_number,
            vendor_id,
            partner_id,
            service_board_id,
            agent_id,
            vendor_config_id=vendor_config_id_obj,
        )

        mock_did_repository.update_did_attendance.assert_awaited_with(
            did_number, partner_id, expected_update_data
        )
        mock_did_repository.insert_did_history.assert_awaited_with(history_data)
        assert result == updated_did
        mock_logger.info.assert_any_call(
            "Starting update_did for did_number: {}, partner_id: {}, vendor_id: {}, "
            "service_board_id: {}, agent_id: {}".format(
                did_number, partner_id, vendor_id, service_board_id, agent_id
            )
        )
        mock_logger.info.assert_any_call(
            "DID {} updated successfully".format(did_number)
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_did_not_found(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        did_number = self._did
        vendor_id = self._vid
        mock_did_repository.find_did_by_did_number_and_vendor_id = AsyncMock(
            return_value=None
        )

        with pytest.raises(ResourceNotFound):
            await did_management_service.update_did(did_number, vendor_id, 1)

        mock_logger.error.assert_called_with(
            "Failed to update DID {}: DID {} not found for the specified vendor".format(
                did_number, did_number
            )
        )

    @pytest.mark.asyncio
    async def test_update_did_no_updates(
        self,
        did_management_service,
        mock_did_repository,
        mock_logger,
        mock_datetime_util,
    ):
        did_number = self._did
        vendor_id = self._vid
        vendor_id_obj = ObjectId(vendor_id)
        vendor_config_id_obj = ObjectId(self._vcid)
        partner_id = 1
        ts = mock_datetime_util.get_current_time.return_value

        existing_did = {
            "did_number": did_number,
            "vendor_id": vendor_id_obj,
            "partner_id": partner_id,
            "assign_date": ts,
            "service_board_id": None,
            "agent_id": None,
        }
        expected_update_data = {"status": DIDStatus.MAPPED.value}
        updated_did = {**existing_did, **expected_update_data}

        mock_did_repository.find_did_by_did_number_and_vendor_id = AsyncMock(
            return_value=existing_did
        )
        mock_did_repository.update_did_attendance = AsyncMock(return_value=updated_did)
        mock_did_repository.insert_did_history = AsyncMock(return_value=None)

        result = await did_management_service.update_did(
            did_number,
            vendor_id,
            partner_id,
            vendor_config_id=vendor_config_id_obj,
        )

        mock_did_repository.update_did_attendance.assert_awaited_with(
            did_number, partner_id, expected_update_data
        )
        assert result == updated_did
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_did_no_updates_empty_update_data(
        self,
        did_management_service,
        mock_did_repository,
        mock_logger,
        mock_datetime_util,
    ):
        did_number = self._did
        vendor_id = self._vid
        vendor_id_obj = ObjectId(vendor_id)
        vendor_config_id_obj = ObjectId(self._vcid)
        partner_id = 1
        ts = mock_datetime_util.get_current_time.return_value

        existing_did = {
            "did_number": did_number,
            "vendor_id": vendor_id_obj,
            "partner_id": partner_id,
            "assign_date": ts,
            "updated_at": ts,
            "service_board_id": None,
            "agent_id": None,
        }
        expected_update_data = {"status": DIDStatus.MAPPED.value}
        updated_did = {**existing_did, **expected_update_data}

        mock_did_repository.find_did_by_did_number_and_vendor_id = AsyncMock(
            return_value=existing_did
        )
        mock_did_repository.update_did_attendance = AsyncMock(return_value=updated_did)
        mock_did_repository.insert_did_history = AsyncMock(return_value=None)

        result = await did_management_service.update_did(
            did_number,
            vendor_id,
            partner_id,
            vendor_config_id=vendor_config_id_obj,
        )

        mock_did_repository.update_did_attendance.assert_awaited_with(
            did_number, partner_id, expected_update_data
        )
        assert result == updated_did
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_did_failed_update(
        self,
        did_management_service,
        mock_did_repository,
        mock_logger,
        mock_datetime_util,
    ):
        did_number = self._did
        vendor_id = self._vid
        vendor_id_obj = ObjectId(vendor_id)
        partner_id = 1
        service_board_id = 100
        ts = mock_datetime_util.get_current_time.return_value

        existing_did = {
            "did_number": did_number,
            "vendor_id": vendor_id_obj,
            "partner_id": partner_id,
            "assign_date": ts,
            "service_board_id": None,
            "agent_id": None,
        }
        expected_update_data = {
            "service_board_id": service_board_id,
            "updated_at": ts,
            "status": DIDStatus.MAPPED.value,
        }
        mock_did_repository.find_did_by_did_number_and_vendor_id = AsyncMock(
            return_value=existing_did
        )
        mock_did_repository.update_did_attendance = AsyncMock(return_value=None)

        with pytest.raises(
            ResourceNotFound, match="Failed to update DID {}".format(did_number)
        ):
            await did_management_service.update_did(
                did_number, vendor_id, partner_id, service_board_id=service_board_id
            )

        mock_did_repository.update_did_attendance.assert_awaited_with(
            did_number, partner_id, expected_update_data
        )
        mock_logger.error.assert_called_with(
            "Failed to update DID {}: Failed to update DID {}".format(
                did_number, did_number
            )
        )

    @pytest.mark.asyncio
    async def test_update_did_failure(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        did_number = self._did
        vendor_id = self._vid
        vendor_id_obj = ObjectId(vendor_id)
        existing_did = {
            "did_number": did_number,
            "vendor_id": vendor_id_obj,
            "partner_id": 1,
            "assign_date": None,
            "service_board_id": None,
            "agent_id": None,
        }
        mock_did_repository.find_did_by_did_number_and_vendor_id = AsyncMock(
            return_value=existing_did
        )
        mock_did_repository.update_did_attendance = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(Exception, match="Database error"):
            await did_management_service.update_did(did_number, vendor_id, 1)

        mock_logger.error.assert_called_with(
            "Failed to update DID {}: Database error".format(did_number)
        )


class TestGetDidsByPartner:

    _vid = "507f1f77bcf86cd799439011"

    @pytest.mark.asyncio
    async def test_get_dids_by_partner_and_vendor_success(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        mock_did_repository.get_dids_by_partner_and_vendor = AsyncMock(
            return_value=["12345"]
        )
        result = await did_management_service.get_dids_by_partner_and_vendor(
            1, self._vid
        )
        mock_did_repository.get_dids_by_partner_and_vendor.assert_awaited_with(
            1, ObjectId(self._vid)
        )
        assert result == ["12345"]
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_dids_by_partner_and_vendor_failure(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        """Covers lines 422-428."""
        mock_did_repository.get_dids_by_partner_and_vendor = AsyncMock(
            side_effect=Exception("DB error")
        )
        with pytest.raises(Exception, match="DB error"):
            await did_management_service.get_dids_by_partner_and_vendor(1, self._vid)
        mock_logger.error.assert_called_once()
        assert "DB error" in mock_logger.error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_dids_by_partner_service_board_success(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        mock_did_repository.get_dids_by_partner_service_board_and_vendor = AsyncMock(
            return_value=["12345"]
        )
        result = (
            await did_management_service.get_dids_by_partner_service_board_and_vendor(
                1, 100, self._vid
            )
        )
        mock_did_repository.get_dids_by_partner_service_board_and_vendor.assert_awaited_with(
            1, 100, ObjectId(self._vid)
        )
        assert result == ["12345"]

    @pytest.mark.asyncio
    async def test_get_dids_by_partner_service_board_failure(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        """Covers lines 456-462."""
        mock_did_repository.get_dids_by_partner_service_board_and_vendor = AsyncMock(
            side_effect=Exception("DB error")
        )
        with pytest.raises(Exception, match="DB error"):
            await did_management_service.get_dids_by_partner_service_board_and_vendor(
                1, 100, self._vid
            )
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_dids_by_partner_agent_service_board_success(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        mock_did_repository.get_dids_by_partner_agent_service_board_and_vendor = (
            AsyncMock(return_value=["12345"])
        )
        result = await did_management_service.get_dids_by_partner_agent_service_board_and_vendor(
            1, 200, 100, self._vid
        )
        mock_did_repository.get_dids_by_partner_agent_service_board_and_vendor.assert_awaited_with(
            1, 200, 100, ObjectId(self._vid)
        )
        assert result == ["12345"]

    @pytest.mark.asyncio
    async def test_get_dids_by_partner_agent_service_board_failure(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        """Covers lines 468-486."""
        mock_did_repository.get_dids_by_partner_agent_service_board_and_vendor = (
            AsyncMock(side_effect=Exception("DB error"))
        )
        with pytest.raises(Exception, match="DB error"):
            await did_management_service.get_dids_by_partner_agent_service_board_and_vendor(
                1, 200, 100, self._vid
            )
        mock_logger.error.assert_called_once()


class TestGetDidsByNumber:

    @pytest.mark.asyncio
    async def test_success(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        number = "+919876543210"
        doc = {"did_number": number}
        mock_did_repository.get_did_by_number = AsyncMock(return_value=doc)

        result = await did_management_service.get_dids_by_number(number)

        mock_did_repository.get_did_by_number.assert_awaited_once_with(number)
        assert result == doc
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        """Covers get_dids_by_number exception path."""
        number = "+919876543210"
        mock_did_repository.get_did_by_number = AsyncMock(
            side_effect=Exception("DB error")
        )

        with pytest.raises(Exception, match="DB error"):
            await did_management_service.get_dids_by_number(number)

        mock_logger.error.assert_called_with(
            "Failed to retrieve DIDs for call_to_number {}: DB error".format(number)
        )


@pytest.mark.asyncio
class TestGetDidsByServiceBoard:

    async def test_success(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        vendor_id = ObjectId()
        mock_did_repository.get_dids_by_service_board = AsyncMock(
            return_value=[
                {
                    "_id": ObjectId(),
                    "did_number": "12345",
                    "service_board_id": 123,
                    "vendor_id": vendor_id,
                    "partner_id": 1,
                    "agent_id": 42,
                }
            ]
        )
        result = await did_management_service.get_dids_by_service_board(123)
        assert len(result) == 1
        assert isinstance(result[0], Contract.DIDResponse)
        assert result[0].did_number == "12345"
        assert isinstance(result[0].vendor_id, str)
        mock_logger.error.assert_not_called()

    async def test_empty(self, did_management_service, mock_did_repository):
        mock_did_repository.get_dids_by_service_board = AsyncMock(return_value=[])
        assert await did_management_service.get_dids_by_service_board(999) == []

    async def test_exception(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        sb_id = 789
        mock_did_repository.get_dids_by_service_board = AsyncMock(
            side_effect=Exception("DB fail")
        )
        with pytest.raises(Exception, match="DB fail"):
            await did_management_service.get_dids_by_service_board(sb_id)
        mock_logger.error.assert_called_once()
        assert (
            "Error fetching DIDs for service board {}".format(sb_id)
            in mock_logger.error.call_args[0][0]
        )


class TestExtractSeriesKey:

    def test_exactly_10_digits(self, did_management_service, mock_logger):
        assert did_management_service.extract_series_key("9876543210") == "98"
        mock_logger.debug.assert_called_with("Length of did_number : 9876543210 is 10")

    def test_more_than_10_with_plus(self, did_management_service, mock_logger):
        did = "+919876543210"
        assert did_management_service.extract_series_key(did) == "98"
        mock_logger.debug.assert_called_with(
            "Length of did_number : {} is > 10 and it contains + in the starting".format(
                did
            )
        )

    def test_more_than_10_without_plus(self, did_management_service, mock_logger):
        did = "919876543210"
        assert did_management_service.extract_series_key(did) == "98"
        mock_logger.debug.assert_called_with(
            "Length of did_number : {} is > 10 and it does not contains + in the starting".format(
                did
            )
        )

    def test_short_number_fallback(self, did_management_service, mock_logger):
        assert did_management_service.extract_series_key("1234") == "34"
        mock_logger.debug.assert_called_with(
            "Returning to Fallback case in extract series key"
        )

    def test_very_short_fallback_empty(self, did_management_service, mock_logger):
        """Covers 604-607: fallback path returns empty string for len < 4."""
        assert did_management_service.extract_series_key("12") == ""
        mock_logger.debug.assert_called_with(
            "Returning to Fallback case in extract series key"
        )

    def test_plus_with_hyphen(self, did_management_service, mock_logger):
        did = "+91-9876543210"
        result = did_management_service.extract_series_key(did)
        assert result == "-9"


@pytest.mark.asyncio
class TestGetDidsAvailableForAssignment:

    async def test_success(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        vendor_id = ObjectId()
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": str(vendor_id)}
        )
        did_management_service.get_available_dids = AsyncMock(
            return_value=["12345", "67890"]
        )
        mock_did_repository.get_details_by_dids = AsyncMock(
            return_value=[
                {"did_number": "12345", "instance_id": "inst1"},
                {"did_number": "67890", "instance_id": "inst2"},
            ]
        )
        did_management_service._DidManagementService__did_repository = (
            mock_did_repository
        )

        result = await did_management_service.get_dids_available_for_assignment(1)

        assert isinstance(result, list) and len(result) > 0
        for sr in result:
            assert isinstance(sr, Contract.DIDSeriesResponse)
            assert sr.count == len(sr.dids)
        mock_logger.info.assert_any_call(
            "Successfully grouped and retrieved DIDs for partner_id: 1"
        )

    async def test_no_dids(self, did_management_service):
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": str(ObjectId())}
        )
        did_management_service.get_available_dids = AsyncMock(return_value=[])
        assert await did_management_service.get_dids_available_for_assignment(2) == []

    async def test_no_partner_config_raises(self, did_management_service, mock_logger):
        """Covers 604-607: ValueError re-raised with correct log."""
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value=None
        )
        with pytest.raises(ValueError, match=PARTNER_CONFIG_NOT_FOUND):
            await did_management_service.get_dids_available_for_assignment(99)

        mock_logger.error.assert_any_call(
            "Error in retrieving free DIDs: PartnerConfig not found: {}".format(
                PARTNER_CONFIG_NOT_FOUND
            )
        )

    async def test_repo_exception(self, did_management_service, mock_logger):
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            side_effect=Exception("DB failure")
        )
        with pytest.raises(Exception, match="DB failure"):
            await did_management_service.get_dids_available_for_assignment(4)
        mock_logger.error.assert_called_once()


@pytest.mark.asyncio
class TestAssignDidsAvailableForAssignment:

    _vid = "507f1f77bcf86cd799439011"

    def _config(self, *, rr=False, sb=False, am=False):
        return {
            "vendor_id": self._vid,
            "vendor_config_id": str(ObjectId()),
            "enable_round_robin": rr,
            "enable_service_board": sb,
            "enable_agent_mapping": am,
        }

    async def test_round_robin_success(self, did_management_service, mock_logger):
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value=self._config(rr=True)
        )
        did_management_service.update_did = AsyncMock()
        data = Contract.AssignDIDToPartner(dids_for_round_robin=["123", "456"])

        result = await did_management_service.assign_dids_available_for_assignment(
            1, data
        )

        assert result == {"message": "Successfully assigned DIDs to the Partner"}
        assert did_management_service.update_did.await_count == 2
        mock_logger.info.assert_any_call(
            "Successfully grouped and assigned DIDs for partner_id: 1"
        )

    async def test_service_board_success(self, did_management_service):
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value=self._config(sb=True)
        )
        did_management_service.update_did = AsyncMock()
        data = Contract.AssignDIDToPartner(
            dids_for_service_board=[
                Contract.ServiceBoardDIDMapping(
                    service_board_id=100, did_numbers=["123", "456"]
                )
            ]
        )
        result = await did_management_service.assign_dids_available_for_assignment(
            2, data
        )
        assert result == {"message": "Successfully assigned DIDs to the Partner"}
        assert did_management_service.update_did.await_count == 2

    async def test_agent_mapping_success(self, did_management_service):
        vcid = str(ObjectId())
        cfg = {**self._config(am=True), "vendor_config_id": vcid}
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value=cfg
        )
        did_management_service.update_did = AsyncMock()
        data = Contract.AssignDIDToPartner(
            dids_for_agent_mapping=[{"agent_id": "1", "did_number": "123"}]
        )

        result = await did_management_service.assign_dids_available_for_assignment(
            3, data
        )

        assert result == {"message": "Successfully assigned DIDs to the Partner"}
        did_management_service.update_did.assert_awaited_once_with(
            did_number="123",
            vendor_id=self._vid,
            partner_id=3,
            service_board_id=None,
            agent_id=1,
            vendor_config_id=ObjectId(vcid),
        )

    async def test_no_criteria_returns_bad_request(self, did_management_service):
        """Covers lines 514, 516 — all enable_* False → returns BadRequestResponse."""
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value=self._config()
        )
        result = await did_management_service.assign_dids_available_for_assignment(
            1, Contract.AssignDIDToPartner()
        )
        assert isinstance(result, BadRequestResponse)

    async def test_missing_partner_config(self, did_management_service, mock_logger):
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value=None
        )
        with pytest.raises(ValueError, match=PARTNER_CONFIG_NOT_FOUND):
            await did_management_service.assign_dids_available_for_assignment(
                4, Contract.AssignDIDToPartner(dids_for_round_robin=["123"])
            )
        mock_logger.error.assert_called_with(
            "PartnerConfig not found: No partner config available"
        )

    async def test_round_robin_empty_dids_raises(self, did_management_service):
        """Covers 780: _assign_round_robin raises TypeError (BadRequestResponse not BaseException)."""
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value=self._config(rr=True)
        )
        with pytest.raises(Exception):
            await did_management_service.assign_dids_available_for_assignment(
                5, Contract.AssignDIDToPartner(dids_for_round_robin=[])
            )

    async def test_service_board_empty_dids_raises(self, did_management_service):
        """Service-board empty list path."""
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value=self._config(sb=True)
        )
        with pytest.raises(Exception):
            await did_management_service.assign_dids_available_for_assignment(
                5, Contract.AssignDIDToPartner(dids_for_service_board=[])
            )

    async def test_agent_mapping_empty_dids_raises(self, did_management_service):
        """Covers 804: agent mapping empty list."""
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value=self._config(am=True)
        )
        with pytest.raises(Exception):
            await did_management_service.assign_dids_available_for_assignment(
                5, Contract.AssignDIDToPartner(dids_for_agent_mapping=[])
            )

    async def test_repo_exception(self, did_management_service, mock_logger):
        did_management_service._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            side_effect=Exception("DB error")
        )
        with pytest.raises(Exception, match="DB error"):
            await did_management_service.assign_dids_available_for_assignment(
                6, Contract.AssignDIDToPartner(dids_for_round_robin=["123"])
            )
        mock_logger.error.assert_called_once()


@pytest.mark.asyncio
class TestUnassignDidsForPartner:

    async def test_success(self):
        svc, logger, dt = _make_svc()
        svc._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": "507f1f77bcf86cd799439011"}
        )
        svc._DidManagementService__did_repository.unassign_did_to_partner = AsyncMock(
            return_value=True
        )
        svc._DidManagementService__did_repository.update_did_history = AsyncMock(
            return_value={}
        )

        result = await svc.unassign_dids_for_partner(1, ["12345", "67890"])

        assert result == {"message": "Successfully unassigned DIDs to the Partner"}
        logger.info.assert_any_call(
            "Unassign DID Numbers(Service)=> Received partner_id: 1"
        )
        logger.info.assert_any_call(
            "Unassign DID Numbers(Service)=> Successfully unassigned DIDs for partner_id: 1"
        )
        for did in ["12345", "67890"]:
            svc._DidManagementService__did_repository.unassign_did_to_partner.assert_any_await(
                did, 1
            )
            svc._DidManagementService__did_repository.update_did_history.assert_any_await(
                did, 1, {"unassign_date": 1_234_567_890}
            )

    async def test_missing_partner_config(self):
        svc, logger, _ = _make_svc()
        svc._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value=None
        )
        with pytest.raises(ValueError, match=PARTNER_CONFIG_NOT_FOUND):
            await svc.unassign_dids_for_partner(1, ["12345"])
        logger.error.assert_called_with(
            "Error in unassigning DIDs: PartnerConfig not found: {}".format(
                PARTNER_CONFIG_NOT_FOUND
            )
        )

    async def test_repo_exception_mid_loop(self):
        """Covers line 731 — exception raised inside the DID loop."""
        svc, logger, _ = _make_svc()
        svc._DidManagementService__partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": "507f1f77bcf86cd799439011"}
        )
        svc._DidManagementService__did_repository.unassign_did_to_partner = AsyncMock(
            side_effect=Exception("DB error")
        )
        with pytest.raises(Exception, match="DB error"):
            await svc.unassign_dids_for_partner(1, ["12345"])
        logger.error.assert_called_once()


@pytest.mark.asyncio
class TestApplyDidStatusUpdate:

    def _doc(self, status=None):
        return {
            "did_number": "12345",
            "status": status or DIDStatus.AVAILABLE.value,
            "partner_id": 1,
        }

    @pytest.mark.asyncio
    async def test_set_available(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        doc = {
            "did_number": "12345",
            "status": DIDStatus.MAPPED.value,
            "partner_id": 1,
        }
        updated_doc = {**doc, "status": DIDStatus.AVAILABLE.value}

        mock_did_repository.get_did_by_number = AsyncMock(return_value=doc)
        mock_did_repository.update_did_status = AsyncMock(return_value=updated_doc)

        payload = Contract.AdminDIDAction(action="set_available", did_numbers=["12345"])
        result = await did_management_service.apply_did_status_update(1, payload)

        assert result["summary"]["total"] == 1
        assert result["summary"]["succeeded"] == 1
        assert result["summary"]["failed"] == 0
        assert result["results"][0]["success"] is True
        assert result["results"][0]["status"] == "updated"
        mock_did_repository.update_did_status.assert_awaited_once()
        mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_mapped(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        doc = {
            "did_number": "12345",
            "status": DIDStatus.AVAILABLE.value,
            "partner_id": 1,
        }
        updated_doc = {**doc, "status": DIDStatus.MAPPED.value}

        mock_did_repository.get_did_by_number = AsyncMock(return_value=doc)
        mock_did_repository.update_did_status = AsyncMock(return_value=updated_doc)

        payload = Contract.AdminDIDAction(action="set_mapped", did_numbers=["12345"])
        result = await did_management_service.apply_did_status_update(1, payload)

        assert result["summary"]["total"] == 1
        assert result["summary"]["succeeded"] == 1
        assert result["summary"]["failed"] == 0
        assert result["results"][0]["success"] is True
        assert result["results"][0]["status"] == "updated"
        mock_did_repository.update_did_status.assert_awaited_once()
        mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_spammed(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        doc = {
            "did_number": "12345",
            "status": DIDStatus.MAPPED.value,
            "partner_id": 1,
        }

        mock_did_repository.get_did_by_number = AsyncMock(return_value=doc)
        mock_did_repository.update_did_status = AsyncMock(return_value=doc)
        mock_did_repository.increment_spam_count = AsyncMock(return_value=True)

        payload = Contract.AdminDIDAction(
            action="mark_cooling_period", did_numbers=["12345"]
        )
        result = await did_management_service.apply_did_status_update(1, payload)

        assert result["summary"]["total"] == 1
        assert result["summary"]["succeeded"] == 1
        assert result["summary"]["failed"] == 0
        assert result["results"][0]["success"] is True
        assert result["results"][0]["status"] == "updated"
        mock_did_repository.update_did_status.assert_awaited_once()
        mock_did_repository.increment_spam_count.assert_awaited_once_with("12345")

    async def test_did_not_found(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        mock_did_repository.get_did_by_number = AsyncMock(return_value=None)

        payload = Contract.AdminDIDAction(action="set_available", did_numbers=["99999"])
        result = await did_management_service.apply_did_status_update(1, payload)

        assert result["summary"]["total"] == 1
        assert result["summary"]["succeeded"] == 0
        assert result["summary"]["failed"] == 1
        assert result["results"][0]["success"] is False
        assert result["results"][0]["status"] == "skipped"
        assert result["results"][0]["error"]["code"] == "DID_NOT_FOUND"
        mock_did_repository.update_did_status.assert_not_called()
        mock_logger.warning.assert_any_call(
            "Validation failed for DID {}: {}".format("99999", result["results"][0])
        )

    async def test_cooling_period_blocked(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        mock_did_repository.get_did_by_number = AsyncMock(
            return_value=self._doc(DIDStatus.COOLING_PERIOD.value)
        )

        payload = Contract.AdminDIDAction(action="set_mapped", did_numbers=["12345"])
        result = await did_management_service.apply_did_status_update(1, payload)

        assert result["summary"]["total"] == 1
        assert result["summary"]["succeeded"] == 0
        assert result["summary"]["failed"] == 1
        assert result["results"][0]["success"] is False
        assert result["results"][0]["status"] == "skipped"
        assert result["results"][0]["error"]["code"] == "COOLING_PERIOD_ACTIVE"
        assert (
            result["results"][0]["error"]["message"]
            == "Cannot modify during active Cooling Period"
        )
        mock_did_repository.update_did_status.assert_not_called()
        mock_logger.warning.assert_any_call(
            "Validation failed for DID {}: {}".format("12345", result["results"][0])
        )

    @pytest.mark.asyncio
    async def test_invalid_action_rejected_by_validation(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        with pytest.raises(pydantic.ValidationError) as exc_info:
            Contract.AdminDIDAction(action="invalid_action", did_numbers=["12345"])

        err = exc_info.value.errors()[0]
        assert err["loc"] == ("action",)
        assert "literal_error" in err["type"]
        assert "set_available" in str(exc_info.value)
        assert "set_mapped" in str(exc_info.value)
        assert "mark_cooling_period" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_with_service_board_id(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        doc = {
            "did_number": "12345",
            "status": DIDStatus.AVAILABLE.value,
            "partner_id": 1,
        }
        updated_doc = {**doc, "status": DIDStatus.MAPPED.value, "service_board_id": 100}

        mock_did_repository.get_did_by_number = AsyncMock(return_value=doc)
        mock_did_repository.update_did_status = AsyncMock(return_value=updated_doc)

        payload = Contract.AdminDIDAction(
            action="set_mapped", did_numbers=["12345"], service_board_id=100
        )
        result = await did_management_service.apply_did_status_update(1, payload)

        assert result["summary"]["total"] == 1
        assert result["summary"]["succeeded"] == 1
        assert result["summary"]["failed"] == 0
        assert result["results"][0]["success"] is True
        mock_did_repository.update_did_status.assert_awaited_once()

    async def test_multiple_dids_mixed(
        self, did_management_service, mock_did_repository
    ):
        """One found (available→mapped), one not found → mixed summary."""
        found_doc = {
            "did_number": "11111",
            "status": DIDStatus.AVAILABLE.value,  # valid status for set_mapped
            "partner_id": 1,
        }
        mock_did_repository.get_did_by_number = AsyncMock(side_effect=[found_doc, None])
        mock_did_repository.update_did_status = AsyncMock(
            return_value={**found_doc, "status": DIDStatus.MAPPED.value}
        )

        payload = Contract.AdminDIDAction(
            action="set_mapped", did_numbers=["11111", "22222"]
        )
        result = await did_management_service.apply_did_status_update(1, payload)

        assert result["summary"]["total"] == 2
        assert result["summary"]["succeeded"] == 1
        assert result["summary"]["failed"] == 1
        assert len(result["results"]) == 2

        success_results = [r for r in result["results"] if r["success"]]
        failed_results = [r for r in result["results"] if not r["success"]]
        assert len(success_results) == 1
        assert len(failed_results) == 1
        assert failed_results[0]["error"]["code"] == "DID_NOT_FOUND"

    async def test_handler_raises_value_error(
        self, did_management_service, mock_did_repository
    ):
        """ValueError from handler is caught, appended to results as error."""
        mock_did_repository.get_did_by_number = AsyncMock(
            return_value=self._doc("available")
        )
        mock_did_repository.update_did_status = AsyncMock(
            side_effect=ValueError("VALIDATION_ERROR|bad value")
        )

        payload = Contract.AdminDIDAction(action="set_available", did_numbers=["12345"])
        result = await did_management_service.apply_did_status_update(1, payload)

        assert result["summary"]["total"] == 1
        assert result["summary"]["succeeded"] == 0
        assert result["summary"]["failed"] == 1
        assert result["results"][0]["success"] is False
        assert result["results"][0]["status"] == "skipped"
        assert result["results"][0]["error"]["code"] == "INVALID_TRANSITION"

    async def test_all_dids_fail(self, did_management_service, mock_did_repository):
        """All DIDs in cooling period → summary shows all failed."""
        mock_did_repository.get_did_by_number = AsyncMock(
            side_effect=[
                self._doc(DIDStatus.COOLING_PERIOD.value),
                self._doc(DIDStatus.COOLING_PERIOD.value),
            ]
        )

        payload = Contract.AdminDIDAction(
            action="set_mapped", did_numbers=["11111", "22222"]
        )
        result = await did_management_service.apply_did_status_update(1, payload)

        assert result["summary"]["total"] == 2
        assert result["summary"]["succeeded"] == 0
        assert result["summary"]["failed"] == 2
        for r in result["results"]:
            assert r["success"] is False
            assert r["error"]["code"] == "COOLING_PERIOD_ACTIVE"

    async def test_error_result_structure(
        self, did_management_service, mock_did_repository
    ):
        """Verify full error result shape matches contract."""
        mock_did_repository.get_did_by_number = AsyncMock(return_value=None)

        payload = Contract.AdminDIDAction(action="set_available", did_numbers=["99999"])
        result = await did_management_service.apply_did_status_update(1, payload)

        error_result = result["results"][0]
        assert "did_number" in error_result
        assert "success" in error_result
        assert "status" in error_result
        assert "error" in error_result
        assert "code" in error_result["error"]
        assert "message" in error_result["error"]
        assert error_result["did_number"] == "99999"
        assert error_result["success"] is False
        assert error_result["status"] == "skipped"

    async def test_process_single_did_invalid_action_not_in_handlers(
        self, did_management_service, mock_did_repository
    ):
        """
        ACTION_HANDLERS cleared at runtime to simulate handler mismatch.
        """
        doc = {
            "did_number": "12345",
            "status": DIDStatus.AVAILABLE.value,
            "partner_id": 1,
        }
        mock_did_repository.get_did_by_number = AsyncMock(return_value=doc)

        payload = Contract.AdminDIDAction(action="set_available", did_numbers=["12345"])

        original_handlers = DidStatusUpdateHelper.ACTION_HANDLERS.copy()
        DidStatusUpdateHelper.ACTION_HANDLERS.clear()

        try:
            result = await did_management_service.apply_did_status_update(1, payload)
        finally:
            DidStatusUpdateHelper.ACTION_HANDLERS.update(original_handlers)

        assert result["summary"]["total"] == 1
        assert result["summary"]["failed"] == 1
        assert result["results"][0]["success"] is False
        assert result["results"][0]["error"]["code"] == "INVALID_ACTION"

    async def test_handler_raises_value_error_no_pipe(
        self, did_management_service, mock_did_repository
    ):
        """
        ValueError with no '|' separator → code defaults to VALIDATION_ERROR.
        """
        mock_did_repository.get_did_by_number = AsyncMock(
            return_value={
                "did_number": "12345",
                "status": DIDStatus.AVAILABLE.value,
                "partner_id": 1,
            }
        )
        mock_did_repository.update_did_status = AsyncMock(
            side_effect=ValueError("plain error no pipe")
        )

        payload = Contract.AdminDIDAction(action="set_available", did_numbers=["12345"])
        result = await did_management_service.apply_did_status_update(1, payload)

        assert result["summary"]["failed"] == 1
        assert result["results"][0]["error"]["code"] == "VALIDATION_ERROR"
        assert result["results"][0]["error"]["message"] == "plain error no pipe"

    async def test_mark_spammed_increment_returns_false(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        """
        increment_spam_count returns False → DID update still succeeds.
        """
        doc = {
            "did_number": "12345",
            "status": DIDStatus.MAPPED.value,
            "partner_id": 1,
        }
        mock_did_repository.get_did_by_number = AsyncMock(return_value=doc)
        mock_did_repository.update_did_status = AsyncMock(return_value=doc)
        mock_did_repository.increment_spam_count = AsyncMock(return_value=False)

        payload = Contract.AdminDIDAction(
            action="mark_cooling_period", did_numbers=["12345"]
        )
        result = await did_management_service.apply_did_status_update(1, payload)

        assert result["summary"]["total"] == 1
        assert result["summary"]["succeeded"] == 1
        assert result["results"][0]["success"] is True
        mock_did_repository.increment_spam_count.assert_awaited_once_with("12345")
        mock_logger.info.assert_any_call(
            "Incremented spam count for DID {}".format("12345")
        )


@pytest.mark.asyncio
class TestListDids:

    def _doc(self, did_number="12345", status="available", partner_id=1, **kw):
        base = {
            "did_number": did_number,
            "status": status,
            "partner_id": partner_id,
            "vendor_id": ObjectId(),
            "service_board_id": None,
            "agent_id": None,
            "spam_count": 0,
            "last_spam_detected_at": None,
            "cooldown_until": None,
            "status_changed_at": 0,
            "assign_date": None,
            "mapped_date": None,
        }
        base.update(kw)
        return base

    async def test_basic_success(
        self, did_management_service, mock_did_repository, mock_logger
    ):
        docs = [self._doc()]
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=(docs, 1))

        result = await did_management_service.list_dids(partner_id=1)

        assert result == {
            "total": 1,
            "page": 1,
            "limit": 20,
            "dids": [result["dids"][0]],
        }
        assert result["dids"][0]["did_number"] == "12345"
        assert isinstance(result["dids"][0]["vendor_id"], str)
        mock_logger.error.assert_not_called()

    async def test_strips_mongo_id(self, did_management_service, mock_did_repository):
        doc = self._doc()
        doc["_id"] = ObjectId()
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=([doc], 1))

        result = await did_management_service.list_dids(partner_id=1)
        assert "_id" not in result["dids"][0]

    async def test_missing_partner_id_raises(self, did_management_service, mock_logger):
        with pytest.raises(ValueError, match="partner_id is required"):
            await did_management_service.list_dids(partner_id=None)
        mock_logger.error.assert_called_once_with(
            "partner_id is required for listing DIDs"
        )

    async def test_invalid_status_raises(self, did_management_service):
        with pytest.raises(ValueError, match="Invalid status filter"):
            await did_management_service.list_dids(partner_id=1, status="garbage")

    async def test_status_alias_available(
        self, did_management_service, mock_did_repository
    ):
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=([], 0))
        await did_management_service.list_dids(partner_id=1, status="available")
        kw = mock_did_repository.get_dids_by_partner.call_args[1]
        assert kw["status"] == DIDStatus.AVAILABLE.value

    async def test_status_alias_mapped(
        self, did_management_service, mock_did_repository
    ):
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=([], 0))
        await did_management_service.list_dids(partner_id=1, status="MAPPED")
        kw = mock_did_repository.get_dids_by_partner.call_args[1]
        assert kw["status"] == DIDStatus.MAPPED.value

    async def test_status_alias_cooling(
        self, did_management_service, mock_did_repository
    ):
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=([], 0))
        await did_management_service.list_dids(partner_id=1, status="cooling")
        kw = mock_did_repository.get_dids_by_partner.call_args[1]
        assert kw["status"] == DIDStatus.COOLING_PERIOD.value

    async def test_status_alias_cooling_period(
        self, did_management_service, mock_did_repository
    ):
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=([], 0))
        await did_management_service.list_dids(partner_id=1, status="cooling_period")
        kw = mock_did_repository.get_dids_by_partner.call_args[1]
        assert kw["status"] == DIDStatus.COOLING_PERIOD.value

    async def test_status_alias_cooldown(
        self, did_management_service, mock_did_repository
    ):
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=([], 0))
        await did_management_service.list_dids(partner_id=1, status="cooldown")
        kw = mock_did_repository.get_dids_by_partner.call_args[1]
        assert kw["status"] == DIDStatus.COOLDOWN_COMPLETED.value

    async def test_status_alias_cooldown_completed(
        self, did_management_service, mock_did_repository
    ):
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=([], 0))
        await did_management_service.list_dids(
            partner_id=1, status="cooldown_completed"
        )
        kw = mock_did_repository.get_dids_by_partner.call_args[1]
        assert kw["status"] == DIDStatus.COOLDOWN_COMPLETED.value

    async def test_pagination_forwarded(
        self, did_management_service, mock_did_repository
    ):
        docs = [
            self._doc(service_board_id=42, agent_id=7, spam_count=3, assign_date=100)
        ]
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=(docs, 50))

        result = await did_management_service.list_dids(partner_id=1, page=3, limit=10)

        assert result["page"] == 3
        assert result["limit"] == 10
        assert result["total"] == 50
        assert result["dids"][0]["service_board_id"] == 42
        assert result["dids"][0]["agent_id"] == 7
        assert result["dids"][0]["spam_count"] == 3
        mock_did_repository.get_dids_by_partner.assert_awaited_once_with(
            partner_id=1,
            service_board_id=None,
            status=None,
            did_number=None,
            offset=3,
            limit=10,
        )

    async def test_service_board_filter_forwarded(
        self, did_management_service, mock_did_repository
    ):
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=([], 0))
        result = await did_management_service.list_dids(
            partner_id=1, service_board_id=100
        )
        assert result["total"] == 0
        mock_did_repository.get_dids_by_partner.assert_awaited_once_with(
            partner_id=1,
            service_board_id=100,
            status=None,
            did_number=None,
            offset=1,
            limit=20,
        )

    async def test_empty_result(self, did_management_service, mock_did_repository):
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=([], 0))
        result = await did_management_service.list_dids(partner_id=1)
        assert result == {"total": 0, "page": 1, "limit": 20, "dids": []}

    async def test_objectid_vendor_id_stringified(
        self, did_management_service, mock_did_repository
    ):
        doc = self._doc()
        doc["vendor_id"] = ObjectId()
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=([doc], 1))
        result = await did_management_service.list_dids(partner_id=1)
        assert isinstance(result["dids"][0]["vendor_id"], str)

    async def test_all_optional_fields_preserved(
        self, did_management_service, mock_did_repository
    ):
        ts = 1_631_234_567_890
        doc = self._doc(
            service_board_id=10,
            agent_id=5,
            spam_count=2,
            last_spam_detected_at=ts,
            cooldown_until=ts,
            status_changed_at=ts,
            assign_date=ts,
            mapped_date=ts,
        )
        mock_did_repository.get_dids_by_partner = AsyncMock(return_value=([doc], 1))
        result = await did_management_service.list_dids(partner_id=1)
        d = result["dids"][0]
        assert d["service_board_id"] == 10
        assert d["agent_id"] == 5
        assert d["spam_count"] == 2
        assert d["last_spam_detected_at"] == ts
        assert d["cooldown_until"] == ts
        assert d["status_changed_at"] == ts
        assert d["assign_date"] == ts
        assert d["mapped_date"] == ts




class TestClaimDidForCampaign:
    """
    claim_did_for_campaign marks a partner-owned DID Mapped AND binds it to
    the campaign's own agent_bot_id — required because holler's own
    AI-bridge session resolution (_pre_create_session) reads agent_bot_id
    straight off the DID used to place the call, independent of
    context_data. Still safe for "multiple DIDs per campaign": it's
    many-DIDs-to-one-agent, never the reverse.
    """

    @pytest.mark.asyncio
    async def test_claims_available_did_and_binds_agent(self):
        svc, logger, _ = _make_svc()
        svc._DidManagementService__did_repository.find_did_attendance = AsyncMock(
            return_value={
                "did_number": "911111111111",
                "partner_id": 101,
                "did_type": "ai_agent",
                "status": DIDStatus.AVAILABLE.value,
                "agent_bot_id": 0,
            }
        )
        svc._DidManagementService__did_repository.update_did_values = AsyncMock(
            return_value={"did_number": "911111111111", "status": DIDStatus.MAPPED.value}
        )

        result = await svc.claim_did_for_campaign(
            partner_id=101, did_number="911111111111", agent_bot_id=56
        )

        assert result == {"did_number": "911111111111", "status": DIDStatus.MAPPED.value}
        svc._DidManagementService__did_repository.update_did_values.assert_awaited_once_with(
            did_number="911111111111",
            partner_id=101,
            update_data={"status": DIDStatus.MAPPED.value, "agent_bot_id": 56},
        )

    @pytest.mark.asyncio
    async def test_already_mapped_to_same_agent_is_idempotent_noop(self):
        svc, logger, _ = _make_svc()
        svc._DidManagementService__did_repository.find_did_attendance = AsyncMock(
            return_value={
                "did_number": "911111111111",
                "partner_id": 101,
                "did_type": "ai_agent",
                "status": DIDStatus.MAPPED.value,
                "agent_bot_id": 56,
            }
        )
        svc._DidManagementService__did_repository.update_did_values = AsyncMock()

        result = await svc.claim_did_for_campaign(
            partner_id=101, did_number="911111111111", agent_bot_id=56
        )

        assert result == {"did_number": "911111111111", "status": DIDStatus.MAPPED.value}
        svc._DidManagementService__did_repository.update_did_values.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_already_mapped_to_a_different_agent(self):
        """Someone else (a concurrent claim, or a genuine assign-ai-agent
        call) already has this DID — must not silently steal it."""
        svc, logger, _ = _make_svc()
        svc._DidManagementService__did_repository.find_did_attendance = AsyncMock(
            return_value={
                "did_number": "911111111111",
                "partner_id": 101,
                "did_type": "ai_agent",
                "status": DIDStatus.MAPPED.value,
                "agent_bot_id": 999,
            }
        )
        svc._DidManagementService__did_repository.update_did_values = AsyncMock()

        with pytest.raises(ValueError):
            await svc.claim_did_for_campaign(
                partner_id=101, did_number="911111111111", agent_bot_id=56
            )
        svc._DidManagementService__did_repository.update_did_values.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_did_not_found_for_partner(self):
        svc, logger, _ = _make_svc()
        svc._DidManagementService__did_repository.find_did_attendance = AsyncMock(
            return_value=None
        )

        with pytest.raises(ResourceNotFound):
            await svc.claim_did_for_campaign(
                partner_id=101, did_number="911111111111", agent_bot_id=56
            )

    @pytest.mark.asyncio
    async def test_raises_when_did_in_cooling_period(self):
        svc, logger, _ = _make_svc()
        svc._DidManagementService__did_repository.find_did_attendance = AsyncMock(
            return_value={
                "did_number": "911111111111",
                "partner_id": 101,
                "did_type": "ai_agent",
                "status": DIDStatus.COOLING_PERIOD.value,
                "agent_bot_id": 0,
            }
        )

        with pytest.raises(ValueError):
            await svc.claim_did_for_campaign(
                partner_id=101, did_number="911111111111", agent_bot_id=56
            )


class TestReleaseCampaignDid:
    """
    release_campaign_did reverts a campaign-claimed DID back to Available
    and clears agent_bot_id — used when a DID is removed from
    did_selection, or the campaign is deleted/stopped. Only acts if the DID
    is currently Mapped to exactly the given agent_bot_id — never a DID
    reassigned elsewhere in the meantime — and never resets partner_id
    (only assign_ai_agent_did / unassign_did do that).
    """

    @pytest.mark.asyncio
    async def test_releases_campaign_claimed_did_and_clears_agent(self):
        svc, logger, _ = _make_svc()
        svc._DidManagementService__did_repository.find_did_attendance = AsyncMock(
            return_value={
                "did_number": "911111111111",
                "partner_id": 101,
                "status": DIDStatus.MAPPED.value,
                "agent_bot_id": 56,
            }
        )
        svc._DidManagementService__did_repository.update_did_values = AsyncMock(
            return_value={
                "did_number": "911111111111",
                "status": DIDStatus.AVAILABLE.value,
            }
        )

        result = await svc.release_campaign_did(
            partner_id=101, did_number="911111111111", agent_bot_id=56
        )

        assert result == {"did_number": "911111111111", "status": DIDStatus.AVAILABLE.value}
        svc._DidManagementService__did_repository.update_did_values.assert_awaited_once_with(
            did_number="911111111111",
            partner_id=101,
            update_data={"status": DIDStatus.AVAILABLE.value, "agent_bot_id": 0},
        )

    @pytest.mark.asyncio
    async def test_does_not_release_when_bound_to_a_different_agent(self):
        """The DID was reassigned to a different agent_bot_id since this
        campaign claimed it — must not release someone else's binding."""
        svc, logger, _ = _make_svc()
        svc._DidManagementService__did_repository.find_did_attendance = AsyncMock(
            return_value={
                "did_number": "911111111111",
                "partner_id": 101,
                "status": DIDStatus.MAPPED.value,
                "agent_bot_id": 999,
            }
        )
        svc._DidManagementService__did_repository.update_did_values = AsyncMock()

        result = await svc.release_campaign_did(
            partner_id=101, did_number="911111111111", agent_bot_id=56
        )

        assert result == {"did_number": "911111111111", "status": DIDStatus.MAPPED.value}
        svc._DidManagementService__did_repository.update_did_values.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_already_available_is_noop(self):
        svc, logger, _ = _make_svc()
        svc._DidManagementService__did_repository.find_did_attendance = AsyncMock(
            return_value={
                "did_number": "911111111111",
                "partner_id": 101,
                "status": DIDStatus.AVAILABLE.value,
                "agent_bot_id": 0,
            }
        )
        svc._DidManagementService__did_repository.update_did_values = AsyncMock()

        result = await svc.release_campaign_did(
            partner_id=101, did_number="911111111111", agent_bot_id=56
        )

        assert result == {"did_number": "911111111111", "status": DIDStatus.AVAILABLE.value}
        svc._DidManagementService__did_repository.update_did_values.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_did_not_found_for_partner(self):
        svc, logger, _ = _make_svc()
        svc._DidManagementService__did_repository.find_did_attendance = AsyncMock(
            return_value=None
        )

        with pytest.raises(ResourceNotFound):
            await svc.release_campaign_did(
                partner_id=101, did_number="911111111111", agent_bot_id=56
            )
