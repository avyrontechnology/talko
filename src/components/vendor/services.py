import uuid

from bson import ObjectId

from src.components.vendor.dto import TalkoContract
from src.components.vendor.message import (
    VENDOR_ACTIVATED_SUCCESSFULLY,
    VENDOR_CREATED_SUCCESSFULLY,
    VENDOR_DEACTIVATED_SUCCESSFULLY,
)
from src.components.vendor.models import TalkoVendorModel
from src.components.vendor.repository import TalkoVendorRepository
from src.components.vendor.validation import TalkoVendorValidator
from src.exceptions import TalkoConflictError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.common_messages import VENDOR_NOT_FOUND
from src.utils.datetime_util import TalkoDateTimeUtil


class TalkoVendorService:
    def __init__(
        self,
        vendor_repo: TalkoVendorRepository,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
        validator: TalkoVendorValidator,
    ):
        self.repository = vendor_repo
        self.logger = logger
        self.datetime_util = datetime_util
        self.validator = validator

    async def create_vendor(
        self, vendor: TalkoContract.VendorCreate
    ) -> TalkoContract.VendorResponse:
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

            vendor_record = TalkoVendorModel(
                name=vendor.name,
                slug=str(uuid.uuid4()),
                vendor_type=vendor_dict["vendor_type"].value,
                is_active=True,
            ).model_dump(mode="json")

            vendor_id = await self.repository.insert_vendor(vendor_record)
            return TalkoContract.VendorResponse(
                id=str(vendor_id), message=VENDOR_CREATED_SUCCESSFULLY
            )

        except Exception as e:
            self.logger.error("Error creating vendor: {}".format(str(e)))
            raise

    async def get_vendors(self) -> list[TalkoContract.GetAllVendorData]:
        self.logger.info("Get vendor all list started.")
        try:
            vendors = await self.repository.find_all_vendors()
            vendor_responses = []
            for vendor in vendors:
                vendor["id"] = str(vendor["_id"])
                del vendor["_id"]
                vendor_responses.append(vendor)
            return [TalkoContract.GetAllVendorData(**vendor) for vendor in vendor_responses]
        except Exception as e:
            self.logger.error("Error fetching vendors: {}".format(str(e)))
            raise

    async def get_vendor_by_id(
        self, vendor_id: str
    ) -> TalkoContract.GetVendorDataOnTheBasisOfId:
        self.logger.info("Get vendor by ID started.")
        try:
            object_id = ObjectId(vendor_id)
            vendor = await self.repository.find_vendor_by_id(object_id)
            if not vendor:
                raise TalkoResourceNotFound(VENDOR_NOT_FOUND.format(vendor_id))

            vendor["id"] = str(vendor["_id"])
            del vendor["_id"]
            return TalkoContract.GetVendorDataOnTheBasisOfId(**vendor)

        except Exception as e:
            self.logger.error("Error getting vendor by ID: {}".format(str(e)))
            raise

    async def activate_vendor(self, vendor_id: str) -> TalkoContract.VendorResponse:
        self.logger.info("Activating vendor with ID: {}".format(vendor_id))
        try:
            object_id = ObjectId(vendor_id)
            vendor = await self.repository.find_vendor_by_id_all(object_id)
            if not vendor:
                raise TalkoResourceNotFound(VENDOR_NOT_FOUND.format(vendor_id))
            if vendor["is_active"]:
                raise TalkoConflictError(
                    "Vendor with ID {} is already active.".format(vendor_id)
                )

            updated_timestamp = self.datetime_util.get_current_time()
            updated_vendor = await self.repository.update_vendor_status(
                object_id, is_active=True, updated_at=updated_timestamp
            )

            return TalkoContract.VendorResponse(
                id=str(updated_vendor["_id"]), message=VENDOR_ACTIVATED_SUCCESSFULLY
            )

        except Exception as e:
            self.logger.error("Error activating vendor: {}".format(str(e)))
            raise

    async def deactivate_vendor(self, vendor_id: str) -> TalkoContract.VendorResponse:
        self.logger.info("Deactivating vendor with ID: {}".format(vendor_id))
        try:
            object_id = ObjectId(vendor_id)
            vendor = await self.repository.find_vendor_by_id_all(object_id)
            if not vendor:
                raise TalkoResourceNotFound(VENDOR_NOT_FOUND.format(vendor_id))
            if not vendor["is_active"]:
                raise TalkoConflictError(
                    "Vendor with ID {} is already active.".format(vendor_id)
                )

            updated_timestamp = self.datetime_util.get_current_time()
            updated_vendor = await self.repository.update_vendor_status(
                object_id, is_active=False, updated_at=updated_timestamp
            )

            return TalkoContract.VendorResponse(
                id=str(updated_vendor["_id"]), message=VENDOR_DEACTIVATED_SUCCESSFULLY
            )

        except Exception as e:
            self.logger.error("Error deactivating vendor: {}".format(str(e)))
            raise
