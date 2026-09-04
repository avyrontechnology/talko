import json

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request

from src.components.analytics import messages as analytics_messages
from src.components.analytics.dto import AnalyticsRequest, AnalyticsResponse
from src.components.analytics.enums import AnalyticsType
from src.components.analytics.services import AnalyticsService
from src.components.common.constants import PaginationConstants
from src.components.common.responses import (
    BadRequestResponse,
    ForbiddenPermissionResponse,
    InternalServerErrorResponse,
    ResourceNotFoundResponse,
    SuccessResponse,
)
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import (
    BadRequestError,
    InvalidAnalyticTypeError,
    InvalidPermissionTypeError,
    PayloadValidationError,
    ResourceNotFound,
)
from src.loggers.holler_service_logger import HollerServiceLogger


class AnalyticsController:
    """Controller to handle analytics-related API endpoints."""

    router = APIRouter()

    @router.get(
        "",
        response_model=AnalyticsResponse,
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_analytics(
        request: Request,
        analytics_type: AnalyticsType = Query(
            ..., description="Analytic type to retrieve"
        ),
        payload: str = Query(
            ...,
            description='Analytic-specific data as JSON string (e.g., {"time_range": "1749148200000-1756992444404", "service_board_id": [40]})',
        ),
        offset: int = Query(
            PaginationConstants.offset,
            ge=PaginationConstants.offset,
            description="Page number for pagination",
        ),
        limit: int = Query(
            PaginationConstants.limit,
            ge=PaginationConstants.offset,
            le=PaginationConstants.LIMIT_MAX,
            description="Number of items per page",
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
        analytics_service: "AnalyticsService" = Depends(
            Provide[Container.analytics_service]
        ),
    ) -> AnalyticsResponse:
        try:
            holler_service_logger.info(
                "Received analytics request: analytics_type={}, payload={}, limit={}, offset={}".format(
                    analytics_type.value, payload, limit, offset
                )
            )
            current_user_detail: dict = request.state.user
            holler_service_logger.debug(
                "Current user details: {}".format(current_user_detail)
            )
            current_user_id: int = current_user_detail.get("user_id")
            partner_id: int = current_user_detail.get("partner_id")

            try:
                data_dict = json.loads(payload)
            except json.JSONDecodeError as e:
                holler_service_logger.error(f"Error in parsing JSON payload: {str(e)}")
                return BadRequestResponse(
                    detail="Data must be a valid JSON string. Example: {{'start_date': {}, 'end_date': {}, 'agents': {}}}".format(
                        1625097600, 1627689600, [1, 2, 3]
                    )
                )

            analytics_request = AnalyticsRequest(
                analytics_type=analytics_type.value, data=data_dict
            ).model_dump()

            result: AnalyticsResponse = await analytics_service.get_analytics(
                current_user_id=current_user_id,
                partner_id=partner_id,
                analytics_request=analytics_request,
                limit=limit,
                offset=offset,
            )

            holler_service_logger.info(
                "Successfully processed analytics request for partner_id: {}".format(
                    partner_id
                )
            )
            return SuccessResponse(data=result)
        except InvalidAnalyticTypeError as e:
            holler_service_logger.error("Invalid analytics type: {}".format(str(e)))
            return BadRequestResponse(
                detail=analytics_messages.INVALID_ANALYTIC_TYPE_ERROR
            )
        except PayloadValidationError as e:
            holler_service_logger.error(
                "Payload validation error: {}".format(e.message)
            )
            return BadRequestResponse(
                detail=analytics_messages.PAYLOAD_VALIDATION_ERROR
            )
        except ResourceNotFound as e:
            holler_service_logger.error(
                "Resource not found while processing analytics: {}".format(str(e))
            )
            return ResourceNotFoundResponse(
                detail=analytics_messages.RESOURCE_NOT_FOUND_ERROR
            )
        except BadRequestError as e:
            holler_service_logger.error(
                "Bad request while processing analytics: {}".format(str(e))
            )
            return BadRequestResponse(detail=analytics_messages.BAD_REQUEST_ERROR)
        except InvalidPermissionTypeError as e:
            holler_service_logger.error("Error in getting analytics: {}".format(str(e)))
            return ForbiddenPermissionResponse(
                detail=analytics_messages.INVALID_PERMISSION_ERROR
            )
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error occurred while processing analytics: {}".format(
                    str(e)
                )
            )
            return InternalServerErrorResponse(
                detail=analytics_messages.EXCEPTION_ERROR
            )
