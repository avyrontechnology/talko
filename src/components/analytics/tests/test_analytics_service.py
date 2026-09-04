from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.analytics.dto import TalkoAnalyticsResponse
from src.components.analytics.enums import TalkoAnalyticsType
from src.components.analytics.services import TalkoAnalyticsService
from src.grpc_client.constants import TalkoGrpcServices


@pytest.mark.asyncio
class TestAnalyticsService:

    async def test_get_analytics_success_without_agents(self):
        """Test generic analytics retrieval without agent-specific enrichment"""
        # Arrange
        mock_analytics_base = MagicMock()
        mock_logger = MagicMock()

        fake_response = TalkoAnalyticsResponse(
            status="success",
            message="ok",
            analytics_type="generic_type",
            data={"foo": "bar"},  # No total_count in data for generic_type
        )
        mock_analytics_base.process_analytics = AsyncMock(return_value=fake_response)

        service = TalkoAnalyticsService(
            analytics_base=mock_analytics_base,
            logger=mock_logger,
        )

        # Act
        result = await service.get_analytics(
            current_user_id=1,
            partner_id=123,
            analytics_request={"analytics_type": "generic_type"},
            limit=10,
            offset=1,
        )

        # Assert
        assert result == fake_response
        assert not hasattr(result, "total_count")  # Ensure no total_count at root
        mock_logger.info.assert_any_call(
            "Processing analytics for partner_id: 123, analytics_type: generic_type"
        )
        mock_logger.info.assert_any_call(
            "Successfully retrieved analytics for partner_id: 123"
        )
        mock_analytics_base.process_analytics.assert_awaited_once_with(
            current_user_id=1,
            partner_id=123,
            analytics_request={"analytics_type": "generic_type"},
            limit=10,
            offset=1,
        )

    async def test_get_analytics_success_with_agents(self):
        """Test agent analytics enrichment with gRPC client"""
        # Arrange
        mock_analytics_base = MagicMock()
        mock_logger = MagicMock()

        fake_response = TalkoAnalyticsResponse(
            status="success",
            message="ok",
            analytics_type=TalkoAnalyticsType.AGENT_CALL_ANALYTICS.value,
            data={
                "agents": [
                    {
                        "agent_id": 1,
                        "total_calls": 10,
                        "unique_calls": 2,
                        "connected_calls": 8,
                        "missed_calls": 2,
                        "total_placed_calls": 8,  # Updated from total_connected_calls
                        "total_connected_unique_calls": 1,
                    },
                    {
                        "agent_id": 2,
                        "total_calls": 5,
                        "unique_calls": 3,
                        "connected_calls": 4,
                        "missed_calls": 1,
                        "total_placed_calls": 4,  # Updated from total_connected_calls
                        "total_connected_unique_calls": 2,
                    },
                ],
                "total_count": 2,
            },
        )
        mock_analytics_base.process_analytics = AsyncMock(return_value=fake_response)

        service = TalkoAnalyticsService(
            analytics_base=mock_analytics_base,
            logger=mock_logger,
        )

        # Patch gRPC client
        with patch(
            "src.components.analytics.services.TalkoRPCServiceFactory.get_service"
        ) as mock_get_service:
            mock_grpc_client = AsyncMock()
            mock_grpc_client.get_service_board_users_details = AsyncMock(
                return_value={1: {"name": "Alice"}, 2: {"name": "Bob"}}
            )
            mock_get_service.return_value = mock_grpc_client

            # Act
            result = await service.get_analytics(
                current_user_id=1,
                partner_id=123,
                analytics_request={
                    "analytics_type": TalkoAnalyticsType.AGENT_CALL_ANALYTICS.value
                },
                limit=10,
                offset=1,
            )

            # Assert
            agent_names = [agent["agent_name"] for agent in result.data["agents"]]
            assert agent_names == ["Alice", "Bob"]
            assert result.data["total_count"] == 2
            assert not hasattr(result, "total_count")  # Ensure no total_count at root
            assert (
                result.data["agents"][0]["total_placed_calls"] == 8
            )  # Verify total_placed_calls
            assert (
                result.data["agents"][1]["total_placed_calls"] == 4
            )  # Verify total_placed_calls
            mock_grpc_client.get_service_board_users_details.assert_awaited_once_with(
                [1, 2]
            )
            mock_logger.info.assert_any_call(
                "Processing analytics for partner_id: 123, analytics_type: agent_call_analytics"
            )
            mock_logger.info.assert_any_call(
                "Successfully retrieved analytics for partner_id: 123"
            )
            mock_analytics_base.process_analytics.assert_awaited_once_with(
                current_user_id=1,
                partner_id=123,
                analytics_request={
                    "analytics_type": TalkoAnalyticsType.AGENT_CALL_ANALYTICS.value
                },
                limit=10,
                offset=1,
            )

    async def test_get_analytics_failure(self):
        """Test that service logs and raises exceptions correctly"""
        # Arrange
        mock_analytics_base = MagicMock()
        mock_logger = MagicMock()
        mock_analytics_base.process_analytics = AsyncMock(side_effect=Exception("boom"))

        service = TalkoAnalyticsService(
            analytics_base=mock_analytics_base,
            logger=mock_logger,
        )

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await service.get_analytics(
                current_user_id=1,
                partner_id=123,
                analytics_request={"analytics_type": "any_type"},
                limit=10,
                offset=1,
            )

        # Assert
        assert str(exc_info.value) == "boom"
        mock_logger.error.assert_any_call(
            "Error processing analytics for partner_id: 123: boom"
        )
        mock_analytics_base.process_analytics.assert_awaited_once_with(
            current_user_id=1,
            partner_id=123,
            analytics_request={"analytics_type": "any_type"},
            limit=10,
            offset=1,
        )
