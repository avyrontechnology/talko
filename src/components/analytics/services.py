from typing import Any, Dict, Union

from src.components.analytics.base import AnalyticsBase
from src.components.analytics.dto import AnalyticsResponse
from src.components.analytics.enums import AnalyticsType
from src.grpc_client.constants import GrpcServices
from src.grpc_client.rpc_service_factory import RPCServiceFactory
from src.loggers.holler_service_logger import HollerServiceLogger


class AnalyticsService:
    def __init__(
        self,
        analytics_base: AnalyticsBase,
        logger: HollerServiceLogger,
    ) -> None:
        self.__analytics_base: AnalyticsBase = analytics_base
        self.__holler_service_logger: HollerServiceLogger = logger

    async def get_analytics(
        self,
        current_user_id: int,
        partner_id: int,
        analytics_request: Dict[str, Any],
        limit: int,
        offset: int,
    ) -> AnalyticsResponse:
        try:
            analytics_type: Union[str, None] = analytics_request.get("analytics_type")
            self.__holler_service_logger.info(
                "Processing analytics for partner_id: {}, analytics_type: {}".format(
                    partner_id, analytics_type
                )
            )

            result: AnalyticsResponse = await self.__analytics_base.process_analytics(
                current_user_id=current_user_id,
                partner_id=partner_id,
                analytics_request=analytics_request,
                limit=limit,
                offset=offset,
            )

            # Attach agent names for agent-based analytics
            if analytics_type in [
                AnalyticsType.AGENT_CALL_ANALYTICS.value,
                AnalyticsType.TOTAL_AGENT_TALK_TIME.value,
                AnalyticsType.AGENT_TALK_TIME_DISTRIBUTION.value,
            ]:
                agent_ids = [agent["agent_id"] for agent in result.data["agents"]]
                if agent_ids:
                    grpc_client = RPCServiceFactory.get_service(GrpcServices.AUTH)
                    agent_data: Dict[int, Dict[str, Any]] = (
                        await grpc_client.get_service_board_users_details(agent_ids)
                    )
                    for agent in result.data["agents"]:
                        agent["agent_name"] = agent_data.get(agent["agent_id"], {}).get(
                            "name", ""
                        )

            self.__holler_service_logger.info(
                "Successfully retrieved analytics for partner_id: {}".format(partner_id)
            )
            return result
        except Exception as e:
            self.__holler_service_logger.error(
                "Error processing analytics for partner_id: {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise
