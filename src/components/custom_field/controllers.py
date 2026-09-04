from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status

from src.components.common.constants import CurrentUserMap
from src.components.common.responses import (
    BadRequestResponse,
    InternalServerErrorResponse,
    ResourceConflictResponse,
    ResourceCreatedResponse,
    ResourceNotFoundResponse,
    SuccessResponse,
)
from src.components.custom_field.constants import CustomFieldEntityType
from src.components.custom_field.dto import Contract
from src.components.custom_field.message import NOT_FOUND, SOMETHING_WENT_WRONG
from src.components.custom_field.services import CustomFieldService
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import BadRequestError, DuplicateResourceError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger


class CustomFieldController:
    custom_field_router = APIRouter()

    @custom_field_router.post(
        "",
        response_model=Contract.CustomFieldCreationUpdationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(PermissionDependency)
    @inject
    async def create_custom_field(
        request: Request,
        field_data: Contract.CustomFieldCreate,
        custom_field_service: CustomFieldService = Depends(
            Provide[Container.custom_field_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.CustomFieldCreationUpdationResponse:
        try:
            current_user_data: dict = request.state.user
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "Partner: {}, create custom field api initiated. data: {}".format(
                    partner_id, field_data
                )
            )
            created_field: Contract.CustomFieldCreationUpdationResponse = (
                await custom_field_service.create_custom_field(partner_id, field_data)
            )
            return ResourceCreatedResponse(data=created_field)
        except BadRequestError as e:
            return BadRequestResponse(detail=str(e))
        except DuplicateResourceError as e:
            return ResourceConflictResponse(detail=str(e))
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error creating custom field: {}.".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @custom_field_router.get("", response_model=list[Contract.CustomFieldResponse])
    @permission_check(PermissionDependency)
    @inject
    async def get_custom_fields(
        request: Request,
        entity_type: CustomFieldEntityType = Query(
            ..., description="Entity type to fetch custom field definitions for"
        ),
        custom_field_service: CustomFieldService = Depends(
            Provide[Container.custom_field_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> list[Contract.CustomFieldResponse]:
        try:
            current_user_data: dict = request.state.user
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "Partner: {}, entity_type: {}, get custom fields api initiated.".format(
                    partner_id, entity_type
                )
            )
            fields: list[Contract.CustomFieldResponse] = (
                await custom_field_service.get_custom_fields(
                    partner_id, entity_type.value
                )
            )
            return SuccessResponse(data=fields)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving custom fields: {}.".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @custom_field_router.patch(
        "/{field_id}", response_model=Contract.CustomFieldCreationUpdationResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def update_custom_field(
        request: Request,
        field_id: str,
        update_data: Contract.CustomFieldUpdate,
        custom_field_service: CustomFieldService = Depends(
            Provide[Container.custom_field_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.CustomFieldCreationUpdationResponse:
        try:
            current_user_data: dict = request.state.user
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "Partner: {}, update custom field {} api initiated. data: {}".format(
                    partner_id, field_id, update_data
                )
            )
            updated_field: Contract.CustomFieldCreationUpdationResponse = (
                await custom_field_service.update_custom_field(
                    partner_id, field_id, update_data
                )
            )
            return SuccessResponse(data=updated_field)
        except BadRequestError as e:
            return BadRequestResponse(detail=str(e))
        except ResourceNotFound as e:
            return ResourceNotFoundResponse(detail=NOT_FOUND)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error updating custom field: {}.".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @custom_field_router.delete(
        "/{field_id}", response_model=Contract.CustomFieldCreationUpdationResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def delete_custom_field(
        request: Request,
        field_id: str,
        custom_field_service: CustomFieldService = Depends(
            Provide[Container.custom_field_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.CustomFieldCreationUpdationResponse:
        try:
            current_user_data: dict = request.state.user
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "Partner: {}, delete custom field {} api initiated.".format(
                    partner_id, field_id
                )
            )
            deleted_field: Contract.CustomFieldCreationUpdationResponse = (
                await custom_field_service.delete_custom_field(partner_id, field_id)
            )
            return SuccessResponse(data=deleted_field)
        except BadRequestError as e:
            return BadRequestResponse(detail=str(e))
        except ResourceNotFound as e:
            return ResourceNotFoundResponse(detail=NOT_FOUND)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error deleting custom field: {}.".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
