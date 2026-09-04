from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.analytics import constants as analytics_constants
from src.components.analytics.builder import QueryBuilder
from src.components.analytics.enums import DateRangePeriod, TimeInterval
from src.components.analytics.repositories import AnalyticsRepository


class TestAnalyticsRepository:
    def setup_method(self):
        self.mock_db_manager = MagicMock()
        self.mock_logger = MagicMock()
        self.mock_collection = MagicMock()
        self.mock_query_builder = MagicMock()
        self.mock_db_manager.collection.return_value.__aenter__.return_value = (
            self.mock_collection
        )

        self.repo = AnalyticsRepository(
            db_manager=self.mock_db_manager,
            logger=self.mock_logger,
            analytics_query_builder=self.mock_query_builder,
        )

    @pytest.mark.asyncio
    @patch("src.components.analytics.repositories.DateRangeHelper.adjust_date_range")
    async def test_get_agent_call_analytics_success(self, mock_adjust):
        """Test successful retrieval of agent call analytics."""
        fake_result = [
            {
                "agent_id": 123,
                "agent_name": "Agent 123",
                "total_calls": 10,
                "unique_calls": ["c1", "c2"],
                "connected_calls": 8,
                "missed_calls": 2,
                "agent_missed_calls": 1,
                "lead_missed_calls": 1,
                "total_placed_calls": 8,
                "total_connected_unique_calls": 1,
            }
        ]
        fake_count_result = [{"total_count": 5}]
        self.mock_collection.aggregate.return_value.to_list = AsyncMock(
            side_effect=[fake_count_result, fake_result]
        )
        mock_adjust.return_value = (1000, 2000, DateRangePeriod.CUSTOM.value)
        self.mock_query_builder.build_query.return_value = {
            analytics_constants.PARTNER_ID: 42,
            "date_time": {
                analytics_constants.GTE_CONDITION: 1000,
                analytics_constants.LTE_CONDITION: 2000,
            },
            "agent": {analytics_constants.IN_CONDITION: [123]},
        }

        result = await self.repo.get_agent_call_analytics(
            partner_id=42,
            start_date=1000,
            end_date=2000,
            agents=[123],
            limit=10,
            offset=1,
            user_role=3,
        )

        assert result["agents"][0]["agent_id"] == 123
        assert result["agents"][0]["agent_name"] == "Agent 123"
        assert result["agents"][0]["total_calls"] == 10
        assert result["total_count"] == 5
        self.mock_logger.info.assert_any_call(
            "Successfully retrieved agent call analytics for partner_id: 42"
        )
        self.mock_collection.aggregate.assert_called()
        self.mock_logger.debug.assert_any_call(
            f"Retrieving agent call analytics for partner_id: 42, "
            f"start_date: 1000, end_date: 2000, period: {DateRangePeriod.CUSTOM.value}, "
            f"limit: 10, offset: 1"
        )

    @pytest.mark.asyncio
    @patch("src.components.analytics.repositories.DateRangeHelper.adjust_date_range")
    async def test_get_total_agent_talk_time_success(self, mock_adjust):
        """Test successful retrieval of total agent talk time."""
        fake_result = [
            {
                "agent_id": 123,
                "agent_name": "Agent 123",
                "total_talk_time": 300,
                "total_call_duration": 600,
            }
        ]
        fake_count_result = [{"total_count": 3}]
        self.mock_collection.aggregate.return_value.to_list = AsyncMock(
            side_effect=[fake_count_result, fake_result]
        )
        mock_adjust.return_value = (1000, 2000, DateRangePeriod.CUSTOM.value)
        self.mock_query_builder.build_query.return_value = {
            analytics_constants.PARTNER_ID: 42,
            "date_time": {
                analytics_constants.GTE_CONDITION: 1000,
                analytics_constants.LTE_CONDITION: 2000,
            },
            "agent": {analytics_constants.IN_CONDITION: [123]},
        }

        result = await self.repo.get_total_agent_talk_time(
            partner_id=42,
            start_date=1000,
            end_date=2000,
            agents=[123],
            limit=10,
            offset=1,
            user_role=3,
        )

        assert result["agents"][0]["agent_id"] == 123
        assert result["agents"][0]["agent_name"] == "Agent 123"
        assert result["agents"][0]["total_talk_time"] == 300
        assert result["total_count"] == 3
        self.mock_logger.info.assert_any_call(
            "Successfully retrieved total agent talk time for partner_id: 42"
        )
        self.mock_collection.aggregate.assert_called()
        self.mock_logger.debug.assert_any_call(
            f"Retrieving total agent talk time for partner_id: 42, "
            f"start_date: 1000, end_date: 2000, period: {DateRangePeriod.CUSTOM.value}, "
            f"limit: 10, offset: 1"
        )

    @pytest.mark.asyncio
    @patch("src.components.analytics.repositories.DateRangeHelper.adjust_date_range")
    async def test_get_agent_talk_time_distribution_success(self, mock_adjust):
        """Test successful retrieval of agent talk time distribution."""
        fake_result = [
            {
                "agent_id": 123,
                "agent_name": "Agent 123",
                "buckets": {"0-1 minutes": 2, "1-5 minutes": 1},
            }
        ]
        fake_count_result = [{"total_count": 4}]
        self.mock_collection.aggregate.return_value.to_list = AsyncMock(
            side_effect=[fake_count_result, fake_result]
        )
        mock_adjust.return_value = (1000, 2000, DateRangePeriod.CUSTOM.value)
        self.mock_query_builder.build_query.return_value = {
            analytics_constants.PARTNER_ID: 42,
            "date_time": {
                analytics_constants.GTE_CONDITION: 1000,
                analytics_constants.LTE_CONDITION: 2000,
            },
            "agent": {analytics_constants.IN_CONDITION: [123]},
        }

        result = await self.repo.get_agent_talk_time_distribution(
            partner_id=42,
            start_date=1000,
            end_date=2000,
            agents=[123],
            limit=10,
            offset=1,
            user_role=3,
        )

        assert result["agents"][0]["agent_id"] == 123
        assert result["agents"][0]["agent_name"] == "Agent 123"
        assert result["agents"][0]["buckets"]["0-1 minutes"] == 2
        assert result["total_count"] == 4
        self.mock_logger.info.assert_any_call(
            "Successfully retrieved agent talk time distribution for partner_id: 42"
        )
        self.mock_collection.aggregate.assert_called()
        self.mock_logger.debug.assert_any_call(
            f"Retrieving agent talk time distribution for partner_id: 42, "
            f"start_date: 1000, end_date: 2000, period: {DateRangePeriod.CUSTOM.value}, "
            f"limit: 10, offset: 1"
        )

    @pytest.mark.asyncio
    @patch("src.components.analytics.repositories.DateRangeHelper.adjust_date_range")
    async def test_get_partner_service_board_success(self, mock_adjust):
        """Test successful retrieval of partner service board analytics."""
        fake_result = [
            {
                "partner_id": 42,
                "total_calls": 50,
                "total_unique_calls": 3,
                "total_connected": 40,
                "total_missed": 10,
                "total_talk_time": 1000,
            }
        ]
        self.mock_collection.aggregate.return_value.to_list = AsyncMock(
            return_value=fake_result
        )
        mock_adjust.return_value = (1000, 2000, DateRangePeriod.CUSTOM.value)
        self.mock_query_builder.build_query.return_value = {
            analytics_constants.PARTNER_ID: 42,
            "date_time": {
                analytics_constants.GTE_CONDITION: 1000,
                analytics_constants.LTE_CONDITION: 2000,
            },
            "service_board_id": {analytics_constants.IN_CONDITION: [99]},
        }

        await self.repo.get_partner_service_board(
            partner_id=42,
            start_date=1000,
            end_date=2000,
            service_board_id=[99],
            limit=10,
            offset=1,
        )
        self.mock_logger.info.assert_any_call(
            "Successfully retrieved partner service board analytics for partner_id: 42"
        )
        self.mock_collection.aggregate.assert_called()
        self.mock_logger.debug.assert_any_call(
            f"Retrieving partner service board analytics for partner_id: 42, "
            f"start_date: 1000, end_date: 2000, period: {DateRangePeriod.CUSTOM.value}, "
            f"service_board_id: [99]"
        )

    @pytest.mark.asyncio
    async def test_get_dashboard_call_trends_success(self):
        """Test successful retrieval of dashboard call trends."""
        # --- Arrange ---
        fake_query = {"partner_id": 42}
        fake_projection = {"_id": 0, "date_time": 1}
        fake_sort_order = [("date_time", 1)]
        fake_cdrs = [
            {"date_time": 1000, "total_calls": 15, "connected_calls": 10},
            {"date_time": 2000, "total_calls": 20, "connected_calls": 12},
        ]
        fake_filtered_docs = fake_cdrs
        fake_formatted_data = [
            {"date": "2025-10-01", "total_calls": 15},
            {"date": "2025-10-02", "total_calls": 20},
        ]
        fake_total_count = 2

        # Create mock helper and attach async mocks
        mock_helper = MagicMock()
        mock_helper.prepare_query_params = AsyncMock(
            return_value=(fake_query, 1000, 2000, None)
        )
        mock_helper.get_projection_and_sort_for_trends = AsyncMock(
            return_value=(fake_projection, fake_sort_order)
        )
        mock_helper.filter_and_format_data = AsyncMock(
            return_value=(
                fake_filtered_docs,
                fake_formatted_data,
                fake_total_count,
                None,
            )
        )
        mock_helper._calculate_total_count = MagicMock(return_value=fake_total_count)

        # Inject mock helper into repo
        self.repo._AnalyticsRepository__call_trends_helper = mock_helper

        # Mock DB collection
        self.mock_collection.find.return_value.to_list = AsyncMock(
            return_value=fake_cdrs
        )

        # --- Act ---
        result = await self.repo.get_dashboard_call_trends(
            partner_id=42,
            start_date=1000,
            end_date=2000,
            agents=[123],
            service_board_id=[11],
            metric="total_calls",
            trend_basis="daily",
            limit=10,
            offset=1,
            user_role=3,
        )

        # --- Assert ---
        assert result["selected_metric"] == "total_calls"
        assert result["trend_basis"] == "daily"
        assert result["total_count"] == fake_total_count
        assert len(result["data"]) == 2
        assert result["data"][0]["date"] == "2025-10-01"

        self.mock_logger.info.assert_any_call(
            "Retrieving call trends for partner 42 — metric=total_calls, trend=daily"
        )
        self.mock_collection.find.assert_called_once()
        mock_helper.prepare_query_params.assert_awaited_once()
        mock_helper.get_projection_and_sort_for_trends.assert_awaited_once()
        mock_helper.filter_and_format_data.assert_awaited_once()
