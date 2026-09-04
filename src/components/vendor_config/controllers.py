from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, status

from src.components.common.constants import CurrentUserMap
from src.components.common.responses import (
    BadRequestResponse,
    InternalServerErrorResponse,
    ResourceCreatedResponse,
    ResourceNotFoundResponse,
    SuccessResponse,
)
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.vendor_config.dto import Contract
from src.components.vendor_config.message import (
    NO_FIELDS_PROVIDED_FOR_UPDATE,
    NOT_FOUND,
    SOMETHING_WENT_WRONG,
)
from src.components.vendor_config.services import VendorConfigService
from src.core.container import Container
from src.exceptions import BadRequestError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger


class VendorConfigController:
    vendor_config_router = APIRouter()

    @vendor_config_router.post(
        "",
        response_model=Contract.VendorConfigCreationUpdationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(PermissionDependency)
    @inject
    async def create_vendor_config(
        request: Request,
        config_data: Contract.VendorConfigCreate,
        vendor_config_service: VendorConfigService = Depends(
            Provide[Container.vendor_config_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.VendorConfigCreationUpdationResponse:
        try:
            holler_service_logger.info(
                "Received vendor config data: {}.".format(config_data)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, create vendor config api initiated.".format(
                    user_id, partner_id
                )
            )
            created_config: Contract.VendorConfigCreationUpdationResponse = (
                await vendor_config_service.create_vendor_config(config_data)
            )
            holler_service_logger.info(
                "Vendor config created successfully: {}".format(created_config)
            )
            return ResourceCreatedResponse(data=created_config)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error creating vendor config: {}.".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @vendor_config_router.get("", response_model=list[Contract.GetAllVendorConfigData])
    @permission_check(PermissionDependency)
    @inject
    async def get_all_vendor_configs(
        request: Request,
        vendor_config_service: VendorConfigService = Depends(
            Provide[Container.vendor_config_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> list[Contract.GetAllVendorConfigData]:
        try:
            holler_service_logger.info("Retrieving all vendor configs data.")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, get all vendor config api initiated".format(
                    user_id, partner_id
                )
            )
            configs: list[Contract.GetAllVendorConfigData] = (
                await vendor_config_service.get_all_configs()
            )
            holler_service_logger.info(
                "Retrieved {} vendor configs.".format(len(configs))
            )
            return SuccessResponse(data=configs)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving vendor configs: {}.".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @vendor_config_router.get("/{id}", response_model=Contract.VendorConfigResponse)
    @permission_check(PermissionDependency)
    @inject
    async def get_vendor_configs_by_id(
        request: Request,
        id: str,
        vendor_config_service: VendorConfigService = Depends(
            Provide[Container.vendor_config_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.VendorConfigResponse:
        try:
            holler_service_logger.info(
                "Retrieving vendor configs for vendor_id: {}.".format(id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, get vendor configs by id api initiated.".format(
                    user_id, partner_id
                )
            )
            configs: Contract.VendorConfigResponse = (
                await vendor_config_service.get_config_by_id(id)
            )
            holler_service_logger.info(
                "Retrieved configs for vendor_id: {}.".format(id)
            )
            return SuccessResponse(data=configs)
        except ValueError as e:
            holler_service_logger.error(
                "Error in get vendor config by id: {}".format(str(e))
            )
            return BadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except ResourceNotFound as e:
            holler_service_logger.error("No vendor config found for id {}".format(id))
            return ResourceNotFoundResponse(detail=NOT_FOUND)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving vendor configs: {}.".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @vendor_config_router.patch(
        "/{id}", response_model=Contract.VendorConfigCreationUpdationResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def update_vendor_config(
        request: Request,
        id: str,
        update_data: Contract.VendorConfigUpdate,
        vendor_config_service: VendorConfigService = Depends(
            Provide[Container.vendor_config_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.VendorConfigCreationUpdationResponse:
        try:
            holler_service_logger.info(
                "Updating vendor config for vendor_id: {}.".format(id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, update vendor config by id.".format(
                    user_id, partner_id
                )
            )
            updated_config: Contract.VendorConfigCreationUpdationResponse = (
                await vendor_config_service.update_vendor_config(id, update_data)
            )
            holler_service_logger.info(
                "Vendor config updated successfully: {}.".format(updated_config)
            )
            return SuccessResponse(data=updated_config)
        except ValueError as e:
            holler_service_logger.error(
                "Error in updating vendor config: {}".format(str(e))
            )
            return BadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except ResourceNotFound as e:
            return ResourceNotFoundResponse(detail=NOT_FOUND)
        except BadRequestError as e:
            holler_service_logger.error(NO_FIELDS_PROVIDED_FOR_UPDATE)
            return BadRequestResponse(detail=NO_FIELDS_PROVIDED_FOR_UPDATE)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error updating vendor config: {}.".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
