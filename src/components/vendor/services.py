import uuid

from bson import ObjectId

from src.components.vendor.dto import Contract
from src.components.vendor.message import (
    VENDOR_ACTIVATED_SUCCESSFULLY,
    VENDOR_CREATED_SUCCESSFULLY,
    VENDOR_DEACTIVATED_SUCCESSFULLY,
)
from src.components.vendor.models import VendorModel
from src.components.vendor.repository import VendorRepository
from src.components.vendor.validation import VendorValidator
from src.exceptions import ConflictError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.common_messages import VENDOR_NOT_FOUND
from src.utils.datetime_util import DateTimeUtil


class VendorService:
    def __init__(
        self,
        vendor_repo: VendorRepository,
        logger: HollerServiceLogger,
        datetime_util: DateTimeUtil,
        validator: VendorValidator,
    ):
        self.repository = vendor_repo
        self.logger = logger
        self.datetime_util = datetime_util
        self.validator = validator

    async def create_vendor(
        self, vendor: Contract.VendorCreate
    ) -> Contract.VendorResponse:
        self.logger.info("Creating vendor with name: {}".format(vendor.name))
        try:
            await self.validator.validate_vendor_create(vendor)
            self.logger.debug("Vendor data validation completed.")

            vendor_dict = vendor.model_dump()
            current_timestamp = self.datetime_util.get_current_time()
            self.logger.debug(
                "Vendor input: {}, timestamp: {}.".format(
                    vendor_dict, current_timestamp
                )
            )

            vendor_record = VendorModel(
                name=vendor.name,
                slug=str(uuid.uuid4()),
                vendor_type=vendor_dict["vendor_type"].value,
                is_active=True,
            ).model_dump(mode="json")

            vendor_id = await self.repository.insert_vendor(vendor_record)
            return Contract.VendorResponse(
                id=str(vendor_id), message=VENDOR_CREATED_SUCCESSFULLY
            )

        except Exception as e:
            self.logger.error("Error creating vendor: {}".format(str(e)))
            raise

    async def get_vendors(self) -> list[Contract.GetAllVendorData]:
        self.logger.info("Get vendor all list started.")
        try:
            vendors = await self.repository.find_all_vendors()
            vendor_responses = []
            for vendor in vendors:
                vendor["id"] = str(vendor["_id"])
                del vendor["_id"]
                vendor_responses.append(vendor)
            return [Contract.GetAllVendorData(**vendor) for vendor in vendor_responses]
        except Exception as e:
            self.logger.error("Error fetching vendors: {}".format(str(e)))
            raise

    async def get_vendor_by_id(
        self, vendor_id: str
    ) -> Contract.GetVendorDataOnTheBasisOfId:
        self.logger.info("Get vendor by ID started.")
        try:
            object_id = ObjectId(vendor_id)
            vendor = await self.repository.find_vendor_by_id(object_id)
            if not vendor:
                raise ResourceNotFound(VENDOR_NOT_FOUND.format(vendor_id))

            vendor["id"] = str(vendor["_id"])
            del vendor["_id"]
            return Contract.GetVendorDataOnTheBasisOfId(**vendor)

        except Exception as e:
            self.logger.error("Error getting vendor by ID: {}".format(str(e)))
            raise

    async def activate_vendor(self, vendor_id: str) -> Contract.VendorResponse:
        self.logger.info("Activating vendor with ID: {}".format(vendor_id))
        try:
            object_id = ObjectId(vendor_id)
            vendor = await self.repository.find_vendor_by_id_all(object_id)
            if not vendor:
                raise ResourceNotFound(VENDOR_NOT_FOUND.format(vendor_id))
            if vendor["is_active"]:
                raise ConflictError(
                    "Vendor with ID {} is already active.".format(vendor_id)
                )

            updated_timestamp = self.datetime_util.get_current_time()
            updated_vendor = await self.repository.update_vendor_status(
                object_id, is_active=True, updated_at=updated_timestamp
            )

            return Contract.VendorResponse(
                id=str(updated_vendor["_id"]), message=VENDOR_ACTIVATED_SUCCESSFULLY
            )

        except Exception as e:
            self.logger.error("Error activating vendor: {}".format(str(e)))
            raise

    async def deactivate_vendor(self, vendor_id: str) -> Contract.VendorResponse:
        self.logger.info("Deactivating vendor with ID: {}".format(vendor_id))
        try:
            object_id = ObjectId(vendor_id)
            vendor = await self.repository.find_vendor_by_id_all(object_id)
            if not vendor:
                raise ResourceNotFound(VENDOR_NOT_FOUND.format(vendor_id))
            if not vendor["is_active"]:
                raise ConflictError(
                    "Vendor with ID {} is already active.".format(vendor_id)
                )

            updated_timestamp = self.datetime_util.get_current_time()
            updated_vendor = await self.repository.update_vendor_status(
                object_id, is_active=False, updated_at=updated_timestamp
            )

            return Contract.VendorResponse(
                id=str(updated_vendor["_id"]), message=VENDOR_DEACTIVATED_SUCCESSFULLY
            )

        except Exception as e:
            self.logger.error("Error deactivating vendor: {}".format(str(e)))
            raise
