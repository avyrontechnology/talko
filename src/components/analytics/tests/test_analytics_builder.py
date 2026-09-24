from unittest.mock import MagicMock

from src.components.analytics import constants as analytics_constants
from src.components.analytics.builder import TalkoQueryBuilder


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
            workspace_id=None,
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

    def test_build_query_with_agents_and_workspace(self):
        """Test build_query with agents and workspace_id."""
        query = self.query_builder.build_query(
            partner_id=42,
            start_date_ms=1000,
            end_date_ms=2000,
            agents=[123, 456],
            workspace_id=[99, 100],
            entity_type="Lead",
            user_role=2,
        )
        expected_query = {
            analytics_constants.PARTNER_ID: 42,
            "date_time": {
                analytics_constants.GTE_CONDITION: 1000,
                analytics_constants.LTE_CONDITION: 2000,
            },
            "agent": {analytics_constants.IN_CONDITION: [123, 456]},
            "workspace_id": {analytics_constants.IN_CONDITION: [99, 100]},
            "entity_type": "Lead",
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
            workspace_id=None,
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
            workspace_id=[99, 100],
            entity_type="Lead",
            user_role=2,
        )
        expected_query = {
            analytics_constants.PARTNER_ID: 42,
            "date_time": {
                analytics_constants.GTE_CONDITION: 1000,
                analytics_constants.LTE_CONDITION: 2000,
            },
            "agent": {analytics_constants.IN_CONDITION: [123, 456]},
            "workspace_id": {analytics_constants.IN_CONDITION: [99, 100]},
            "entity_type": "Lead",
        }
        assert query == expected_query

    def test_build_trend_query_no_agents(self):
        """Test build_trend_query without agents."""
        query = self.query_builder.build_trend_query(
            partner_id=42,
            start_date_ms=1000,
            end_date_ms=2000,
            agents=[],
            workspace_id=None,
            entity_type="Lead",
            user_role=3,
        )
        expected_query = {
            analytics_constants.PARTNER_ID: 42,
            "date_time": {
                analytics_constants.GTE_CONDITION: 1000,
                analytics_constants.LTE_CONDITION: 2000,
            },
            "entity_type": "Lead",
        }
        assert query == expected_query
