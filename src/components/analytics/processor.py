from typing import Any

from src.components.analytics.dto import (
    TalkoAgentCallAnalyticsRequest,
    TalkoAgentTalkTimeDistributionRequest,
    TalkoDashboardFollowupTrendsRequest,
    TalkoPartnerWorkspaceRequest,
    TalkoTotalAgentTalkTimeRequest,
)
from src.components.analytics.repositories import TalkoAnalyticsRepository
from src.components.common.user_hierarchy import TalkoUserHierarchy
from src.grpc_client.client_services.auth_service_client import TalkoAuthServiceClient
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.enums import TalkoUserRoleHierarchy


class TalkoAnalyticsProcessor:
    def __init__(
        self,
        analytics_repository: TalkoAnalyticsRepository,
        logger: TalkoServiceLogger,
        grpc_client: TalkoAuthServiceClient,
        user_hierarchy: TalkoUserHierarchy,
    ) -> None:
        self.analytics_repository: TalkoAnalyticsRepository = analytics_repository
        self.logger: TalkoServiceLogger = logger
        self.grpc_client: TalkoAuthServiceClient = grpc_client
        self.user_hierarchy: TalkoUserHierarchy = user_hierarchy

    async def user_hierarchy_data(self, request_data, current_user_id: int) -> tuple[list, int]:
        """Fetch and validate agent hierarchy under the given user."""
        if current_user_id is None:
            # Partner API-key auth carries no user_id and gRPC is disabled —
            # fall back to partner-wide scope (empty agent filter + maintainer
            # role bypasses the repository's empty-result guard).
            self.logger.info("No user_id (API-key auth); using partner-wide analytics scope")
            return [], TalkoUserRoleHierarchy.MAINTAINER.value
        agent_ids = await self.user_hierarchy.get_user_hierarchy_data(request_data, current_user_id)
        agent_data: dict[int, dict[str, Any]] = await self.grpc_client.get_user_roles(current_user_id)
        user_role = agent_data.get("hierarchy", 0)
        self.logger.debug(f"User role in hierarchy data: {user_role}")
        return agent_ids, user_role

    def _parse_time_range(self, time_range: str | None) -> tuple[int | None, int | None]:
        """Parse time_range string into start_date and end_date in seconds."""
        if not time_range:
            return None, None
        try:
            start_ms, end_ms = map(int, time_range.split("-"))
            if end_ms < start_ms:
                self.logger.error(
                    f"Invalid time_range: end timestamp ({end_ms}) is before start timestamp ({start_ms})"
                )
                raise ValueError("end timestamp must be greater than or equal to start timestamp")
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
        request_data: TalkoAgentCallAnalyticsRequest,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        try:
            start_date, end_date = self._parse_time_range(request_data.time_range)
            self.logger.info(
                f"Fetching agent call analytics for user_id={current_user_id}, partner_id={partner_id}, agents={request_data.agents}, date_range=({start_date}, {end_date}), limit={limit}, offset={offset}"
            )
            agent_ids: list = []
            user_role: int = 0
            agent_ids, user_role = await self.user_hierarchy_data(request_data, current_user_id)

            result: dict[str, Any] = await self.analytics_repository.get_agent_call_analytics(
                partner_id=partner_id,
                start_date=start_date,
                end_date=end_date,
                agents=agent_ids,
                workspace_id=request_data.workspace_id,
                entity_type=request_data.entity_type,
                limit=limit,
                offset=offset,
                user_role=user_role,
            )
            self.logger.info(
                f"Agent call analytics fetched successfully for user_id={current_user_id}, partner_id={partner_id}"
            )
            return result
        except Exception as e:
            self.logger.error(
                f"Error in agent call analytics for user_id={current_user_id}, partner_id={partner_id}, error={str(e)}"
            )
            raise

    async def _get_total_agent_talk_time(
        self,
        current_user_id: int,
        partner_id: int,
        request_data: TalkoTotalAgentTalkTimeRequest,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        try:
            start_date, end_date = self._parse_time_range(request_data.time_range)
            self.logger.info(
                f"Fetching total agent talk time for user_id={current_user_id}, partner_id={partner_id}, agents={request_data.agents}, date_range=({start_date}, {end_date}), limit={limit}, offset={offset}"
            )

            agent_ids: list = []
            user_role: int = 0
            agent_ids, user_role = await self.user_hierarchy_data(request_data, current_user_id)

            self.logger.info(f"Fetching total agent talk time for agent ids={agent_ids}, user role={user_role}")

            result: dict[str, Any] = await self.analytics_repository.get_total_agent_talk_time(
                partner_id=partner_id,
                start_date=start_date,
                end_date=end_date,
                agents=agent_ids,
                workspace_id=request_data.workspace_id,
                entity_type=request_data.entity_type,
                limit=limit,
                offset=offset,
                user_role=user_role,
            )
            self.logger.info(
                f"Total agent talk time fetched successfully for user_id={current_user_id}, partner_id={partner_id}"
            )
            return result
        except Exception as e:
            self.logger.error(
                f"Error in total agent talk time for user_id={current_user_id}, partner_id={partner_id}, error={str(e)}"
            )
            raise

    async def _get_agent_talk_time_distribution(
        self,
        current_user_id: int,
        partner_id: int,
        request_data: TalkoAgentTalkTimeDistributionRequest,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        try:
            start_date, end_date = self._parse_time_range(request_data.time_range)
            self.logger.info(
                f"Fetching agent talk time distribution for user_id={current_user_id}, partner_id={partner_id}, agents={request_data.agents}, date_range=({start_date}, {end_date}), limit={limit}, offset={offset}"
            )

            agent_ids: list = []
            user_role: int = 0
            agent_ids, user_role = await self.user_hierarchy_data(request_data, current_user_id)

            result: dict[str, Any] = await self.analytics_repository.get_agent_talk_time_distribution(
                partner_id=partner_id,
                start_date=start_date,
                end_date=end_date,
                agents=agent_ids,
                workspace_id=request_data.workspace_id,
                entity_type=request_data.entity_type,
                limit=limit,
                offset=offset,
                user_role=user_role,
            )
            self.logger.info(
                f"Agent talk time distribution fetched successfully for user_id={current_user_id}, partner_id={partner_id}"
            )
            return result
        except Exception as e:
            self.logger.error(
                f"Error in agent talk time distribution for user_id={current_user_id}, partner_id={partner_id}, error={str(e)}"
            )
            raise

    async def _get_partner_workspace(
        self,
        current_user_id: int,
        partner_id: int,
        request_data: TalkoPartnerWorkspaceRequest,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        try:
            start_date, end_date = self._parse_time_range(request_data.time_range)
            self.logger.info(
                f"Fetching partner workspace for user_id={current_user_id}, partner_id={partner_id}, date_range=({start_date}, {end_date}), limit={limit}, offset={offset}"
            )

            agent_ids: list = []
            user_role: int = 0
            agent_ids, user_role = await self.user_hierarchy_data(request_data, current_user_id)

            result: dict[str, Any] = await self.analytics_repository.get_partner_workspace(
                partner_id=partner_id,
                start_date=start_date,
                end_date=end_date,
                workspace_id=request_data.workspace_id,
                entity_type=request_data.entity_type,
                limit=limit,
                offset=offset,
                agents=agent_ids,
                user_role=user_role,
            )
            self.logger.debug(f"Processor get partner servcie board result: {result}")
            self.logger.info(
                f"Partner workspace fetched successfully for user_id={current_user_id}, partner_id={partner_id}"
            )
            return result
        except Exception as e:
            self.logger.error(
                f"Error in partner workspace for user_id={current_user_id}, partner_id={partner_id}, error={str(e)}"
            )
            raise

    async def _get_dashboard_call_trends(
        self,
        current_user_id: int,
        partner_id: int,
        request_data: TalkoDashboardFollowupTrendsRequest,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        try:
            start_date, end_date = self._parse_time_range(request_data.time_range)
            self.logger.info(
                f"Fetching dashboard followup trends for user_id={current_user_id}, partner_id={partner_id}, metric={request_data.metric_filter}, trend_basis={request_data.trend_basis}, date_range=({start_date}, {end_date}), limit={limit}, offset={offset}"
            )

            agent_ids: list = []
            user_role: int = 0
            agent_ids, user_role = await self.user_hierarchy_data(request_data, current_user_id)

            result: dict[str, Any] = await self.analytics_repository.get_dashboard_call_trends(
                partner_id=partner_id,
                start_date=start_date,
                end_date=end_date,
                agents=agent_ids,
                workspace_id=request_data.workspace_id,
                entity_type=request_data.entity_type,
                metric=request_data.metric_filter,
                trend_basis=request_data.trend_basis,
                limit=limit,
                offset=offset,
                user_role=user_role,
            )
            self.logger.info(
                f"Dashboard followup trends fetched successfully for user_id={current_user_id}, partner_id={partner_id}"
            )
            return result
        except Exception as e:
            self.logger.error(
                f"Error in dashboard followup trends for user_id={current_user_id}, partner_id={partner_id}, error={str(e)}"
            )
            raise
