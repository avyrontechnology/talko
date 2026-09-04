from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Request, status

from src.components.common.constants import CurrentUserMap
from src.components.common.responses import (
    BadRequestResponse,
    InternalServerErrorResponse,
    ResourceCreatedResponse,
    ResourceNotFoundResponse,
    SuccessResponse,
)
from src.components.partner_config.dto import Contract
from src.components.partner_config.message import (
    NO_FIELD_PROVIDED_FOR_UPDATE,
    PARTNER_CONFIG_WITH_ID_NOT_FOUND,
    PARTNER_CONFIG_WITH_PARTNER_ID_ALREADY_EXIST,
    SOMETHING_WENT_WRONG,
)
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import BadRequestError, ConflictError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger

from .services import PartnerConfigService


class PartnerConfigController:
    """
    Controller for managing partner configuration routes.
    Provides endpoints for creating, retrieving, updating,
    and managing partner configurations and DID assignments.
    """

    router = APIRouter()

    @router.post(
        "",
        response_model=Contract.PartnerConfigResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(PermissionDependency)
    @inject
    async def create_partner_config(
        request: Request,
        config_data: Contract.PartnerConfigCreate,
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.PartnerConfigResponse:
        """
        Create a new partner configuration.

        - Validates the vendor ID.
        - Optionally assigns available DIDs to the new config.
        """
        try:
            holler_service_logger.info(
                "Received partner config data: {}".format(config_data)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, create partner config api initiated.".format(
                    user_id, partner_id
                )
            )
            created_config: Contract.PartnerConfigResponse = (
                await partner_config_service.create_partner_config(config_data)
            )
            holler_service_logger.info(
                "Partner config created successfully: {}".format(created_config)
            )
            return ResourceCreatedResponse(data=created_config)

        except ValueError as e:
            holler_service_logger.error(
                "Error in partner config creation: {}.".format(str(e))
            )
            return BadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except ConflictError as e:
            holler_service_logger.error(PARTNER_CONFIG_WITH_PARTNER_ID_ALREADY_EXIST)
            return BadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error creating partner config: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.get("", response_model=list[Contract.PartnerConfigResponse])
    @permission_check(PermissionDependency)
    @inject
    async def get_all_partner_configs(
        request: Request,
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> list[Contract.PartnerConfigResponse]:
        """
        Retrieve all partner configurations.
        """
        try:
            holler_service_logger.info("Retrieving all partner configs")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, get all partner config api initiated.".format(
                    user_id, partner_id
                )
            )
            configs: list[Contract.PartnerConfigResponse] = (
                await partner_config_service.get_all_partner_configs()
            )
            holler_service_logger.info(
                "Retrieved {} partner configs.".format(len(configs))
            )
            return SuccessResponse(data=configs)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving partner configs: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.get("/{id}", response_model=Contract.PartnerConfigResponse)
    @permission_check(PermissionDependency)
    @inject
    async def get_partner_config_by_id(
        request: Request,
        id: str,
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.PartnerConfigResponse:
        """
        Retrieve a single partner configuration by its ID.
        """
        try:
            holler_service_logger.info(
                "Retrieving partner config for partner_id: {}".format(id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, get partner config by id api initiated.".format(
                    user_id, partner_id
                )
            )
            config: Contract.PartnerConfigResponse = (
                await partner_config_service.get_partner_config_by_id(id)
            )
            holler_service_logger.info(
                "Partner config retrieved successfully: {}".format(config)
            )
            return SuccessResponse(data=config)
        except ValueError as e:
            holler_service_logger.error(
                "Error in partner config get partner by id: {}.".format(str(e))
            )
            return BadRequestResponse(detail=str(e))
        except ResourceNotFound as e:
            holler_service_logger.error(PARTNER_CONFIG_WITH_ID_NOT_FOUND)
            return ResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving partner config: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.patch("/{id}", response_model=Contract.PartnerConfigResponse)
    @permission_check(PermissionDependency)
    @inject
    async def update_partner_config(
        request: Request,
        id: str,
        update_data: Contract.PartnerConfigUpdate,
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.PartnerConfigResponse:
        """
        Update a partner configuration using provided fields.

        - Allows partial updates.
        - Validates the vendor ID if included.
        """
        try:
            holler_service_logger.info(
                "Updating partner config for partner_id: {}".format(id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, update partner config api initiated.".format(
                    user_id, partner_id
                )
            )
            updated_config: Contract.PartnerConfigResponse = (
                await partner_config_service.update_partner_config(id, update_data)
            )
            holler_service_logger.info(
                "Partner config updated successfully: {}".format(updated_config)
            )
            return SuccessResponse(data=updated_config)
        except ValueError as e:
            holler_service_logger.error(
                "Error in partner config creation: {}.".format(str(e))
            )
            return BadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except ResourceNotFound as e:
            holler_service_logger.error(PARTNER_CONFIG_WITH_ID_NOT_FOUND)
            return ResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except BadRequestError as e:
            holler_service_logger.error(NO_FIELD_PROVIDED_FOR_UPDATE)
            return BadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error updating partner config: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
