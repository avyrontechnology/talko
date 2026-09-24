from typing import Any

from bson import ObjectId

from src.components.did_management.services import TalkoDidManagementService
from src.components.vendor.message import INVALID_VENDOR_ID
from src.components.vendor.repository import TalkoVendorRepository
from src.components.vendor_config.dto import TalkoContract
from src.components.vendor_config.message import (
    INVALID_VENDOR_CONFIG_ID,
    NO_FIELDS_PROVIDED_FOR_UPDATE,
    VENDOR_CONFIG_CREATED_SUCCESSFULLY,
    VENDOR_CONFIG_UPDATED_SUCCESSFULLY,
)
from src.components.vendor_config.models import TalkoVendorConfigModel
from src.components.vendor_config.repository import TalkoVendorConfigRepository
from src.components.vendor_config.validation import TalkoVendorConfigValidator
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil


class TalkoVendorConfigService:
    """
    Service class responsible for managing vendor configuration operations,
    including creation, retrieval, and updates.
    """

    def __init__(
        self,
        repository: TalkoVendorConfigRepository,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
        validator: TalkoVendorConfigValidator,
        did_management_service: TalkoDidManagementService,
        vendor_repository: TalkoVendorRepository,
    ):
        self.__repository: TalkoVendorConfigRepository = repository
        self.__logger: TalkoServiceLogger = logger
        self.__datetime_util: TalkoDateTimeUtil = datetime_util
        self.__validator: TalkoVendorConfigValidator = validator
        self.__did_management_service: TalkoDidManagementService = did_management_service
        self.__vendor_repository: TalkoVendorRepository = vendor_repository

    async def create_vendor_config(
        self, config: TalkoContract.VendorConfigCreate
    ) -> TalkoContract.VendorConfigCreationUpdationResponse:
        try:
            self.__logger.info(f"Creating vendor config for vendor_id: {config.vendor_id}")

            self.__validator.validate_vendor_config_create(config)
            vendor_id: ObjectId = ObjectId(config.vendor_id)
            await self.__validator.validate_vendor_exists(vendor_id)

            # Get vendor to use its name/type for prefix
            vendor_doc: dict[str, Any] = await self.__vendor_repository.find_vendor_by_id_all(vendor_id)
            if not vendor_doc:
                raise TalkoResourceNotFound("Vendor not found")

            vendor_type: str = vendor_doc.get("vendor_type", "Unknown")

            # Clean short name for prefix (remove spaces, special chars, limit length)
            prefix: str = "".join(word.capitalize() for word in vendor_type.split("_"))[:20]

            # Count existing configs for this vendor to get next number
            existing_configs: list[dict[str, Any]] = await self.__repository.find_configs_by_vendor_id(vendor_id)
            next_number: int = len(existing_configs) + 1

            # Auto-generate name if not provided
            auto_name: str = f"{prefix}-{next_number}-Config"

            # You can also support user-provided name with fallback
            final_name: str = (
                config.name.strip() if getattr(config, "name", None) and config.name.strip() else auto_name
            )

            self.__logger.debug(f"Vendor validation completed for vendor_id: {vendor_id}")

            config_dict: dict[str, Any] = {
                "name": final_name,
                "vendor_id": vendor_id,
                "generic_url_handler": config.generic_url_handler,
                "cdr_url_handler": config.cdr_url_handler,
                "dialer_url_handler": config.dialer_url_handler,
                "channel_pool": config.channel_pool.model_dump() if config.channel_pool else None,
            }
            current_timestamp: Any = self.__datetime_util.get_current_time()
            config_dict["created_at"] = current_timestamp

            self.__logger.debug(f"Vendor config input: {config_dict}, timestamp: {current_timestamp}.")

            vendor_cfg: TalkoVendorConfigModel = TalkoVendorConfigModel(**config_dict)
            config_id: ObjectId = await self.__repository.insert_vendor_config(vendor_cfg.model_dump())

            for did_number in config.available_did:
                await self.__did_management_service.assign_did(
                    workspace_id=0,
                    did_number=did_number,
                    partner_id=0,
                    vendor_id=str(vendor_id),
                    vendor_config_id=str(config_id),
                )

            self.__logger.info(f"Vendor config created with ID: {config_id}")

            return TalkoContract.VendorConfigCreationUpdationResponse(
                id=str(config_id), message=VENDOR_CONFIG_CREATED_SUCCESSFULLY
            )
        except Exception as e:
            self.__logger.error(f"Failed to create vendor config service: {str(e)}.")
            raise

    async def get_all_configs(self) -> list[TalkoContract.GetAllVendorConfigData]:
        self.__logger.info("Retrieving all vendor configs service started.")
        try:
            configs: list[dict[str, Any]] = await self.__repository.find_all_configs()
            self.__logger.debug(f"Retrieved vendor configs from the database. data: {configs}")

            config_responses: list[TalkoContract.GetAllVendorConfigData] = []
            for config in configs:
                config["id"] = str(config["_id"])
                del config["_id"]
                config_responses.append(TalkoContract.GetAllVendorConfigData(**config))

            self.__logger.debug(f"Converted vendor configs to response format. data: {config_responses}")
            self.__logger.info("Retrieved all vendor configs data successfully.")
            return config_responses
        except Exception as e:
            self.__logger.error(f"Failed to retrieve vendor configs: {str(e)}")
            raise

    async def get_config_by_id(self, id: str) -> TalkoContract.VendorConfigResponse:
        try:
            self.__logger.info(f"Retrieving vendor config by ID: {id}")
            try:
                object_id: ObjectId = ObjectId(id)
            except Exception:
                self.__logger.error(f"Invalid vendor config_id: {id}")
                raise ValueError(INVALID_VENDOR_CONFIG_ID)

            await self.__validator.validate_vendor_config_exists(object_id)
            self.__logger.debug(f"Vendor config validation completed for id: {object_id}")

            config: dict[str, Any] = await self.__repository.find_config_by_id(object_id)
            if not config:
                self.__logger.error(f"No config found for id {id}")
                raise TalkoResourceNotFound(f"No vendor config found for id {id}")

            config["id"] = str(config["_id"])
            del config["_id"]

            vendor_id: ObjectId = config["vendor_id"]
            assigned_dids: list[str] = await self.__did_management_service.get_assigned_dids(vendor_id)
            available_dids: list[str] = await self.__did_management_service.get_available_dids(
                vendor_id, ObjectId(config.get("id"))
            )
            config["vendor_id"] = str(vendor_id)
            config["name"] = config.get("name", "")
            config["available_did"] = available_dids
            config["assigned_did"] = assigned_dids
            config["dialer_url_handler"] = config.get("dialer_url_handler")
            config["channel_pool"] = config.get("channel_pool")

            self.__logger.debug(f"Returning vendor config response: {config}")
            self.__logger.info(f"Vendor config retrieved successfully for id: {id}")
            return TalkoContract.VendorConfigResponse(**config)
        except Exception as e:
            self.__logger.error(f"Failed to retrieve vendor config by ID {id}: {str(e)}")
            raise

    async def update_vendor_config(
        self, id: str, update: TalkoContract.VendorConfigUpdate
    ) -> TalkoContract.VendorConfigCreationUpdationResponse:
        self.__logger.info(f"Updating vendor config for id: {id}")
        try:
            try:
                object_id: ObjectId = ObjectId(id)
            except Exception:
                self.__logger.error(f"Invalid vendor config_id: {id}.")
                raise ValueError(INVALID_VENDOR_CONFIG_ID)

            await self.__validator.validate_vendor_config_exists(object_id)
            self.__logger.debug(f"Vendor config validation completed for id: {object_id}")

            update_dict: dict[str, Any] = {k: v for k, v in update.model_dump().items() if v is not None}
            if not update_dict:
                self.__logger.error(NO_FIELDS_PROVIDED_FOR_UPDATE)
                raise TalkoBadRequestError(NO_FIELDS_PROVIDED_FOR_UPDATE)

            self.__logger.debug(f"Provided updated vendor config data: {update_dict}")

            update_dict["updated_at"] = self.__datetime_util.get_current_time()

            updated_config: dict[str, Any] = await self.__repository.update_vendor_config(object_id, update_dict)
            updated_config["id"] = str(updated_config["_id"])
            del updated_config["_id"]

            if update.available_did:
                vendor_id: ObjectId = ObjectId(updated_config["vendor_id"])
                for did_number in update.available_did:
                    await self.__did_management_service.assign_did(
                        workspace_id=0,
                        did_number=did_number,
                        partner_id=0,
                        vendor_id=str(vendor_id),
                        vendor_config_id=str(object_id),
                    )

            self.__logger.debug(f"Updated vendor config: {updated_config}")
            self.__logger.info(f"Vendor config updated successfully for id: {id}")
            return TalkoContract.VendorConfigCreationUpdationResponse(
                id=str(updated_config["id"]),
                message=VENDOR_CONFIG_UPDATED_SUCCESSFULLY,
            )
        except Exception as e:
            self.__logger.error(f"Failed to update vendor config: {str(e)}")
            raise

    async def update_did_lists(
        self,
        vendor_id: str,
        remove_from_available: list[str] | None = None,
        add_to_available: list[str] | None = None,
        remove_from_assigned: list[str] | None = None,
        add_to_assigned: list[str] | None = None,
    ) -> TalkoContract.VendorConfigResponse:
        self.__logger.info("In vendor config update did list method started")
        self.__logger.debug(
            f"In update did list data received. vendor id: {vendor_id}, remove from available: {remove_from_available}, "
            f"add to available: {add_to_available}, remove from assigned: {remove_from_assigned}, add to assigned: {add_to_assigned}."
        )

        try:
            object_id: ObjectId = ObjectId(vendor_id)
        except Exception:
            self.__logger.error(f"In update did list method invalid vendor_id: {vendor_id}.")
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

        config: dict[str, Any] = await self.__repository.find_config_by_id(object_id)
        if not config:
            raise TalkoResourceNotFound(f"No vendor config found for id {vendor_id}")

        config["id"] = str(config["_id"])
        del config["_id"]
        config["vendor_id"] = str(config["vendor_id"])

        assigned_dids: list[str] = await self.__did_management_service.get_assigned_dids(object_id)
        available_dids: list[str] = await self.__did_management_service.get_available_dids(object_id)

        config["available_did"] = available_dids
        config["assigned_did"] = assigned_dids

        self.__logger.debug(f"Updated did lists for vendor config: {config}")
        self.__logger.info("Updated did list for vendor config ended successfully.")
        return TalkoContract.VendorConfigResponse(**config)
