import json
from typing import Any, Awaitable, Callable, Dict, Type, Union

from pydantic import BaseModel, ValidationError

from src.components.analytics.dto import (
    TalkoAgentCallAnalyticsRequest,
    TalkoAgentTalkTimeDistributionRequest,
    TalkoAnalyticsResponse,
    TalkoDashboardFollowupTrendsRequest,
    TalkoPartnerServiceBoardRequest,
    TalkoTotalAgentTalkTimeRequest,
)
from src.components.analytics.enums import TalkoAnalyticsType
from src.components.analytics.processor import TalkoAnalyticsProcessor
from src.exceptions import TalkoInvalidAnalyticTypeError, TalkoPayloadValidationError
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoAnalyticsBase:
    def __init__(
        self,
        analytics_processor: "TalkoAnalyticsProcessor",
        logger: TalkoServiceLogger,
    ) -> None:
        self.__analytics_processor: TalkoAnalyticsProcessor = analytics_processor
        self.__talko_service_logger: TalkoServiceLogger = logger

    async def process_analytics(
        self,
        current_user_id: int,
        partner_id: int,
        analytics_request: Dict[str, Any],
        limit: int,
        offset: int,
    ) -> TalkoAnalyticsResponse:
        analytics_type: Union[str, None] = analytics_request.get("analytics_type")
        data: Dict[str, Any] = analytics_request.get("data", {})

        mappings: Dict[str, Dict[str, Any]] = {
            TalkoAnalyticsType.AGENT_CALL_ANALYTICS.value: {
                "schema": TalkoAgentCallAnalyticsRequest,
                "method": self.__analytics_processor._get_agent_call_analytics,
            },
            TalkoAnalyticsType.TOTAL_AGENT_TALK_TIME.value: {
                "schema": TalkoTotalAgentTalkTimeRequest,
                "method": self.__analytics_processor._get_total_agent_talk_time,
            },
            TalkoAnalyticsType.AGENT_TALK_TIME_DISTRIBUTION.value: {
                "schema": TalkoAgentTalkTimeDistributionRequest,
                "method": self.__analytics_processor._get_agent_talk_time_distribution,
            },
            TalkoAnalyticsType.PARTNER_SERVICE_BOARD.value: {
                "schema": TalkoPartnerServiceBoardRequest,
                "method": self.__analytics_processor._get_partner_service_board,
            },
            TalkoAnalyticsType.DASHBOARD_CALL_TRENDS.value: {
                "schema": TalkoDashboardFollowupTrendsRequest,
                "method": self.__analytics_processor._get_dashboard_call_trends,
            },
        }

        try:
            mapping: Union[Dict[str, Any], None] = mappings.get(analytics_type)
            if not mapping:
                self.__talko_service_logger.error(
                    "Invalid analytics type: {}".format(analytics_type)
                )
                raise TalkoInvalidAnalyticTypeError(
                    "Invalid analytics type: {}".format(analytics_type)
                )

            try:
                validate_data: BaseModel = mapping["schema"](**data)
            except ValidationError as e:
                example_payload: Dict[str, Any] = (
                    mapping["schema"].model_json_schema().get("example", {})
                )
                self.__talko_service_logger.error(
                    "Invalid payload for analytics type {}: {}".format(
                        analytics_type, str(e)
                    )
                )
                raise TalkoPayloadValidationError(
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
            self.__talko_service_logger.debug(
                "Analytics data: {}".format(analytics_data)
            )
            self.__talko_service_logger.info(
                "Successfully generated analytics for {}".format(analytics_type)
            )
            return TalkoAnalyticsResponse(
                analytics_type=analytics_type,
                data=analytics_data,
            )
        except Exception as e:
            self.__talko_service_logger.error(
                "Error processing analytics {}: {}".format(analytics_type, str(e))
            )
            raise
