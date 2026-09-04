from typing import Any, Dict, Optional

from src.components.analytics.dto import (
    AgentCallAnalyticsRequest,
    AgentTalkTimeDistributionRequest,
    DashboardFollowupTrendsRequest,
    PartnerServiceBoardRequest,
    TotalAgentTalkTimeRequest,
)
from src.components.analytics.repositories import AnalyticsRepository
from src.components.common.user_hierarchy import UserHierarchy
from src.exceptions import InvalidPermissionTypeError
from src.grpc_client.client_services.auth_service_client import AuthServiceClient
from src.grpc_client.constants import GrpcServices
from src.grpc_client.rpc_service_factory import RPCServiceFactory
from src.loggers.holler_service_logger import HollerServiceLogger


class AnalyticsProcessor:
    def __init__(
        self,
        analytics_repository: AnalyticsRepository,
        logger: HollerServiceLogger,
        grpc_client: AuthServiceClient,
        user_hierarchy: UserHierarchy,
    ) -> None:
        self.analytics_repository: AnalyticsRepository = analytics_repository
        self.logger: HollerServiceLogger = logger
        self.grpc_client: AuthServiceClient = grpc_client
        self.user_hierarchy: UserHierarchy = user_hierarchy

    async def user_hierarchy_data(
        self, request_data, current_user_id: int
    ) -> tuple[list, int]:
        """Fetch and validate agent hierarchy under the given user."""
        agent_ids = await self.user_hierarchy.get_user_hierarchy_data(
            request_data, current_user_id
        )
        agent_data: Dict[int, Dict[str, Any]] = await self.grpc_client.get_user_roles(
            current_user_id
        )
        user_role = agent_data.get("hierarchy", 0)
        self.logger.debug("User role in hierarchy data: {}".format(user_role))
        return agent_ids, user_role

    def _parse_time_range(
        self, time_range: Optional[str]
    ) -> tuple[Optional[int], Optional[int]]:
        """Parse time_range string into start_date and end_date in seconds."""
        if not time_range:
            return None, None
        try:
            start_ms, end_ms = map(int, time_range.split("-"))
            if end_ms < start_ms:
                self.logger.error(
                    "Invalid time_range: end timestamp ({}) is before start timestamp ({})".format(
                        end_ms, start_ms
                    )
                )
                raise ValueError(
                    "end timestamp must be greater than or equal to start timestamp"
                )
            return start_ms // 1000, end_ms // 1000
        except ValueError as e:
            self.logger.error(f"Invalid time_range format: {str(e)}")
            raise ValueError(
                "Invalid time_range format. Expected 'start_ms-end_ms', e.g., '1749148200000-1756992444404'"
            )

    async def _get_agent_call_analytics(
        self,
        current_user_id: int,
        partner_id: int,
        request_data: AgentCallAnalyticsRequest,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        try:
            start_date, end_date = self._parse_time_range(request_data.time_range)
            self.logger.info(
                "Fetching agent call analytics for user_id={}, partner_id={}, agents={}, date_range=({}, {}), limit={}, offset={}".format(
                    current_user_id,
                    partner_id,
                    request_data.agents,
                    start_date,
                    end_date,
                    limit,
                    offset,
                )
            )
            agent_ids: list = []
            user_role: int = 0
            agent_ids, user_role = await self.user_hierarchy_data(
                request_data, current_user_id
            )

            result: Dict[str, Any] = (
                await self.analytics_repository.get_agent_call_analytics(
                    partner_id=partner_id,
                    start_date=start_date,
                    end_date=end_date,
                    agents=agent_ids,
                    service_board_id=request_data.service_board_id,
                    entity_type=request_data.entity_type,
                    limit=limit,
                    offset=offset,
                    user_role=user_role,
                )
            )
            self.logger.info(
                "Agent call analytics fetched successfully for user_id={}, partner_id={}".format(
                    current_user_id, partner_id
                )
            )
            return result
        except Exception as e:
            self.logger.error(
                "Error in agent call analytics for user_id={}, partner_id={}, error={}".format(
                    current_user_id, partner_id, str(e)
                )
            )
            raise

    async def _get_total_agent_talk_time(
        self,
        current_user_id: int,
        partner_id: int,
        request_data: TotalAgentTalkTimeRequest,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        try:
            start_date, end_date = self._parse_time_range(request_data.time_range)
            self.logger.info(
                "Fetching total agent talk time for user_id={}, partner_id={}, agents={}, date_range=({}, {}), limit={}, offset={}".format(
                    current_user_id,
                    partner_id,
                    request_data.agents,
                    start_date,
                    end_date,
                    limit,
                    offset,
                )
            )

            agent_ids: list = []
            user_role: int = 0
            agent_ids, user_role = await self.user_hierarchy_data(
                request_data, current_user_id
            )

            self.logger.info("Fetching total agent talk time for agent ids={}, user role={}".format(agent_ids, user_role))

            result: Dict[str, Any] = (
                await self.analytics_repository.get_total_agent_talk_time(
                    partner_id=partner_id,
                    start_date=start_date,
                    end_date=end_date,
                    agents=agent_ids,
                    service_board_id=request_data.service_board_id,
                    entity_type=request_data.entity_type,
                    limit=limit,
                    offset=offset,
                    user_role=user_role,
                )
            )
            self.logger.info(
                "Total agent talk time fetched successfully for user_id={}, partner_id={}".format(
                    current_user_id, partner_id
                )
            )
            return result
        except Exception as e:
            self.logger.error(
                "Error in total agent talk time for user_id={}, partner_id={}, error={}".format(
                    current_user_id, partner_id, str(e)
                )
            )
            raise

    async def _get_agent_talk_time_distribution(
        self,
        current_user_id: int,
        partner_id: int,
        request_data: AgentTalkTimeDistributionRequest,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        try:
            start_date, end_date = self._parse_time_range(request_data.time_range)
            self.logger.info(
                "Fetching agent talk time distribution for user_id={}, partner_id={}, agents={}, date_range=({}, {}), limit={}, offset={}".format(
                    current_user_id,
                    partner_id,
                    request_data.agents,
                    start_date,
                    end_date,
                    limit,
                    offset,
                )
            )

            agent_ids: list = []
            user_role: int = 0
            agent_ids, user_role = await self.user_hierarchy_data(
                request_data, current_user_id
            )

            result: Dict[str, Any] = (
                await self.analytics_repository.get_agent_talk_time_distribution(
                    partner_id=partner_id,
                    start_date=start_date,
                    end_date=end_date,
                    agents=agent_ids,
                    service_board_id=request_data.service_board_id,
                    entity_type=request_data.entity_type,
                    limit=limit,
                    offset=offset,
                    user_role=user_role,
                )
            )
            self.logger.info(
                "Agent talk time distribution fetched successfully for user_id={}, partner_id={}".format(
                    current_user_id, partner_id
                )
            )
            return result
        except Exception as e:
            self.logger.error(
                "Error in agent talk time distribution for user_id={}, partner_id={}, error={}".format(
                    current_user_id, partner_id, str(e)
                )
            )
            raise

    async def _get_partner_service_board(
        self,
        current_user_id: int,
        partner_id: int,
        request_data: PartnerServiceBoardRequest,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        try:
            start_date, end_date = self._parse_time_range(request_data.time_range)
            self.logger.info(
                "Fetching partner service board for user_id={}, partner_id={}, date_range=({}, {}), limit={}, offset={}".format(
                    current_user_id,
                    partner_id,
                    start_date,
                    end_date,
                    limit,
                    offset,
                )
            )

            agent_ids: list = []
            user_role: int = 0
            agent_ids, user_role = await self.user_hierarchy_data(
                request_data, current_user_id
            )

            result: Dict[str, Any] = (
                await self.analytics_repository.get_partner_service_board(
                    partner_id=partner_id,
                    start_date=start_date,
                    end_date=end_date,
                    service_board_id=request_data.service_board_id,
                    entity_type=request_data.entity_type,
                    limit=limit,
                    offset=offset,
                    agents=agent_ids,
                    user_role=user_role,
                )
            )
            self.logger.debug(
                "Processor get partner servcie board result: {}".format(result)
            )
            self.logger.info(
                "Partner service board fetched successfully for user_id={}, partner_id={}".format(
                    current_user_id, partner_id
                )
            )
            return result
        except Exception as e:
            self.logger.error(
                "Error in partner service board for user_id={}, partner_id={}, error={}".format(
                    current_user_id, partner_id, str(e)
                )
            )
            raise

    async def _get_dashboard_call_trends(
        self,
        current_user_id: int,
        partner_id: int,
        request_data: DashboardFollowupTrendsRequest,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        try:
            start_date, end_date = self._parse_time_range(request_data.time_range)
            self.logger.info(
                "Fetching dashboard followup trends for user_id={}, partner_id={}, metric={}, trend_basis={}, date_range=({}, {}), limit={}, offset={}".format(
                    current_user_id,
                    partner_id,
                    request_data.metric_filter,
                    request_data.trend_basis,
                    start_date,
                    end_date,
                    limit,
                    offset,
                )
            )

            agent_ids: list = []
            user_role: int = 0
            agent_ids, user_role = await self.user_hierarchy_data(
                request_data, current_user_id
            )

            result: Dict[str, Any] = (
                await self.analytics_repository.get_dashboard_call_trends(
                    partner_id=partner_id,
                    start_date=start_date,
                    end_date=end_date,
                    agents=agent_ids,
                    service_board_id=request_data.service_board_id,
                    entity_type=request_data.entity_type,
                    metric=request_data.metric_filter,
                    trend_basis=request_data.trend_basis,
                    limit=limit,
                    offset=offset,
                    user_role=user_role,
                )
            )
            self.logger.info(
                "Dashboard followup trends fetched successfully for user_id={}, partner_id={}".format(
                    current_user_id, partner_id
                )
            )
            return result
        except Exception as e:
            self.logger.error(
                "Error in dashboard followup trends for user_id={}, partner_id={}, error={}".format(
                    current_user_id, partner_id, str(e)
                )
            )
            raise
