from typing import Any, Dict, List

from bson import ObjectId

from src.components.did_management.services import TalkoDidManagementService
from src.components.partner_config.dto import TalkoContract
from src.components.partner_config.helper import TalkoPartnerConfigHelper
from src.components.partner_config.message import (
    NO_AVAILABLE_DIDS_FOR_VENDOR,
    PARTNER_CONFIG_WITH_ID_NOT_FOUND,
    PARTNER_CONFIG_WITH_PARTNER_ID_ALREADY_EXIST,
)
from src.components.partner_config.models import TalkoPartnerConfigModel
from src.components.partner_config.repository import TalkoPartnerConfigRepository
from src.components.partner_config.validation import TalkoPartnerConfigValidator
from src.components.vendor.validation import TalkoVendorValidator
from src.components.vendor_config.repository import TalkoVendorConfigRepository
from src.components.vendor_config.services import TalkoVendorConfigService
from src.components.vendor_config.validation import TalkoVendorConfigValidator
from src.exceptions import TalkoBadRequestError, TalkoConflictError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil


class TalkoPartnerConfigService:
    """
    Service class for handling partner config operations such as create, get all, and get by ID.
    """

    def __init__(
        self,
        repository: TalkoPartnerConfigRepository,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
        validator: TalkoVendorValidator,
        vendor_config_service: TalkoVendorConfigService,
        vendor_config_validator: TalkoVendorConfigValidator,
        vendor_config_repository: TalkoVendorConfigRepository,
        partner_config_validator: TalkoPartnerConfigValidator,
        did_management_service: TalkoDidManagementService,
    ):
        """
        Initialize the service with necessary dependencies.
        """
        self.repository: TalkoPartnerConfigRepository = repository
        self.logger: TalkoServiceLogger = logger
        self.datetime_util: TalkoDateTimeUtil = datetime_util
        self.validator: TalkoVendorValidator = validator
        self.vendor_config_service: TalkoVendorConfigService = vendor_config_service
        self.vendor_config_validator: TalkoVendorConfigValidator = vendor_config_validator
        self.vendor_config_repository: TalkoVendorConfigRepository = vendor_config_repository
        self.partner_config_validator: TalkoPartnerConfigValidator = partner_config_validator
        self.did_management_service: TalkoDidManagementService = did_management_service

    async def create_partner_config(
        self, config: TalkoContract.PartnerConfigCreate
    ) -> TalkoContract.PartnerConfigResponse:
        """
        Creates a new partner configuration and assigns DIDs if requested.
        """
        try:
            self.logger.info("Creation of partner config started.")
            self.logger.debug(
                "Creating partner config for partner_id: {}".format(config.partner_id)
            )

            # Validate and prepare config
            vendor_id: ObjectId = await TalkoPartnerConfigHelper.validate_and_prepare_config(
                config,
                self.vendor_config_validator,
                self.partner_config_validator,
                self.repository,
                self.logger,
            )
            vendor_config_id: ObjectId = ObjectId(config.vendor_config_id)

            await self.vendor_config_validator.validate_vendor_config_exists(vendor_config_id)

            if config.ai_vendor_config_id:
                await self.vendor_config_validator.validate_vendor_config_exists(
                    ObjectId(config.ai_vendor_config_id)
                )

            # Validate mutual exclusivity
            if config.enable_round_robin and config.enable_service_board:
                raise TalkoBadRequestError(
                    "Round-robin and service board cannot be enabled simultaneously."
                )

            # Validate required fields
            if config.enable_service_board and (
                not config.service_board_ids or not config.board_did_counts
            ):
                raise TalkoBadRequestError(
                    "service_board_ids and board_did_counts are required when enable_service_board is true."
                )
            if config.enable_agent_mapping and not config.agent_mapping_ids:
                raise TalkoBadRequestError(
                    "agent_mapping_ids is required when enable_agent_mapping is true."
                )
            if config.enable_round_robin and not config.round_robin_did_count:
                raise TalkoBadRequestError(
                    "round_robin_did_count is required when enable_round_robin is true."
                )

            # Handle DID assignment
            config_dict: Dict[str, Any] = (
                await TalkoPartnerConfigHelper.handle_did_assignment(
                    config,
                    vendor_id,
                    self.vendor_config_repository,
                    self.vendor_config_service,
                    self.did_management_service,
                    self.logger,
                )
            )

            # Merge input config with assigned data
            full_config: Dict[str, Any] = config.model_dump()
            full_config.update(config_dict)
            full_config["vendor_id"] = vendor_id
            full_config["vendor_config_id"] = str(vendor_config_id)
            full_config["created_at"] = self.datetime_util.get_current_time()
            full_config["updated_at"] = full_config["created_at"]

            # Format using TalkoPartnerConfigModel
            model_config: Dict[str, Any] = TalkoPartnerConfigModel(**full_config).model_dump(
                by_alias=True, exclude_unset=True
            )
            config_id: ObjectId = await self.repository.insert_partner_config(
                model_config
            )
            model_config["id"] = str(config_id)
            model_config["message"] = "Partner config created successfully."

            self.logger.info(
                "Create partner config ended successfully with ID: {}".format(config_id)
            )
            return TalkoContract.PartnerConfigResponse(**model_config)
        except Exception as e:
            self.logger.error("Error creating partner config: {}".format(str(e)))
            raise

    async def get_all_partner_configs(self) -> List[TalkoContract.PartnerDataConfigResponse]:
        """
        Retrieves all partner configurations.
        """
        self.logger.info("Get all partner config data started.")
        try:
            configs: List[Dict[str, Any]] = (
                await self.repository.find_all_partner_configs()
            )
            config_responses: List[TalkoContract.PartnerDataConfigResponse] = []
            for config in configs:
                config["id"] = str(config["_id"])
                config["vendor_id"] = str(config["vendor_id"])
                if config.get("ai_vendor_config_id") is not None:
                    config["ai_vendor_config_id"] = str(config["ai_vendor_config_id"])
                del config["_id"]
                config_responses.append(TalkoContract.PartnerDataConfigResponse(**config))
            self.logger.info("Get all partner config data ended successfully.")
            return config_responses
        except Exception as e:
            self.logger.error("Failed to retrieve partner configs: {}".format(str(e)))
            raise

    async def get_partner_config_by_id(
        self, id: str
    ) -> TalkoContract.PartnerDataConfigResponse:
        """
        Retrieves a partner configuration by its ID.
        """
        self.logger.info("Get partner config by ID started for ID: {}".format(id))
        try:
            config: Dict[str, Any] = await self.repository.find_partner_config_by_id(
                ObjectId(id)
            )
            if not config:
                self.logger.error("Partner config with ID {} not found".format(id))
                raise TalkoResourceNotFound(PARTNER_CONFIG_WITH_ID_NOT_FOUND)

            config["id"] = str(config["_id"])
            config["vendor_id"] = str(config["vendor_id"])
            if config.get("ai_vendor_config_id") is not None:
                config["ai_vendor_config_id"] = str(config["ai_vendor_config_id"])
            del config["_id"]
            self.logger.info(
                "Get partner config by ID ended successfully for ID: {}".format(id)
            )
            return TalkoContract.PartnerDataConfigResponse(**config)
        except Exception as e:
            self.logger.error(
                "Failed to retrieve partner config by ID {}: {}".format(id, str(e))
            )
            raise

    async def update_partner_config(
        self, id: str, update_data: TalkoContract.PartnerConfigUpdate
    ) -> TalkoContract.PartnerConfigResponse:
        """
        Update a partner configuration with optional attendance data.

        Args:
            id (str): The ID of the partner configuration to update.
            update_data (TalkoContract.PartnerConfigUpdate): General update data including optional attendance fields.

        Returns:
            TalkoContract.PartnerConfigResponse: The updated partner config.

        Raises:
            TalkoResourceNotFound: If the config is not found.
            Exception: For other unexpected errors.
        """
        try:
            self.logger.info(f"Updating partner config {id}")
            # Fetch existing config
            existing_config: TalkoContract.PartnerConfigResponse = (
                await self.get_partner_config_by_id(id)
            )
            if not existing_config:
                raise TalkoResourceNotFound(PARTNER_CONFIG_WITH_ID_NOT_FOUND)

            # Merge update data
            updated_config_data = existing_config.copy(deep=True)
            update_dict = update_data.model_dump(exclude_unset=True)
            updated_config_data.update(update_dict)

            # Handle attendance update if provided
            if (
                "service_default_attendance" in update_dict
                or "round_robin_default_attendance" in update_dict
            ):
                attendance_update = {
                    k: update_dict[k]
                    for k in [
                        "service_default_attendance",
                        "round_robin_default_attendance",
                    ]
                    if k in update_dict
                }
                vendor_id = ObjectId(existing_config.vendor_id)
                attendance_data = await TalkoPartnerConfigHelper.update_default_attendance(
                    updated_config_data,
                    vendor_id,
                    self.did_management_service,
                    self.logger,
                )
                if "service_default_attendance" in attendance_update:
                    updated_config_data.service_default_attendance.update(
                        attendance_update["service_default_attendance"]
                    )
                if "round_robin_default_attendance" in attendance_update:
                    updated_config_data.round_robin_default_attendance[
                        "default"
                    ].extend(
                        attendance_update["round_robin_default_attendance"].get(
                            "default", []
                        )
                    )
                updated_config_data.update(attendance_data)

            # Update the config in the repository
            model_config = TalkoPartnerConfigModel(
                **updated_config_data.model_dump()
            ).model_dump(by_alias=True, exclude_unset=True)
            model_config["updated_at"] = self.datetime_util.get_current_time()
            updated_doc = await self.repository.update_partner_config(id, model_config)
            updated_config_data.id = id
            updated_config_data.updated_at = model_config["updated_at"]
            updated_config_data.vendor_id = str(vendor_id)

            self.logger.info(f"Partner config {id} updated successfully")
            return TalkoContract.PartnerConfigResponse(**updated_config_data.model_dump())
        except TalkoResourceNotFound as e:
            self.logger.error(f"Partner config {id} not found: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error updating partner config {id}: {str(e)}")
            raise
