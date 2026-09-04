from typing import Any, Dict, Union

from src.components.analytics.base import TalkoAnalyticsBase
from src.components.analytics.dto import TalkoAnalyticsResponse
from src.components.analytics.enums import TalkoAnalyticsType
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoAnalyticsService:
    def __init__(
        self,
        analytics_base: TalkoAnalyticsBase,
        logger: TalkoServiceLogger,
    ) -> None:
        self.__analytics_base: TalkoAnalyticsBase = analytics_base
        self.__talko_service_logger: TalkoServiceLogger = logger

    async def get_analytics(
        self,
        current_user_id: int,
        partner_id: int,
        analytics_request: Dict[str, Any],
        limit: int,
        offset: int,
    ) -> TalkoAnalyticsResponse:
        try:
            analytics_type: Union[str, None] = analytics_request.get("analytics_type")
            self.__talko_service_logger.info(
                "Processing analytics for partner_id: {}, analytics_type: {}".format(
                    partner_id, analytics_type
                )
            )

            result: TalkoAnalyticsResponse = await self.__analytics_base.process_analytics(
                current_user_id=current_user_id,
                partner_id=partner_id,
                analytics_request=analytics_request,
                limit=limit,
                offset=offset,
            )

            # Attach agent names for agent-based analytics
            if analytics_type in [
                TalkoAnalyticsType.AGENT_CALL_ANALYTICS.value,
                TalkoAnalyticsType.TOTAL_AGENT_TALK_TIME.value,
                TalkoAnalyticsType.AGENT_TALK_TIME_DISTRIBUTION.value,
            ]:
                agent_ids = [agent["agent_id"] for agent in result.data["agents"]]
                if agent_ids:
                    grpc_client = TalkoRPCServiceFactory.get_service(TalkoGrpcServices.AUTH)
                    agent_data: Dict[int, Dict[str, Any]] = (
                        await grpc_client.get_service_board_users_details(agent_ids)
                    )
                    for agent in result.data["agents"]:
                        agent["agent_name"] = agent_data.get(agent["agent_id"], {}).get(
                            "name", ""
                        )

            self.__talko_service_logger.info(
                "Successfully retrieved analytics for partner_id: {}".format(partner_id)
            )
            return result
        except Exception as e:
            self.__talko_service_logger.error(
                "Error processing analytics for partner_id: {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise
