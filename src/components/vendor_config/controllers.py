from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, status

from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceCreatedResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.vendor_config.dto import TalkoContract
from src.components.vendor_config.message import (
    NO_FIELDS_PROVIDED_FOR_UPDATE,
    NOT_FOUND,
    SOMETHING_WENT_WRONG,
)
from src.components.vendor_config.services import TalkoVendorConfigService
from src.core.container import TalkoContainer
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoVendorConfigController:
    vendor_config_router = APIRouter()

    @vendor_config_router.post(
        "",
        response_model=TalkoContract.VendorConfigCreationUpdationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def create_vendor_config(
        request: Request,
        config_data: TalkoContract.VendorConfigCreate,
        vendor_config_service: TalkoVendorConfigService = Depends(
            Provide[TalkoContainer.vendor_config_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.VendorConfigCreationUpdationResponse:
        try:
            talko_service_logger.info(
                "Received vendor config data: {}.".format(config_data)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, create vendor config api initiated.".format(
                    user_id, partner_id
                )
            )
            created_config: TalkoContract.VendorConfigCreationUpdationResponse = (
                await vendor_config_service.create_vendor_config(config_data)
            )
            talko_service_logger.info(
                "Vendor config created successfully: {}".format(created_config)
            )
            return TalkoResourceCreatedResponse(data=created_config)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error creating vendor config: {}.".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @vendor_config_router.get("", response_model=list[TalkoContract.GetAllVendorConfigData])
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_all_vendor_configs(
        request: Request,
        vendor_config_service: TalkoVendorConfigService = Depends(
            Provide[TalkoContainer.vendor_config_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> list[TalkoContract.GetAllVendorConfigData]:
        try:
            talko_service_logger.info("Retrieving all vendor configs data.")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, get all vendor config api initiated".format(
                    user_id, partner_id
                )
            )
            configs: list[TalkoContract.GetAllVendorConfigData] = (
                await vendor_config_service.get_all_configs()
            )
            talko_service_logger.info(
                "Retrieved {} vendor configs.".format(len(configs))
            )
            return TalkoSuccessResponse(data=configs)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error retrieving vendor configs: {}.".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @vendor_config_router.get("/{id}", response_model=TalkoContract.VendorConfigResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_vendor_configs_by_id(
        request: Request,
        id: str,
        vendor_config_service: TalkoVendorConfigService = Depends(
            Provide[TalkoContainer.vendor_config_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.VendorConfigResponse:
        try:
            talko_service_logger.info(
                "Retrieving vendor configs for vendor_id: {}.".format(id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, get vendor configs by id api initiated.".format(
                    user_id, partner_id
                )
            )
            configs: TalkoContract.VendorConfigResponse = (
                await vendor_config_service.get_config_by_id(id)
            )
            talko_service_logger.info(
                "Retrieved configs for vendor_id: {}.".format(id)
            )
            return TalkoSuccessResponse(data=configs)
        except ValueError as e:
            talko_service_logger.error(
                "Error in get vendor config by id: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except TalkoResourceNotFound as e:
            talko_service_logger.error("No vendor config found for id {}".format(id))
            return TalkoResourceNotFoundResponse(detail=NOT_FOUND)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error retrieving vendor configs: {}.".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @vendor_config_router.patch(
        "/{id}", response_model=TalkoContract.VendorConfigCreationUpdationResponse
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def update_vendor_config(
        request: Request,
        id: str,
        update_data: TalkoContract.VendorConfigUpdate,
        vendor_config_service: TalkoVendorConfigService = Depends(
            Provide[TalkoContainer.vendor_config_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.VendorConfigCreationUpdationResponse:
        try:
            talko_service_logger.info(
                "Updating vendor config for vendor_id: {}.".format(id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, update vendor config by id.".format(
                    user_id, partner_id
                )
            )
            updated_config: TalkoContract.VendorConfigCreationUpdationResponse = (
                await vendor_config_service.update_vendor_config(id, update_data)
            )
            talko_service_logger.info(
                "Vendor config updated successfully: {}.".format(updated_config)
            )
            return TalkoSuccessResponse(data=updated_config)
        except ValueError as e:
            talko_service_logger.error(
                "Error in updating vendor config: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except TalkoResourceNotFound as e:
            return TalkoResourceNotFoundResponse(detail=NOT_FOUND)
        except TalkoBadRequestError as e:
            talko_service_logger.error(NO_FIELDS_PROVIDED_FOR_UPDATE)
            return TalkoBadRequestResponse(detail=NO_FIELDS_PROVIDED_FOR_UPDATE)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error updating vendor config: {}.".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
