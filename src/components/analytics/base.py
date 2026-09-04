import json
from typing import Any, Awaitable, Callable, Dict, Type, Union

from pydantic import BaseModel, ValidationError

from src.components.analytics.dto import (
    AgentCallAnalyticsRequest,
    AgentTalkTimeDistributionRequest,
    AnalyticsResponse,
    DashboardFollowupTrendsRequest,
    PartnerServiceBoardRequest,
    TotalAgentTalkTimeRequest,
)
from src.components.analytics.enums import AnalyticsType
from src.components.analytics.processor import AnalyticsProcessor
from src.exceptions import InvalidAnalyticTypeError, PayloadValidationError
from src.loggers.holler_service_logger import HollerServiceLogger


class AnalyticsBase:
    def __init__(
        self,
        analytics_processor: "AnalyticsProcessor",
        logger: HollerServiceLogger,
    ) -> None:
        self.__analytics_processor: AnalyticsProcessor = analytics_processor
        self.__holler_service_logger: HollerServiceLogger = logger

    async def process_analytics(
        self,
        current_user_id: int,
        partner_id: int,
        analytics_request: Dict[str, Any],
        limit: int,
        offset: int,
    ) -> AnalyticsResponse:
        analytics_type: Union[str, None] = analytics_request.get("analytics_type")
        data: Dict[str, Any] = analytics_request.get("data", {})

        mappings: Dict[str, Dict[str, Any]] = {
            AnalyticsType.AGENT_CALL_ANALYTICS.value: {
                "schema": AgentCallAnalyticsRequest,
                "method": self.__analytics_processor._get_agent_call_analytics,
            },
            AnalyticsType.TOTAL_AGENT_TALK_TIME.value: {
                "schema": TotalAgentTalkTimeRequest,
                "method": self.__analytics_processor._get_total_agent_talk_time,
            },
            AnalyticsType.AGENT_TALK_TIME_DISTRIBUTION.value: {
                "schema": AgentTalkTimeDistributionRequest,
                "method": self.__analytics_processor._get_agent_talk_time_distribution,
            },
            AnalyticsType.PARTNER_SERVICE_BOARD.value: {
                "schema": PartnerServiceBoardRequest,
                "method": self.__analytics_processor._get_partner_service_board,
            },
            AnalyticsType.DASHBOARD_CALL_TRENDS.value: {
                "schema": DashboardFollowupTrendsRequest,
                "method": self.__analytics_processor._get_dashboard_call_trends,
            },
        }

        try:
            mapping: Union[Dict[str, Any], None] = mappings.get(analytics_type)
            if not mapping:
                self.__holler_service_logger.error(
                    "Invalid analytics type: {}".format(analytics_type)
                )
                raise InvalidAnalyticTypeError(
                    "Invalid analytics type: {}".format(analytics_type)
                )

            try:
                validate_data: BaseModel = mapping["schema"](**data)
            except ValidationError as e:
                example_payload: Dict[str, Any] = (
                    mapping["schema"].model_json_schema().get("example", {})
                )
                self.__holler_service_logger.error(
                    "Invalid payload for analytics type {}: {}".format(
                        analytics_type, str(e)
                    )
                )
                raise PayloadValidationError(
                    message="Invalid payload for analytics type '{}'. Expected schema: {}".format(
                        analytics_type, json.dumps(example_payload)
                    ),
                    example_payload=example_payload,
                )

            method: Callable[..., Awaitable[Any]] = mapping["method"]
            analytics_data: Any = await method(
                current_user_id=current_user_id,
                partner_id=partner_id,
                request_data=validate_data,
                limit=limit,
                offset=offset,
            )
            self.__holler_service_logger.debug(
                "Analytics data: {}".format(analytics_data)
            )
            self.__holler_service_logger.info(
                "Successfully generated analytics for {}".format(analytics_type)
            )
            return AnalyticsResponse(
                analytics_type=analytics_type,
                data=analytics_data,
            )
        except Exception as e:
            self.__holler_service_logger.error(
                "Error processing analytics {}: {}".format(analytics_type, str(e))
            )
            raise
