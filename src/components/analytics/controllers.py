import json

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request

from src.components.analytics import messages as analytics_messages
from src.components.analytics.dto import TalkoAnalyticsRequest, TalkoAnalyticsResponse
from src.components.analytics.enums import TalkoAnalyticsType
from src.components.analytics.services import TalkoAnalyticsService
from src.components.common.constants import TalkoPaginationConstants
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoForbiddenPermissionResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import TalkoContainer
from src.exceptions import (
    TalkoBadRequestError,
    TalkoInvalidAnalyticTypeError,
    TalkoInvalidPermissionTypeError,
    TalkoPayloadValidationError,
    TalkoResourceNotFound,
)
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoAnalyticsController:
    """Controller to handle analytics-related API endpoints."""

    router = APIRouter()

    @router.get(
        "",
        response_model=TalkoAnalyticsResponse,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_analytics(
        request: Request,
        analytics_type: TalkoAnalyticsType = Query(
            ..., description="Analytic type to retrieve"
        ),
        payload: str = Query(
            ...,
            description='Analytic-specific data as JSON string (e.g., {"time_range": "1749148200000-1756992444404", "service_board_id": [40]})',
        ),
        offset: int = Query(
            TalkoPaginationConstants.offset,
            ge=TalkoPaginationConstants.offset,
            description="Page number for pagination",
        ),
        limit: int = Query(
            TalkoPaginationConstants.limit,
            ge=TalkoPaginationConstants.offset,
            le=TalkoPaginationConstants.LIMIT_MAX,
            description="Number of items per page",
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
        analytics_service: "TalkoAnalyticsService" = Depends(
            Provide[TalkoContainer.analytics_service]
        ),
    ) -> TalkoAnalyticsResponse:
        try:
            talko_service_logger.info(
                "Received analytics request: analytics_type={}, payload={}, limit={}, offset={}".format(
                    analytics_type.value, payload, limit, offset
                )
            )
            current_user_detail: dict = request.state.user
            talko_service_logger.debug(
                "Current user details: {}".format(current_user_detail)
            )
            current_user_id: int = current_user_detail.get("user_id")
            partner_id: int = current_user_detail.get("partner_id")

            try:
                data_dict = json.loads(payload)
            except json.JSONDecodeError as e:
                talko_service_logger.error(f"Error in parsing JSON payload: {str(e)}")
                return TalkoBadRequestResponse(
                    detail="Data must be a valid JSON string. Example: {{'start_date': {}, 'end_date': {}, 'agents': {}}}".format(
                        1625097600, 1627689600, [1, 2, 3]
                    )
                )

            analytics_request = TalkoAnalyticsRequest(
                analytics_type=analytics_type.value, data=data_dict
            ).model_dump()

            result: TalkoAnalyticsResponse = await analytics_service.get_analytics(
                current_user_id=current_user_id,
                partner_id=partner_id,
                analytics_request=analytics_request,
                limit=limit,
                offset=offset,
            )

            talko_service_logger.info(
                "Successfully processed analytics request for partner_id: {}".format(
                    partner_id
                )
            )
            return TalkoSuccessResponse(data=result)
        except TalkoInvalidAnalyticTypeError as e:
            talko_service_logger.error("Invalid analytics type: {}".format(str(e)))
            return TalkoBadRequestResponse(
                detail=analytics_messages.INVALID_ANALYTIC_TYPE_ERROR
            )
        except TalkoPayloadValidationError as e:
            talko_service_logger.error(
                "Payload validation error: {}".format(e.message)
            )
            return TalkoBadRequestResponse(
                detail=analytics_messages.PAYLOAD_VALIDATION_ERROR
            )
        except TalkoResourceNotFound as e:
            talko_service_logger.error(
                "Resource not found while processing analytics: {}".format(str(e))
            )
            return TalkoResourceNotFoundResponse(
                detail=analytics_messages.RESOURCE_NOT_FOUND_ERROR
            )
        except TalkoBadRequestError as e:
            talko_service_logger.error(
                "Bad request while processing analytics: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=analytics_messages.BAD_REQUEST_ERROR)
        except TalkoInvalidPermissionTypeError as e:
            talko_service_logger.error("Error in getting analytics: {}".format(str(e)))
            return TalkoForbiddenPermissionResponse(
                detail=analytics_messages.INVALID_PERMISSION_ERROR
            )
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error occurred while processing analytics: {}".format(
                    str(e)
                )
            )
            return TalkoInternalServerErrorResponse(
                detail=analytics_messages.EXCEPTION_ERROR
            )
