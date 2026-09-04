from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.vendor.dto import Contract
from src.components.vendor.message import (
    VENDOR_ACTIVATED_SUCCESSFULLY,
    VENDOR_CREATED_SUCCESSFULLY,
    VENDOR_DEACTIVATED_SUCCESSFULLY,
)
from src.components.vendor.services import VendorService
from src.exceptions import ConflictError, ResourceNotFound
from src.utils.common_messages import VENDOR_NOT_FOUND


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def mock_logger():
    return MagicMock()


@pytest.fixture
def mock_datetime_util():
    mock = MagicMock()
    mock.get_current_time.return_value = 1234567890
    return mock


@pytest.fixture
def mock_validator():
    return AsyncMock()


@pytest.fixture
def vendor_service(mock_repo, mock_logger, mock_datetime_util, mock_validator):
    return VendorService(
        vendor_repo=mock_repo,
        logger=mock_logger,
        datetime_util=mock_datetime_util,
        validator=mock_validator,
    )


class TestVendorService:
    """Test suite for VendorService class"""

    @pytest.mark.asyncio
    async def test_create_vendor_success(
        self, vendor_service, mock_repo, mock_validator
    ):
        vendor_input = Contract.VendorCreate(name="Test Vendor", vendor_type="airtel")
        mock_repo.insert_vendor.return_value = ObjectId("64ab9fbfe7f4f5b4a10ebc88")

        result = await vendor_service.create_vendor(vendor_input)

        assert result.id == "64ab9fbfe7f4f5b4a10ebc88"
        assert result.message == VENDOR_CREATED_SUCCESSFULLY
        mock_validator.validate_vendor_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_vendor_failure_logs_error(self, vendor_service, mock_repo):
        vendor_input = Contract.VendorCreate(name="Vendor Error", vendor_type="airtel")
        mock_repo.insert_vendor.side_effect = Exception("DB Error")

        with pytest.raises(Exception):
            await vendor_service.create_vendor(vendor_input)

        vendor_service.logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_vendors_success(self, vendor_service, mock_repo):
        vendor_obj = {
            "_id": ObjectId("64ab9fbfe7f4f5b4a10ebc88"),
            "name": "Test Vendor",
            "vendor_type": "partner",
            "is_active": True,
        }
        mock_repo.find_all_vendors.return_value = [vendor_obj]

        result = await vendor_service.get_vendors()

        assert len(result) == 1
        assert result[0].name == "Test Vendor"
        assert result[0].id == "64ab9fbfe7f4f5b4a10ebc88"

    @pytest.mark.asyncio
    async def test_get_vendors_failure(self, vendor_service, mock_repo):
        mock_repo.find_all_vendors.side_effect = Exception("DB Failed")

        with pytest.raises(Exception):
            await vendor_service.get_vendors()

        vendor_service.logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_vendor_by_id_success(self, vendor_service, mock_repo):
        vendor_id = "64ab9fbfe7f4f5b4a10ebc88"
        mock_repo.find_vendor_by_id.return_value = {
            "_id": ObjectId(vendor_id),
            "name": "Vendor A",
            "slug": "vendor-a",
            "vendor_type": "airtel",
            "is_active": True,
        }

        result = await vendor_service.get_vendor_by_id(vendor_id)

        assert result.name == "Vendor A"
        assert result.id == vendor_id

    @pytest.mark.asyncio
    async def test_get_vendor_by_id_not_found(self, vendor_service, mock_repo):
        vendor_id = "64ab9fbfe7f4f5b4a10ebc88"
        mock_repo.find_vendor_by_id.return_value = None

        with pytest.raises(ResourceNotFound) as e:
            await vendor_service.get_vendor_by_id(vendor_id)

        assert VENDOR_NOT_FOUND.format(vendor_id) in str(e.value)

    @pytest.mark.asyncio
    async def test_get_vendor_by_id_exception(self, vendor_service, mock_repo):
        mock_repo.find_vendor_by_id.side_effect = Exception("DB Crash")

        with pytest.raises(Exception):
            await vendor_service.get_vendor_by_id("64ab9fbfe7f4f5b4a10ebc88")

        vendor_service.logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_activate_vendor_success(self, vendor_service, mock_repo):
        vendor_id = "64ab9fbfe7f4f5b4a10ebc88"
        mock_repo.find_vendor_by_id_all.return_value = {
            "_id": ObjectId(vendor_id),
            "is_active": False,
        }
        mock_repo.update_vendor_status.return_value = {
            "_id": ObjectId(vendor_id),
            "is_active": True,
        }

        result = await vendor_service.activate_vendor(vendor_id)

        assert result.message == VENDOR_ACTIVATED_SUCCESSFULLY

    @pytest.mark.asyncio
    async def test_activate_vendor_already_active(self, vendor_service, mock_repo):
        vendor_id = "64ab9fbfe7f4f5b4a10ebc88"
        mock_repo.find_vendor_by_id_all.return_value = {
            "_id": ObjectId(vendor_id),
            "is_active": True,
        }

        with pytest.raises(ConflictError):
            await vendor_service.activate_vendor(vendor_id)

    @pytest.mark.asyncio
    async def test_activate_vendor_not_found(self, vendor_service, mock_repo):
        mock_repo.find_vendor_by_id_all.return_value = None
        vendor_id = "64ab9fbfe7f4f5b4a10ebc88"

        with pytest.raises(ResourceNotFound):
            await vendor_service.activate_vendor(vendor_id)

    @pytest.mark.asyncio
    async def test_activate_vendor_exception(self, vendor_service, mock_repo):
        mock_repo.find_vendor_by_id_all.side_effect = Exception("Unexpected")

        with pytest.raises(Exception):
            await vendor_service.activate_vendor("64ab9fbfe7f4f5b4a10ebc88")

        vendor_service.logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_deactivate_vendor_success(self, vendor_service, mock_repo):
        vendor_id = "64ab9fbfe7f4f5b4a10ebc88"
        mock_repo.find_vendor_by_id_all.return_value = {
            "_id": ObjectId(vendor_id),
            "is_active": True,
        }
        mock_repo.update_vendor_status.return_value = {
            "_id": ObjectId(vendor_id),
            "is_active": False,
        }

        result = await vendor_service.deactivate_vendor(vendor_id)

        assert result.message == VENDOR_DEACTIVATED_SUCCESSFULLY

    @pytest.mark.asyncio
    async def test_deactivate_vendor_already_inactive(self, vendor_service, mock_repo):
        vendor_id = "64ab9fbfe7f4f5b4a10ebc88"
        mock_repo.find_vendor_by_id_all.return_value = {
            "_id": ObjectId(vendor_id),
            "is_active": False,
        }

        with pytest.raises(ConflictError):
            await vendor_service.deactivate_vendor(vendor_id)

    @pytest.mark.asyncio
    async def test_deactivate_vendor_not_found(self, vendor_service, mock_repo):
        mock_repo.find_vendor_by_id_all.return_value = None

        with pytest.raises(ResourceNotFound):
            await vendor_service.deactivate_vendor("64ab9fbfe7f4f5b4a10ebc88")

    @pytest.mark.asyncio
    async def test_deactivate_vendor_exception(self, vendor_service, mock_repo):
        mock_repo.find_vendor_by_id_all.side_effect = Exception("Unexpected")

        with pytest.raises(Exception):
            await vendor_service.deactivate_vendor("64ab9fbfe7f4f5b4a10ebc88")

        vendor_service.logger.error.assert_called()
