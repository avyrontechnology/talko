from typing import Any, Dict, List, Optional

from bson import ObjectId

from src.components.did_management.services import DidManagementService
from src.components.vendor.message import INVALID_VENDOR_ID
from src.components.vendor.repository import VendorRepository
from src.components.vendor_config.constants import ADD_TO_SET, PULL_ALL, SET
from src.components.vendor_config.dto import Contract
from src.components.vendor_config.message import (
    INVALID_VENDOR_CONFIG_ID,
    NO_FIELDS_PROVIDED_FOR_UPDATE,
    VENDOR_CONFIG_CREATED_SUCCESSFULLY,
    VENDOR_CONFIG_UPDATED_SUCCESSFULLY,
)
from src.components.vendor_config.models import VendorConfigModel
from src.components.vendor_config.repository import VendorConfigRepository
from src.components.vendor_config.validation import VendorConfigValidator
from src.exceptions import BadRequestError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.datetime_util import DateTimeUtil


class VendorConfigService:
    """
    Service class responsible for managing vendor configuration operations,
    including creation, retrieval, and updates.
    """

    def __init__(
        self,
        repository: VendorConfigRepository,
        logger: HollerServiceLogger,
        datetime_util: DateTimeUtil,
        validator: VendorConfigValidator,
        did_management_service: DidManagementService,
        vendor_repository: VendorRepository,
    ):
        self.__repository: VendorConfigRepository = repository
        self.__logger: HollerServiceLogger = logger
        self.__datetime_util: DateTimeUtil = datetime_util
        self.__validator: VendorConfigValidator = validator
        self.__did_management_service: DidManagementService = did_management_service
        self.__vendor_repository: VendorRepository = vendor_repository

    async def create_vendor_config(
        self, config: Contract.VendorConfigCreate
    ) -> Contract.VendorConfigCreationUpdationResponse:
        try:
            self.__logger.info(
                "Creating vendor config for vendor_id: {}".format(config.vendor_id)
            )

            self.__validator.validate_vendor_config_create(config)
            vendor_id: ObjectId = ObjectId(config.vendor_id)
            await self.__validator.validate_vendor_exists(vendor_id)

            # Get vendor to use its name/type for prefix
            vendor_doc: Dict[str, Any] = (
                await self.__vendor_repository.find_vendor_by_id_all(vendor_id)
            )
            if not vendor_doc:
                raise ResourceNotFound("Vendor not found")

            vendor_type: str = vendor_doc.get("vendor_type", "Unknown")

            # Clean short name for prefix (remove spaces, special chars, limit length)
            prefix: str = "".join(word.capitalize() for word in vendor_type.split("_"))[
                :20
            ]

            # Count existing configs for this vendor to get next number
            existing_configs: List[Dict[str, Any]] = (
                await self.__repository.find_configs_by_vendor_id(vendor_id)
            )
            next_number: int = len(existing_configs) + 1

            # Auto-generate name if not provided
            auto_name: str = "{}-{}-Config".format(prefix, next_number)

            # You can also support user-provided name with fallback
            final_name: str = (
                config.name.strip()
                if getattr(config, "name", None) and config.name.strip()
                else auto_name
            )

            self.__logger.debug(
                "Vendor validation completed for vendor_id: {}".format(vendor_id)
            )

            config_dict: Dict[str, Any] = {
                "name": final_name,
                "vendor_id": vendor_id,
                "generic_url_handler": config.generic_url_handler,
                "cdr_url_handler": config.cdr_url_handler,
                "dialer_url_handler": config.dialer_url_handler,
            }
            current_timestamp: Any = self.__datetime_util.get_current_time()
            config_dict["created_at"] = current_timestamp

            self.__logger.debug(
                "Vendor config input: {}, timestamp: {}.".format(
                    config_dict, current_timestamp
                )
            )

            vendor_cfg: VendorConfigModel = VendorConfigModel(**config_dict)
            config_id: ObjectId = await self.__repository.insert_vendor_config(
                vendor_cfg.model_dump()
            )

            for did_number in config.available_did:
                await self.__did_management_service.assign_did(
                    service_board_id=0,
                    did_number=did_number,
                    partner_id=0,
                    vendor_id=str(vendor_id),
                    vendor_config_id=str(config_id),
                )

            self.__logger.info("Vendor config created with ID: {}".format(config_id))

            return Contract.VendorConfigCreationUpdationResponse(
                id=str(config_id), message=VENDOR_CONFIG_CREATED_SUCCESSFULLY
            )
        except Exception as e:
            self.__logger.error(
                "Failed to create vendor config service: {}.".format(str(e))
            )
            raise

    async def get_all_configs(self) -> List[Contract.GetAllVendorConfigData]:
        self.__logger.info("Retrieving all vendor configs service started.")
        try:
            configs: List[Dict[str, Any]] = await self.__repository.find_all_configs()
            self.__logger.debug(
                "Retrieved vendor configs from the database. data: {}".format(configs)
            )

            config_responses: List[Contract.GetAllVendorConfigData] = []
            for config in configs:
                config["id"] = str(config["_id"])
                del config["_id"]
                config_responses.append(Contract.GetAllVendorConfigData(**config))

            self.__logger.debug(
                "Converted vendor configs to response format. data: {}".format(
                    config_responses
                )
            )
            self.__logger.info("Retrieved all vendor configs data successfully.")
            return config_responses
        except Exception as e:
            self.__logger.error("Failed to retrieve vendor configs: {}".format(str(e)))
            raise

    async def get_config_by_id(self, id: str) -> Contract.VendorConfigResponse:
        try:
            self.__logger.info("Retrieving vendor config by ID: {}".format(id))
            try:
                object_id: ObjectId = ObjectId(id)
            except Exception:
                self.__logger.error("Invalid vendor config_id: {}".format(id))
                raise ValueError(INVALID_VENDOR_CONFIG_ID)

            await self.__validator.validate_vendor_config_exists(object_id)
            self.__logger.debug(
                "Vendor config validation completed for id: {}".format(object_id)
            )

            config: Dict[str, Any] = await self.__repository.find_config_by_id(
                object_id
            )
            if not config:
                self.__logger.error("No config found for id {}".format(id))
                raise ResourceNotFound("No vendor config found for id {}".format(id))

            config["id"] = str(config["_id"])
            del config["_id"]

            vendor_id: ObjectId = config["vendor_id"]
            assigned_dids: List[str] = (
                await self.__did_management_service.get_assigned_dids(vendor_id)
            )
            available_dids: List[str] = (
                await self.__did_management_service.get_available_dids(
                    vendor_id, ObjectId(config.get("id"))
                )
            )
            config["vendor_id"] = str(vendor_id)
            config["name"] = config.get("name", "")
            config["available_did"] = available_dids
            config["assigned_did"] = assigned_dids
            config["dialer_url_handler"] = config.get("dialer_url_handler")

            self.__logger.debug("Returning vendor config response: {}".format(config))
            self.__logger.info(
                "Vendor config retrieved successfully for id: {}".format(id)
            )
            return Contract.VendorConfigResponse(**config)
        except Exception as e:
            self.__logger.error(
                "Failed to retrieve vendor config by ID {}: {}".format(id, str(e))
            )
            raise

    async def update_vendor_config(
        self, id: str, update: Contract.VendorConfigUpdate
    ) -> Contract.VendorConfigCreationUpdationResponse:
        self.__logger.info("Updating vendor config for id: {}".format(id))
        try:
            try:
                object_id: ObjectId = ObjectId(id)
            except Exception:
                self.__logger.error("Invalid vendor config_id: {}.".format(id))
                raise ValueError(INVALID_VENDOR_CONFIG_ID)

            await self.__validator.validate_vendor_config_exists(object_id)
            self.__logger.debug(
                "Vendor config validation completed for id: {}".format(object_id)
            )

            update_dict: Dict[str, Any] = {
                k: v for k, v in update.model_dump().items() if v is not None
            }
            if not update_dict:
                self.__logger.error(NO_FIELDS_PROVIDED_FOR_UPDATE)
                raise BadRequestError(NO_FIELDS_PROVIDED_FOR_UPDATE)

            self.__logger.debug(
                "Provided updated vendor config data: {}".format(update_dict)
            )

            update_dict["updated_at"] = self.__datetime_util.get_current_time()

            updated_config: Dict[str, Any] = (
                await self.__repository.update_vendor_config(object_id, update_dict)
            )
            updated_config["id"] = str(updated_config["_id"])
            del updated_config["_id"]

            if update.available_did:
                vendor_id: ObjectId = ObjectId(updated_config["vendor_id"])
                for did_number in update.available_did:
                    await self.__did_management_service.assign_did(
                        service_board_id=0,
                        did_number=did_number,
                        partner_id=0,
                        vendor_id=str(vendor_id),
                        vendor_config_id=str(object_id),
                    )

            self.__logger.debug("Updated vendor config: {}".format(updated_config))
            self.__logger.info(
                "Vendor config updated successfully for id: {}".format(id)
            )
            return Contract.VendorConfigCreationUpdationResponse(
                id=str(updated_config["id"]),
                message=VENDOR_CONFIG_UPDATED_SUCCESSFULLY,
            )
        except Exception as e:
            self.__logger.error("Failed to update vendor config: {}".format(str(e)))
            raise

    async def update_did_lists(
        self,
        vendor_id: str,
        remove_from_available: Optional[List[str]] = None,
        add_to_available: Optional[List[str]] = None,
        remove_from_assigned: Optional[List[str]] = None,
        add_to_assigned: Optional[List[str]] = None,
    ) -> Contract.VendorConfigResponse:
        self.__logger.info("In vendor config update did list method started")
        self.__logger.debug(
            "In update did list data received. vendor id: {}, remove from available: {}, "
            "add to available: {}, remove from assigned: {}, add to assigned: {}.".format(
                vendor_id,
                remove_from_available,
                add_to_available,
                remove_from_assigned,
                add_to_assigned,
            )
        )

        try:
            object_id: ObjectId = ObjectId(vendor_id)
        except Exception:
            self.__logger.error(
                "In update did list method invalid vendor_id: {}.".format(vendor_id)
            )
            raise ValueError(INVALID_VENDOR_ID)

        current_timestamp: Any = self.__datetime_util.get_current_time()
        await self.__did_management_service.update_did_status(
            vendor_id=object_id,
            remove_from_available=remove_from_available or [],
            add_to_available=add_to_available or [],
            remove_from_assigned=remove_from_assigned or [],
            add_to_assigned=add_to_assigned or [],
            timestamp=current_timestamp,
        )

        config: Dict[str, Any] = await self.__repository.find_config_by_id(object_id)
        if not config:
            raise ResourceNotFound("No vendor config found for id {}".format(vendor_id))

        config["id"] = str(config["_id"])
        del config["_id"]
        config["vendor_id"] = str(config["vendor_id"])

        assigned_dids: List[str] = (
            await self.__did_management_service.get_assigned_dids(object_id)
        )
        available_dids: List[str] = (
            await self.__did_management_service.get_available_dids(object_id)
        )

        config["available_did"] = available_dids
        config["assigned_did"] = assigned_dids

        self.__logger.debug("Updated did lists for vendor config: {}".format(config))
        self.__logger.info("Updated did list for vendor config ended successfully.")
        return Contract.VendorConfigResponse(**config)
