from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.vendor_config.dto import Contract
from src.components.vendor_config.message import (
    NO_FIELDS_PROVIDED_FOR_UPDATE,
    VENDOR_CONFIG_CREATED_SUCCESSFULLY,
)
from src.components.vendor_config.services import VendorConfigService
from src.exceptions import BadRequestError, ResourceNotFound


@pytest.mark.asyncio
class TestVendorConfigService:
    @pytest.fixture
    def service(self):
        repo = AsyncMock()
        logger = MagicMock()
        datetime_util = MagicMock()
        datetime_util.get_current_time.return_value = 1735689600

        svc = VendorConfigService(
            repository=repo,
            logger=logger,
            datetime_util=datetime_util,
            validator=AsyncMock(),
            did_management_service=AsyncMock(),
            vendor_repository=AsyncMock(),
        )
        return svc

    def get_private(self, obj, attr):
        return getattr(obj, f"_VendorConfigService__{attr}")

    async def test_get_all_configs_success(self, service):
        self.get_private(service, "repository").find_all_configs.return_value = [
            {"_id": ObjectId(), "vendor_id": ObjectId(), "vendor_name": "Tata Tele"}
        ]

        results = await service.get_all_configs()
        assert len(results) == 1
        assert results[0].vendor_name == "Tata Tele"

    async def test_get_config_by_id_success(self, service):
        config_id = ObjectId()
        vendor_id = ObjectId()

        self.get_private(service, "repository").find_config_by_id.return_value = {
            "_id": config_id,
            "vendor_id": vendor_id,
            "name": "Tata-1-Config",
            "vendor_name": "Tata Tele",
            "generic_url_handler": {"url": "http://test.com"},
            "created_at": 1735689600,
            "updated_at": 1735689600,
        }
        self.get_private(
            service, "did_management_service"
        ).get_assigned_dids.return_value = ["+911"]
        self.get_private(
            service, "did_management_service"
        ).get_available_dids.return_value = ["+912"]

        result = await service.get_config_by_id(str(config_id))
        assert result.id == str(config_id)
        assert result.vendor_name == "Tata Tele"
        assert result.assigned_did == ["+911"]

    async def test_update_did_lists_success(self, service):
        vendor_id = ObjectId()

        self.get_private(service, "repository").find_config_by_id.return_value = {
            "_id": ObjectId(),
            "vendor_id": vendor_id,
            "name": "Airtel-Config",
            "vendor_name": "Airtel India",
            "generic_url_handler": {"url": "http://airtel.com"},
            "created_at": 1735689600,
            "updated_at": 1735689600,
        }
        self.get_private(
            service, "did_management_service"
        ).get_assigned_dids.return_value = []
        self.get_private(
            service, "did_management_service"
        ).get_available_dids.return_value = ["+91000"]

        result = await service.update_did_lists(
            str(vendor_id), add_to_available=["+91000"]
        )

        assert result.name == "Airtel-Config"
        assert result.available_did == ["+91000"]

    async def test_create_vendor_config_success(self, service):
        vendor_id = ObjectId()
        config_dto = Contract.VendorConfigCreate(
            vendor_id=str(vendor_id),
            available_did=["+91999"],
            generic_url_handler={"endpoint": "test"},
        )

        self.get_private(
            service, "vendor_repository"
        ).find_vendor_by_id_all.return_value = {"vendor_type": "knowlarity"}
        self.get_private(
            service, "repository"
        ).find_configs_by_vendor_id.return_value = []
        self.get_private(service, "repository").insert_vendor_config.return_value = (
            ObjectId()
        )

        result = await service.create_vendor_config(config_dto)
        assert result.message == VENDOR_CONFIG_CREATED_SUCCESSFULLY


@pytest.mark.asyncio
class TestVendorConfigServiceCoverage:
    @pytest.fixture
    def service(self):
        repo = AsyncMock()
        logger = MagicMock()
        datetime_util = MagicMock()
        datetime_util.get_current_time.return_value = 123456789

        svc = VendorConfigService(
            repository=repo,
            logger=logger,
            datetime_util=datetime_util,
            validator=AsyncMock(),
            did_management_service=AsyncMock(),
            vendor_repository=AsyncMock(),
        )
        return svc

    def get_private(self, obj, attr):
        return getattr(obj, f"_VendorConfigService__{attr}")

    async def test_create_vendor_config_did_loop_coverage(self, service):
        vendor_id = ObjectId()
        config = Contract.VendorConfigCreate(
            vendor_id=str(vendor_id),
            available_did=["+911", "+912"],
            generic_url_handler={"url": "test"},
        )
        self.get_private(
            service, "vendor_repository"
        ).find_vendor_by_id_all.return_value = {"vendor_type": "test"}
        self.get_private(
            service, "repository"
        ).find_configs_by_vendor_id.return_value = []
        self.get_private(service, "repository").insert_vendor_config.return_value = (
            ObjectId()
        )

        await service.create_vendor_config(config)
        assert (
            self.get_private(service, "did_management_service").assign_did.call_count
            == 2
        )

    async def test_get_all_configs_exception(self, service):
        self.get_private(service, "repository").find_all_configs.side_effect = (
            Exception("DB Fail")
        )
        with pytest.raises(Exception, match="DB Fail"):
            await service.get_all_configs()
        self.get_private(service, "logger").error.assert_called()

    async def test_get_config_by_id_invalid_oid(self, service):
        with pytest.raises(ValueError):
            await service.get_config_by_id("invalid-id")

    async def test_get_config_by_id_not_found(self, service):
        self.get_private(service, "repository").find_config_by_id.return_value = None
        with pytest.raises(ResourceNotFound):
            await service.get_config_by_id(str(ObjectId()))

    async def test_get_config_by_id_exception_logging(self, service):
        self.get_private(service, "repository").find_config_by_id.side_effect = (
            Exception("Fail")
        )
        with pytest.raises(Exception):
            await service.get_config_by_id(str(ObjectId()))

    async def test_update_vendor_config_invalid_id(self, service):
        with pytest.raises(ValueError):
            await service.update_vendor_config("invalid", MagicMock())

    async def test_update_vendor_config_no_fields(self, service):
        config_id = str(ObjectId())

        update_dto = Contract.VendorConfigUpdate(
            generic_url_handler=None,
            available_did=None,
            cdr_url_handler=None,
            dialer_url_handler=None,
        )

        self.get_private(
            service, "validator"
        ).validate_vendor_config_exists.return_value = None

        with pytest.raises(BadRequestError, match=NO_FIELDS_PROVIDED_FOR_UPDATE):
            await service.update_vendor_config(config_id, update_dto)

    async def test_update_vendor_config_did_loop(self, service):
        config_id = ObjectId()
        update = MagicMock(spec=Contract.VendorConfigUpdate)
        update.model_dump.return_value = {"available_did": ["+913"]}
        update.available_did = ["+913"]

        self.get_private(service, "repository").update_vendor_config.return_value = {
            "_id": config_id,
            "vendor_id": ObjectId(),
        }
        await service.update_vendor_config(str(config_id), update)
        self.get_private(service, "did_management_service").assign_did.assert_awaited()

    async def test_update_vendor_config_exception(self, service):
        self.get_private(service, "repository").update_vendor_config.side_effect = (
            Exception("Update Fail")
        )
        update = MagicMock()
        update.model_dump.return_value = {"name": "test"}
        with pytest.raises(Exception):
            await service.update_vendor_config(str(ObjectId()), update)

    async def test_update_did_lists_invalid_id(self, service):
        with pytest.raises(ValueError):
            await service.update_did_lists("invalid-id")

    async def test_update_did_lists_config_not_found(self, service):
        vendor_id = ObjectId()
        self.get_private(service, "repository").find_config_by_id.return_value = None
        with pytest.raises(ResourceNotFound):
            await service.update_did_lists(str(vendor_id))

    async def test_update_did_lists_invalid_id_format(self, service):
        with pytest.raises(ValueError):
            await service.update_did_lists("not-a-valid-object-id")
        self.get_private(service, "logger").error.assert_called()
