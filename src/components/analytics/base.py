import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from src.components.analytics.dto import (
    TalkoAgentCallAnalyticsRequest,
    TalkoAgentTalkTimeDistributionRequest,
    TalkoAnalyticsResponse,
    TalkoDashboardFollowupTrendsRequest,
    TalkoPartnerWorkspaceRequest,
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
        analytics_request: dict[str, Any],
        limit: int,
        offset: int,
    ) -> TalkoAnalyticsResponse:
        analytics_type: str | None = analytics_request.get("analytics_type")
        data: dict[str, Any] = analytics_request.get("data", {})

        mappings: dict[str, dict[str, Any]] = {
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
            TalkoAnalyticsType.PARTNER_WORKSPACE.value: {
                "schema": TalkoPartnerWorkspaceRequest,
                "method": self.__analytics_processor._get_partner_workspace,
            },
            TalkoAnalyticsType.DASHBOARD_CALL_TRENDS.value: {
                "schema": TalkoDashboardFollowupTrendsRequest,
                "method": self.__analytics_processor._get_dashboard_call_trends,
            },
        }

        try:
            mapping: dict[str, Any] | None = mappings.get(analytics_type)
            if not mapping:
                self.__talko_service_logger.error(f"Invalid analytics type: {analytics_type}")
                raise TalkoInvalidAnalyticTypeError(f"Invalid analytics type: {analytics_type}")

            try:
                validate_data: BaseModel = mapping["schema"](**data)
            except ValidationError as e:
                example_payload: dict[str, Any] = mapping["schema"].model_json_schema().get("example", {})
                self.__talko_service_logger.error(f"Invalid payload for analytics type {analytics_type}: {str(e)}")
                raise TalkoPayloadValidationError(
                    message=f"Invalid payload for analytics type '{analytics_type}'. Expected schema: {json.dumps(example_payload)}",
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
            self.__talko_service_logger.debug(f"Analytics data: {analytics_data}")
            self.__talko_service_logger.info(f"Successfully generated analytics for {analytics_type}")
            return TalkoAnalyticsResponse(
                analytics_type=analytics_type,
                data=analytics_data,
            )
        except Exception as e:
            self.__talko_service_logger.error(f"Error processing analytics {analytics_type}: {str(e)}")
            raise
