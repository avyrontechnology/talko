from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.analytics.base import TalkoAnalyticsBase
from src.components.analytics.dto import (
    TalkoAgentCallAnalyticsRequest,
    TalkoAgentTalkTimeDistributionRequest,
    TalkoDashboardFollowupTrendsRequest,
    TalkoPartnerServiceBoardRequest,
    TalkoTotalAgentTalkTimeRequest,
)
from src.components.analytics.processor import TalkoAnalyticsProcessor
from src.exceptions import TalkoPayloadValidationError


@pytest.mark.asyncio
class TestAnalyticsProcessor:
    @pytest.fixture
    def setup_processor(self):
        mock_repo = AsyncMock()
        mock_logger = MagicMock()
        mock_grpc_client = AsyncMock()
        mock_user_hierarchy = AsyncMock()
        processor = TalkoAnalyticsProcessor(
            analytics_repository=mock_repo,
            logger=mock_logger,
            grpc_client=mock_grpc_client,
            user_hierarchy=mock_user_hierarchy,
        )
        # Mock user_hierarchy_data to return agent_ids and user_role
        mock_user_hierarchy.get_user_hierarchy_data.return_value = [1, 2, 3]
        mock_grpc_client.get_user_roles.return_value = {"hierarchy": 3}
        return processor, mock_repo, mock_logger, mock_grpc_client, mock_user_hierarchy

    async def test_get_agent_call_analytics_success(self, setup_processor):
        processor, mock_repo, mock_logger, _, _ = setup_processor

        request = TalkoAgentCallAnalyticsRequest(
            time_range="1735689600000-1738272000000",  # 2025-01-01 to 2025-01-31
            agents=[1, 2],
            service_board_id=[1, 3],
        )

        expected_result = {"analytics": "agent_calls", "total_count": 10}
        mock_repo.get_agent_call_analytics.return_value = expected_result

        result = await processor._get_agent_call_analytics(
            current_user_id=101,
            partner_id=202,
            request_data=request,
            limit=10,
            offset=1,
        )

        assert result == expected_result
        mock_repo.get_agent_call_analytics.assert_awaited_once_with(
            partner_id=202,
            start_date=1735689600,  # Converted from ms to s
            end_date=1738272000,
            agents=[1, 2, 3],  # From mocked user_hierarchy_data
            service_board_id=[1, 3],
            limit=10,
            offset=1,
            user_role=3,  # From mocked get_user_roles
        )
        mock_logger.info.assert_any_call(
            "Fetching agent call analytics for user_id=101, partner_id=202, agents=[1, 2], date_range=(1735689600, 1738272000), limit=10, offset=1"
        )

    async def test_get_agent_call_analytics_failure(self, setup_processor):
        processor, mock_repo, mock_logger, _, _ = setup_processor

        request = TalkoAgentCallAnalyticsRequest(
            time_range="1735689600000-1738272000000",
            agents=[3],
        )

        mock_repo.get_agent_call_analytics.side_effect = Exception("DB error")

        with pytest.raises(Exception) as exc_info:
            await processor._get_agent_call_analytics(
                current_user_id=11,
                partner_id=22,
                request_data=request,
                limit=10,
                offset=1,
            )

        assert str(exc_info.value) == "DB error"
        mock_logger.error.assert_any_call(
            "Error in agent call analytics for user_id=11, partner_id=22, error=DB error"
        )

    async def test_get_total_agent_talk_time_success(self, setup_processor):
        processor, mock_repo, mock_logger, _, _ = setup_processor

        request = TalkoTotalAgentTalkTimeRequest(
            time_range="1738368000000-1740787200000",  # 2025-02-01 to 2025-02-28
            agents=[5, 6],
        )

        expected_result = {"total_talk_time": 120, "total_count": 5}
        mock_repo.get_total_agent_talk_time.return_value = expected_result

        result = await processor._get_total_agent_talk_time(
            current_user_id=33,
            partner_id=44,
            request_data=request,
            limit=10,
            offset=1,
        )

        assert result == expected_result
        mock_repo.get_total_agent_talk_time.assert_awaited_once_with(
            partner_id=44,
            start_date=1738368000,
            end_date=1740787200,
            agents=[1, 2, 3],
            service_board_id=None,
            limit=10,
            offset=1,
            user_role=3,
        )

    async def test_get_agent_talk_time_distribution_success(self, setup_processor):
        processor, mock_repo, mock_logger, _, _ = setup_processor

        request = TalkoAgentTalkTimeDistributionRequest(
            time_range="1740787200000-1743379200000",  # 2025-03-01 to 2025-03-31
            agents=[7],
        )

        expected_result = {"distribution": {"0-1min": 2, "1-5min": 3}, "total_count": 5}
        mock_repo.get_agent_talk_time_distribution.return_value = expected_result

        result = await processor._get_agent_talk_time_distribution(
            current_user_id=55,
            partner_id=66,
            request_data=request,
            limit=10,
            offset=1,
        )

        assert result == expected_result
        mock_repo.get_agent_talk_time_distribution.assert_awaited_once_with(
            partner_id=66,
            start_date=1740787200,
            end_date=1743379200,
            agents=[1, 2, 3],
            service_board_id=None,
            limit=10,
            offset=1,
            user_role=3,
        )

    async def test_get_partner_service_board_success(self, setup_processor):
        processor, mock_repo, mock_logger, _, _ = setup_processor

        request = TalkoPartnerServiceBoardRequest(
            time_range="1743465600000-1746057600000",  # 2025-04-01 to 2025-04-30
        )

        expected_result = {"service_board": "data", "total_count": 1}
        mock_repo.get_partner_service_board.return_value = expected_result

        result = await processor._get_partner_service_board(
            current_user_id=77,
            partner_id=88,
            request_data=request,
            limit=10,
            offset=1,
        )

        assert result == expected_result
        mock_repo.get_partner_service_board.assert_awaited_once_with(
            partner_id=88,
            start_date=1743465600,
            end_date=1746057600,
            service_board_id=None,
            limit=10,
            offset=1,
        )

    async def test_get_total_agent_talk_time_failure(self, setup_processor):
        processor, mock_repo, mock_logger, _, _ = setup_processor

        request = TalkoTotalAgentTalkTimeRequest(
            time_range="1738368000000-1740787200000",
            agents=[9],
        )

        mock_repo.get_total_agent_talk_time.side_effect = Exception(
            "Talk time DB error"
        )

        with pytest.raises(Exception) as exc_info:
            await processor._get_total_agent_talk_time(
                current_user_id=111,
                partner_id=222,
                request_data=request,
                limit=10,
                offset=1,
            )

        assert str(exc_info.value) == "Talk time DB error"
        mock_logger.error.assert_any_call(
            "Error in total agent talk time for user_id=111, partner_id=222, error=Talk time DB error"
        )

    async def test_get_agent_talk_time_distribution_failure(self, setup_processor):
        processor, mock_repo, mock_logger, _, _ = setup_processor

        request = TalkoAgentTalkTimeDistributionRequest(
            time_range="1740787200000-1743379200000",
            agents=[10],
        )

        mock_repo.get_agent_talk_time_distribution.side_effect = Exception(
            "Distribution error"
        )

        with pytest.raises(Exception) as exc_info:
            await processor._get_agent_talk_time_distribution(
                current_user_id=333,
                partner_id=444,
                request_data=request,
                limit=10,
                offset=1,
            )

        assert str(exc_info.value) == "Distribution error"
        mock_logger.error.assert_any_call(
            "Error in agent talk time distribution for user_id=333, partner_id=444, error=Distribution error"
        )

    async def test_get_partner_service_board_failure(self, setup_processor):
        processor, mock_repo, mock_logger, _, _ = setup_processor

        request = TalkoPartnerServiceBoardRequest(
            time_range="1743465600000-1746057600000",
        )

        mock_repo.get_partner_service_board.side_effect = Exception(
            "Service board failure"
        )

        with pytest.raises(Exception) as exc_info:
            await processor._get_partner_service_board(
                current_user_id=555,
                partner_id=666,
                request_data=request,
                limit=10,
                offset=1,
            )

        assert str(exc_info.value) == "Service board failure"
        mock_logger.error.assert_any_call(
            "Error in partner service board for user_id=555, partner_id=666, error=Service board failure"
        )

    async def test_get_dashboard_call_trends_success(self, setup_processor):
        processor, mock_repo, mock_logger, _, _ = setup_processor

        request = TalkoDashboardFollowupTrendsRequest(
            time_range="1722470400000-1726444800000",  # 2025-08-01 to 2025-09-15
            service_board_id=[40, 41],
            metric_filter="agent_missed_calls",
            trend_basis="Weekly",
        )

        expected_result = {
            "trend_basis": "Weekly",
            "selected_metric": "agent_missed_calls",
            "total_count": 13,
            "data": [
                {"period": "Week 1 (Aug 04 - Aug 10)", "count": 5},
                {"period": "Week 2 (Aug 11 - Aug 17)", "count": 8},
            ],
        }
        mock_repo.get_dashboard_call_trends.return_value = expected_result

        result = await processor._get_dashboard_call_trends(
            current_user_id=99,
            partner_id=100,
            request_data=request,
            limit=10,
            offset=0,
        )

        assert result == expected_result
        mock_repo.get_dashboard_call_trends.assert_awaited_once_with(
            partner_id=100,
            start_date=1722470400,
            end_date=1726444800,
            agents=[1, 2, 3],
            service_board_id=[40, 41],
            metric="agent_missed_calls",
            trend_basis="Weekly",
            limit=10,
            offset=0,
            user_role=3,
        )
        mock_logger.info.assert_any_call(
            "Fetching dashboard followup trends for user_id=99, partner_id=100, metric=agent_missed_calls, trend_basis=Weekly, date_range=(1722470400, 1726444800), limit=10, offset=0"
        )

    async def test_get_dashboard_call_trends_failure(self, setup_processor):
        processor, mock_repo, mock_logger, _, _ = setup_processor

        request = TalkoDashboardFollowupTrendsRequest(
            time_range="1722470400000-1726444800000",
            service_board_id=[40],
            metric_filter="agent_missed_calls",
            trend_basis="Weekly",
        )

        mock_repo.get_dashboard_call_trends.side_effect = Exception("Trend DB error")

        with pytest.raises(Exception) as exc_info:
            await processor._get_dashboard_call_trends(
                current_user_id=111,
                partner_id=222,
                request_data=request,
                limit=10,
                offset=0,
            )

        assert str(exc_info.value) == "Trend DB error"
        mock_logger.error.assert_any_call(
            "Error in dashboard followup trends for user_id=111, partner_id=222, error=Trend DB error"
        )

    async def test_parse_time_range_invalid_end_before_start_isolated(
        self, setup_processor
    ):
        processor, _, mock_logger, _, _ = setup_processor
        time_range = "1738272000000-1735689600000"

        with pytest.raises(ValueError) as exc_info:
            processor._parse_time_range(time_range)

        mock_logger.error.assert_any_call(
            "Invalid time_range: end timestamp (1735689600000) is before start timestamp (1738272000000)"
        )

    async def test_parse_time_range_invalid_format(self, setup_processor):
        processor, _, mock_logger, _, _ = setup_processor

        request = TalkoAgentCallAnalyticsRequest(
            time_range="invalid_time_range",  # Malformed time_range
            agents=[1, 2],
            service_board_id=[1, 3],
        )

        with pytest.raises(ValueError) as exc_info:
            await processor._get_agent_call_analytics(
                current_user_id=101,
                partner_id=202,
                request_data=request,
                limit=10,
                offset=1,
            )

        assert (
            str(exc_info.value)
            == "Invalid time_range format. Expected 'start_ms-end_ms', e.g., '1749148200000-1756992444404'"
        )
        mock_logger.error.assert_any_call(
            "Invalid time_range format: invalid literal for int() with base 10: 'invalid_time_range'"
        )

    @pytest.mark.asyncio
    async def test_parse_time_range_empty_or_none(self, setup_processor):
        processor, _, mock_logger, _, _ = setup_processor

        # Test with None
        result = processor._parse_time_range(None)
        assert result == (None, None)
        mock_logger.error.assert_not_called()

        # Test with empty string
        result = processor._parse_time_range("")
        assert result == (None, None)
        mock_logger.error.assert_not_called()
