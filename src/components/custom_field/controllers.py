from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status

from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceConflictResponse,
    TalkoResourceCreatedResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.custom_field.constants import TalkoCustomFieldEntityType
from src.components.custom_field.dto import TalkoContract
from src.components.custom_field.message import NOT_FOUND, SOMETHING_WENT_WRONG
from src.components.custom_field.services import TalkoCustomFieldService
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import TalkoContainer
from src.exceptions import TalkoBadRequestError, TalkoDuplicateResourceError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoCustomFieldController:
    custom_field_router = APIRouter()

    @custom_field_router.post(
        "",
        response_model=TalkoContract.CustomFieldCreationUpdationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def create_custom_field(
        request: Request,
        field_data: TalkoContract.CustomFieldCreate,
        custom_field_service: TalkoCustomFieldService = Depends(
            Provide[TalkoContainer.custom_field_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.CustomFieldCreationUpdationResponse:
        try:
            current_user_data: dict = request.state.user
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "Partner: {}, create custom field api initiated. data: {}".format(
                    partner_id, field_data
                )
            )
            created_field: TalkoContract.CustomFieldCreationUpdationResponse = (
                await custom_field_service.create_custom_field(partner_id, field_data)
            )
            return TalkoResourceCreatedResponse(data=created_field)
        except TalkoBadRequestError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoDuplicateResourceError as e:
            return TalkoResourceConflictResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error creating custom field: {}.".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @custom_field_router.get("", response_model=list[TalkoContract.CustomFieldResponse])
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_custom_fields(
        request: Request,
        entity_type: TalkoCustomFieldEntityType = Query(
            ..., description="Entity type to fetch custom field definitions for"
        ),
        custom_field_service: TalkoCustomFieldService = Depends(
            Provide[TalkoContainer.custom_field_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> list[TalkoContract.CustomFieldResponse]:
        try:
            current_user_data: dict = request.state.user
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "Partner: {}, entity_type: {}, get custom fields api initiated.".format(
                    partner_id, entity_type
                )
            )
            fields: list[TalkoContract.CustomFieldResponse] = (
                await custom_field_service.get_custom_fields(
                    partner_id, entity_type.value
                )
            )
            return TalkoSuccessResponse(data=fields)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error retrieving custom fields: {}.".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @custom_field_router.patch(
        "/{field_id}", response_model=TalkoContract.CustomFieldCreationUpdationResponse
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def update_custom_field(
        request: Request,
        field_id: str,
        update_data: TalkoContract.CustomFieldUpdate,
        custom_field_service: TalkoCustomFieldService = Depends(
            Provide[TalkoContainer.custom_field_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.CustomFieldCreationUpdationResponse:
        try:
            current_user_data: dict = request.state.user
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "Partner: {}, update custom field {} api initiated. data: {}".format(
                    partner_id, field_id, update_data
                )
            )
            updated_field: TalkoContract.CustomFieldCreationUpdationResponse = (
                await custom_field_service.update_custom_field(
                    partner_id, field_id, update_data
                )
            )
            return TalkoSuccessResponse(data=updated_field)
        except TalkoBadRequestError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoResourceNotFound as e:
            return TalkoResourceNotFoundResponse(detail=NOT_FOUND)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error updating custom field: {}.".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @custom_field_router.delete(
        "/{field_id}", response_model=TalkoContract.CustomFieldCreationUpdationResponse
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def delete_custom_field(
        request: Request,
        field_id: str,
        custom_field_service: TalkoCustomFieldService = Depends(
            Provide[TalkoContainer.custom_field_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.CustomFieldCreationUpdationResponse:
        try:
            current_user_data: dict = request.state.user
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "Partner: {}, delete custom field {} api initiated.".format(
                    partner_id, field_id
                )
            )
            deleted_field: TalkoContract.CustomFieldCreationUpdationResponse = (
                await custom_field_service.delete_custom_field(partner_id, field_id)
            )
            return TalkoSuccessResponse(data=deleted_field)
        except TalkoBadRequestError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoResourceNotFound as e:
            return TalkoResourceNotFoundResponse(detail=NOT_FOUND)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error deleting custom field: {}.".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
