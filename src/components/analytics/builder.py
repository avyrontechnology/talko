from typing import Dict, List, Optional

from dateutil.relativedelta import relativedelta

from src.components.analytics import constants as analytics_constants
from src.components.analytics.date_range_helper import DateRangeHelper
from src.components.cdr.models import CDR
from src.core.doc_db import DocDatabaseSessionManager
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.enums import UserRoleHierarchy


class QueryBuilder:
    """Helper class to build MongoDB queries for analytics."""

    def __init__(self, logger: HollerServiceLogger):
        self.__logger = logger

    def build_query(
        self,
        partner_id: int,
        start_date_ms: Optional[int],
        end_date_ms: Optional[int],
        agents: Optional[List[int]] = None,
        service_board_id: Optional[List[int]] = None,
        entity_type: Optional[str] = None,
        user_role: Optional[int] = UserRoleHierarchy.MAINTAINER.value,
    ) -> Dict:
        """Build MongoDB query with partner_id, date range, and optional filters."""
        query = {analytics_constants.PARTNER_ID: partner_id}
        if start_date_ms and end_date_ms:
            query["date_time"] = {
                analytics_constants.GTE_CONDITION: start_date_ms,
                analytics_constants.LTE_CONDITION: end_date_ms,
            }
        if (
            user_role != UserRoleHierarchy.MAINTAINER.value
            and agents
            and len(agents) > 0
        ):
            query["agent"] = {analytics_constants.IN_CONDITION: agents}
        if service_board_id and len(service_board_id) > 0:
            query["service_board_id"] = {
                analytics_constants.IN_CONDITION: service_board_id
            }
        if entity_type:
            query["entity_type"] = entity_type
        self.__logger.debug(f"Built query: {query}")
        return query

    def build_trend_query(
        self,
        partner_id: int,
        start_date_ms: int,
        end_date_ms: int,
        agents: List[int],
        service_board_id: Optional[List[int]],
        entity_type: Optional[str],
        user_role: int,
    ) -> Dict:
        """Build query for trend analysis using correct field names."""
        query = self.build_query(
            partner_id=partner_id,
            start_date_ms=start_date_ms,
            end_date_ms=end_date_ms,
            agents=agents,
            service_board_id=service_board_id,
            entity_type=entity_type,
            user_role=user_role,
        )
        return query
