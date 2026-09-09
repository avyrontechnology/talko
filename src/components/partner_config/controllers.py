from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends, Request, status

from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoForbiddenPermissionResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceCreatedResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.partner_config.dto import TalkoContract
from src.components.partner_config.message import (
    NO_FIELD_PROVIDED_FOR_UPDATE,
    PARTNER_CONFIG_WITH_ID_NOT_FOUND,
    PARTNER_CONFIG_WITH_PARTNER_ID_ALREADY_EXIST,
    SOMETHING_WENT_WRONG,
)
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.rbac.superadmin import (
    TalkoSuperadminDenied,
    resolve_effective_partner_id,
)
from src.core.container import TalkoContainer
from src.exceptions import TalkoBadRequestError, TalkoConflictError, TalkoResourceNotFound
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger

from .services import TalkoPartnerConfigService


class TalkoPartnerConfigController:
    """
    Controller for managing partner configuration routes.
    Provides endpoints for creating, retrieving, updating,
    and managing partner configurations and DID assignments.
    """

    router = APIRouter()

    @router.post(
        "",
        response_model=TalkoContract.PartnerConfigResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def create_partner_config(
        request: Request,
        config_data: TalkoContract.PartnerConfigCreate,
        partner_config_service: TalkoPartnerConfigService = Depends(
            Provide[TalkoContainer.partner_config_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.PartnerConfigResponse:
        """
        Create a new partner configuration.

        - Validates the vendor ID.
        - Optionally assigns available DIDs to the new config.
        """
        try:
            talko_service_logger.info(
                "Received partner config data: {}".format(config_data)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, create partner config api initiated.".format(
                    user_id, partner_id
                )
            )
            # Body carries the target partner: superadmins may onboard any
            # partner, everyone else only their own scope.
            grpc_client = TalkoRPCServiceFactory.get_service(TalkoGrpcServices.AUTH)
            try:
                await resolve_effective_partner_id(
                    request, grpc_client, talko_service_logger, config_data.partner_id
                )
            except TalkoSuperadminDenied as denied:
                return TalkoForbiddenPermissionResponse(detail=str(denied))
            created_config: TalkoContract.PartnerConfigResponse = (
                await partner_config_service.create_partner_config(config_data)
            )
            talko_service_logger.info(
                "Partner config created successfully: {}".format(created_config)
            )
            return TalkoResourceCreatedResponse(data=created_config)

        except ValueError as e:
            talko_service_logger.error(
                "Error in partner config creation: {}.".format(str(e))
            )
            return TalkoBadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except TalkoConflictError as e:
            talko_service_logger.error(PARTNER_CONFIG_WITH_PARTNER_ID_ALREADY_EXIST)
            return TalkoBadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error creating partner config: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.get("", response_model=list[TalkoContract.PartnerConfigResponse])
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_all_partner_configs(
        request: Request,
        partner_config_service: TalkoPartnerConfigService = Depends(
            Provide[TalkoContainer.partner_config_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> list[TalkoContract.PartnerConfigResponse]:
        """
        Retrieve all partner configurations.
        """
        try:
            talko_service_logger.info("Retrieving all partner configs")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, get all partner config api initiated.".format(
                    user_id, partner_id
                )
            )
            configs: list[TalkoContract.PartnerConfigResponse] = (
                await partner_config_service.get_all_partner_configs()
            )
            talko_service_logger.info(
                "Retrieved {} partner configs.".format(len(configs))
            )
            return TalkoSuccessResponse(data=configs)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error retrieving partner configs: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.get("/{id}", response_model=TalkoContract.PartnerConfigResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_partner_config_by_id(
        request: Request,
        id: str,
        partner_config_service: TalkoPartnerConfigService = Depends(
            Provide[TalkoContainer.partner_config_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.PartnerConfigResponse:
        """
        Retrieve a single partner configuration by its ID.
        """
        try:
            talko_service_logger.info(
                "Retrieving partner config for partner_id: {}".format(id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, get partner config by id api initiated.".format(
                    user_id, partner_id
                )
            )
            config: TalkoContract.PartnerConfigResponse = (
                await partner_config_service.get_partner_config_by_id(id)
            )
            talko_service_logger.info(
                "Partner config retrieved successfully: {}".format(config)
            )
            return TalkoSuccessResponse(data=config)
        except ValueError as e:
            talko_service_logger.error(
                "Error in partner config get partner by id: {}.".format(str(e))
            )
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoResourceNotFound as e:
            talko_service_logger.error(PARTNER_CONFIG_WITH_ID_NOT_FOUND)
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error retrieving partner config: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.patch("/{id}", response_model=TalkoContract.PartnerConfigResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def update_partner_config(
        request: Request,
        id: str,
        update_data: TalkoContract.PartnerConfigUpdate,
        partner_config_service: TalkoPartnerConfigService = Depends(
            Provide[TalkoContainer.partner_config_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.PartnerConfigResponse:
        """
        Update a partner configuration using provided fields.

        - Allows partial updates.
        - Validates the vendor ID if included.
        """
        try:
            talko_service_logger.info(
                "Updating partner config for partner_id: {}".format(id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, update partner config api initiated.".format(
                    user_id, partner_id
                )
            )
            updated_config: TalkoContract.PartnerConfigResponse = (
                await partner_config_service.update_partner_config(id, update_data)
            )
            talko_service_logger.info(
                "Partner config updated successfully: {}".format(updated_config)
            )
            return TalkoSuccessResponse(data=updated_config)
        except ValueError as e:
            talko_service_logger.error(
                "Error in partner config creation: {}.".format(str(e))
            )
            return TalkoBadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except TalkoResourceNotFound as e:
            talko_service_logger.error(PARTNER_CONFIG_WITH_ID_NOT_FOUND)
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except TalkoBadRequestError as e:
            talko_service_logger.error(NO_FIELD_PROVIDED_FOR_UPDATE)
            return TalkoBadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error updating partner config: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
