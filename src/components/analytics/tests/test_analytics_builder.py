from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.analytics import constants as analytics_constants
from src.components.analytics.builder import TalkoQueryBuilder
from src.components.analytics.enums import TalkoDateRangePeriod
from src.components.analytics.repositories import TalkoAnalyticsRepository


class TestQueryBuilder:
    def setup_method(self):
        self.mock_logger = MagicMock()
        self.query_builder = TalkoQueryBuilder(logger=self.mock_logger)

    def test_build_query_basic(self):
        """Test build_query with basic parameters."""
        query = self.query_builder.build_query(
            partner_id=42,
            start_date_ms=1000,
            end_date_ms=2000,
            agents=None,
            service_board_id=None,
            user_role=3,
        )
        expected_query = {
            analytics_constants.PARTNER_ID: 42,
            "date_time": {
                analytics_constants.GTE_CONDITION: 1000,
                analytics_constants.LTE_CONDITION: 2000,
            },
        }
        assert query == expected_query
        self.mock_logger.debug.assert_called_with(f"Built query: {expected_query}")

    def test_build_query_with_agents_and_service_board(self):
        """Test build_query with agents and service_board_id."""
        query = self.query_builder.build_query(
            partner_id=42,
            start_date_ms=1000,
            end_date_ms=2000,
            agents=[123, 456],
            service_board_id=[99, 100],
            user_role=2,
        )
        expected_query = {
            analytics_constants.PARTNER_ID: 42,
            "date_time": {
                analytics_constants.GTE_CONDITION: 1000,
                analytics_constants.LTE_CONDITION: 2000,
            },
            "agent": {analytics_constants.IN_CONDITION: [123, 456]},
            "service_board_id": {analytics_constants.IN_CONDITION: [99, 100]},
        }
        assert query == expected_query
        self.mock_logger.debug.assert_called_with(f"Built query: {expected_query}")

    def test_build_query_no_dates(self):
        """Test build_query without start_date_ms and end_date_ms."""
        query = self.query_builder.build_query(
            partner_id=42,
            start_date_ms=None,
            end_date_ms=None,
            agents=[123],
            service_board_id=None,
            user_role=3,
        )
        expected_query = {analytics_constants.PARTNER_ID: 42}
        assert query == expected_query
        self.mock_logger.debug.assert_called_with(f"Built query: {expected_query}")

    def test_build_trend_query(self):
        """Test build_trend_query with full parameters."""
        query = self.query_builder.build_trend_query(
            partner_id=42,
            start_date_ms=1000,
            end_date_ms=2000,
            agents=[123, 456],
            service_board_id=[99, 100],
            user_role=2,
        )
        expected_query = {
            analytics_constants.PARTNER_ID: 42,
            "date_time": {
                analytics_constants.GTE_CONDITION: 1000,
                analytics_constants.LTE_CONDITION: 2000,
            },
            "agent_id": {analytics_constants.IN_CONDITION: [123, 456]},
            "service_board_id": {analytics_constants.IN_CONDITION: [99, 100]},
        }

    def test_build_trend_query_no_agents(self):
        """Test build_trend_query without agents."""
        query = self.query_builder.build_trend_query(
            partner_id=42,
            start_date_ms=1000,
            end_date_ms=2000,
            agents=[],
            service_board_id=None,
            user_role=3,
        )
        expected_query = {
            analytics_constants.PARTNER_ID: 42,
            "call_time": {
                analytics_constants.GTE_CONDITION: 1000,
                analytics_constants.LTE_CONDITION: 2000,
            },
        }
