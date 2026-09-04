from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.analytics.base import AnalyticsBase
from src.components.analytics.dto import (
    AgentCallAnalyticsRequest,
    AnalyticsResponse,
    DashboardFollowupTrendsRequest,
    PartnerServiceBoardRequest,
)
from src.components.analytics.enums import AnalyticsType, Metric, TimeInterval
from src.exceptions import InvalidAnalyticTypeError, PayloadValidationError


@pytest.mark.asyncio
class TestAnalyticsBase:
    @pytest.fixture
    def setup_analytics_base(self):
        mock_processor = AsyncMock()
        mock_logger = MagicMock()
        service = AnalyticsBase(analytics_processor=mock_processor, logger=mock_logger)
        # Mock user_hierarchy_data to simulate user_role == 3
        mock_processor.user_hierarchy_data.return_value = ([1, 2, 3], 3)
        return service, mock_processor, mock_logger

    async def test_process_analytics_success(self, setup_analytics_base):
        service, mock_processor, mock_logger = setup_analytics_base

        expected_data = {"analytics": "agent_calls", "total_count": 10}
        mock_processor._get_agent_call_analytics.return_value = expected_data

        request = {
            "analytics_type": AnalyticsType.AGENT_CALL_ANALYTICS.value,
            "data": {
                "time_range": "1735689600000-1738272000000",  # 2025-01-01 to 2025-01-31
                "agents": [1, 2],
                "service_board_id": [1, 3],
            },
        }

        result = await service.process_analytics(1, 123, request, limit=10, offset=1)

        assert isinstance(result, AnalyticsResponse)
        assert result.analytics_type == AnalyticsType.AGENT_CALL_ANALYTICS.value
        assert result.data == expected_data
        mock_processor._get_agent_call_analytics.assert_awaited_once_with(
            current_user_id=1,
            partner_id=123,
            request_data=AgentCallAnalyticsRequest(
                time_range="1735689600000-1738272000000",
                agents=[1, 2],
                service_board_id=[1, 3],
            ),
            limit=10,
            offset=1,
        )
        mock_logger.info.assert_any_call(
            f"Successfully generated analytics for {AnalyticsType.AGENT_CALL_ANALYTICS.value}"
        )

    async def test_process_analytics_invalid_type(self, setup_analytics_base):
        service, mock_processor, mock_logger = setup_analytics_base

        request = {"analytics_type": "invalid_type", "data": {}}

        with pytest.raises(InvalidAnalyticTypeError) as exc_info:
            await service.process_analytics(1, 123, request, limit=10, offset=1)

        assert str(exc_info.value) == "Invalid analytics type: invalid_type"
        mock_logger.error.assert_any_call("Invalid analytics type: invalid_type")

    async def test_process_analytics_invalid_payload(self, setup_analytics_base):
        service, mock_processor, mock_logger = setup_analytics_base

        mock_processor._get_total_agent_talk_time.side_effect = AssertionError(
            "Processor method should not be called"
        )

        request = {
            "analytics_type": AnalyticsType.TOTAL_AGENT_TALK_TIME.value,
            "data": {
                "time_range": 12345,  # invalid type
                "agents": "not-a-list",  # invalid type
            },
        }

        with pytest.raises(PayloadValidationError) as exc_info:
            await service.process_analytics(1, 123, request, limit=10, offset=1)

        mock_processor._get_total_agent_talk_time.assert_not_awaited()
        assert (
            f"Invalid payload for analytics type '{AnalyticsType.TOTAL_AGENT_TALK_TIME.value}'"
            in str(exc_info.value)
        )

        assert any(
            f"Invalid payload for analytics type {AnalyticsType.TOTAL_AGENT_TALK_TIME.value}:"
            in str(call)
            for call in mock_logger.error.call_args_list
        )

    async def test_process_analytics_method_exception(self, setup_analytics_base):
        service, mock_processor, mock_logger = setup_analytics_base

        mock_processor._get_partner_service_board.side_effect = Exception("boom")

        request = {
            "analytics_type": AnalyticsType.PARTNER_SERVICE_BOARD.value,
            "data": {
                "time_range": "1743465600000-1746057600000",  # 2025-04-01 to 2025-04-30
            },
        }

        with pytest.raises(Exception) as exc_info:
            await service.process_analytics(1, 123, request, limit=10, offset=1)

        assert str(exc_info.value) == "boom"
        mock_processor._get_partner_service_board.assert_awaited_once_with(
            current_user_id=1,
            partner_id=123,
            request_data=PartnerServiceBoardRequest(
                time_range="1743465600000-1746057600000"
            ),
            limit=10,
            offset=1,
        )
        mock_logger.error.assert_any_call(
            f"Error processing analytics {AnalyticsType.PARTNER_SERVICE_BOARD.value}: boom"
        )

    async def test_process_analytics_dashboard_call_trends_success(
        self, setup_analytics_base
    ):
        service, mock_processor, mock_logger = setup_analytics_base

        expected_data = {
            "trend_basis": "Weekly",
            "selected_metric": "agent_missed_calls",
            "total_count": 13,
            "data": [
                {"period": "Week 1 (Aug 04 - Aug 10)", "count": 5},
                {"period": "Week 2 (Aug 11 - Aug 17)", "count": 8},
            ],
        }
        mock_processor._get_dashboard_call_trends.return_value = expected_data

        request = {
            "analytics_type": AnalyticsType.DASHBOARD_CALL_TRENDS.value,
            "data": {
                "time_range": "1722470400000-1726444800000",  # 2025-08-01 to 2025-09-15
                "service_board_id": [40, 41],
                "metric_filter": "agent_missed_calls",
                "trend_basis": TimeInterval.WEEKS.value,
            },
        }

        result = await service.process_analytics(1, 123, request, limit=10, offset=0)

        assert isinstance(result, AnalyticsResponse)
        assert result.analytics_type == AnalyticsType.DASHBOARD_CALL_TRENDS.value
        assert result.data == expected_data
        mock_processor._get_dashboard_call_trends.assert_awaited_once_with(
            current_user_id=1,
            partner_id=123,
            request_data=DashboardFollowupTrendsRequest(
                time_range="1722470400000-1726444800000",
                service_board_id=[40, 41],
                metric_filter="agent_missed_calls",
                trend_basis="Weekly",
            ),
            limit=10,
            offset=0,
        )
        mock_logger.info.assert_any_call(
            f"Successfully generated analytics for {AnalyticsType.DASHBOARD_CALL_TRENDS.value}"
        )

    async def test_process_analytics_dashboard_call_trends_invalid_payload(
        self, setup_analytics_base
    ):
        service, mock_processor, mock_logger = setup_analytics_base

        mock_processor._get_dashboard_call_trends.side_effect = AssertionError(
            "Processor method should not be called"
        )

        request = {
            "analytics_type": AnalyticsType.DASHBOARD_CALL_TRENDS.value,
            "data": {
                "time_range": 12345,  # invalid type
                "service_board_id": "wrong",  # invalid type
                "metric_filter": 999,  # invalid type
                "trend_basis": "Yearly",  # invalid value
            },
        }

        with pytest.raises(PayloadValidationError) as exc_info:
            await service.process_analytics(1, 123, request, limit=10, offset=0)

        assert (
            f"Invalid payload for analytics type '{AnalyticsType.DASHBOARD_CALL_TRENDS.value}'"
            in str(exc_info.value)
        )

        assert any(
            f"Invalid payload for analytics type {AnalyticsType.DASHBOARD_CALL_TRENDS.value}:"
            in str(call)
            for call in mock_logger.error.call_args_list
        )
