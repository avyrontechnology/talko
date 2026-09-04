from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.common.user_hierarchy import TalkoUserHierarchy


@pytest.mark.asyncio
class TestUserHierarchy:
    @pytest.fixture
    def mock_grpc_client(self):
        client = MagicMock()
        client.get_user_child_details = AsyncMock()
        client.get_user_child_hierarchy = AsyncMock()
        return client

    @pytest.fixture
    def mock_logger(self):
        return MagicMock()

    @pytest.fixture
    def user_hierarchy(self, mock_grpc_client, mock_logger):
        return TalkoUserHierarchy(grpc_client=mock_grpc_client, logger=mock_logger)

    async def test_get_user_hierarchy_data_success(
        self, user_hierarchy, mock_grpc_client, mock_logger
    ):
        # Arrange
        current_user_id = 100
        mock_grpc_client.get_user_child_details.return_value = [200, 300]
        mock_grpc_client.get_user_child_hierarchy.return_value = {
            200: {"user_id": 200, "child_ids": [400]},
            300: {"user_id": 300, "child_ids": [500, 600]},
        }

        request_data = MagicMock()
        request_data.agents = []  # no filtering

        # Act
        result = await user_hierarchy.get_user_hierarchy_data(
            request_data, current_user_id
        )

        # Assert
        expected = sorted([100, 200, 300, 400, 500, 600])
        assert sorted(result) == expected
        mock_grpc_client.get_user_child_details.assert_called_once_with(current_user_id)
        mock_grpc_client.get_user_child_hierarchy.assert_called_once_with([200, 300])
        mock_logger.info.assert_any_call(
            f"Fetching user hierarchy for user_id={current_user_id}, filter_agents={[]}"
        )

    async def test_get_user_hierarchy_data_with_filter(
        self, user_hierarchy, mock_grpc_client
    ):
        # Arrange
        current_user_id = 101
        mock_grpc_client.get_user_child_details.return_value = [201]
        mock_grpc_client.get_user_child_hierarchy.return_value = {
            201: {"user_id": 201, "child_ids": [301]}
        }

        request_data = MagicMock()
        request_data.agents = [201, 301]  # filter applied

        # Act
        result = await user_hierarchy.get_user_hierarchy_data(
            request_data, current_user_id
        )

        # Assert
        assert sorted(result) == [201, 301]  # only filtered IDs present

    async def test_get_user_hierarchy_data_filter_excludes_all(
        self, user_hierarchy, mock_grpc_client
    ):
        # Arrange
        current_user_id = 102
        mock_grpc_client.get_user_child_details.return_value = [202]
        mock_grpc_client.get_user_child_hierarchy.return_value = {
            202: {"user_id": 202, "child_ids": [302]}
        }

        request_data = MagicMock()
        request_data.agents = [999]  # filter with non-existent agent

        # Act
        result = await user_hierarchy.get_user_hierarchy_data(
            request_data, current_user_id
        )

        # Assert
        assert result == []  # filter excludes everything

    async def test_get_user_hierarchy_data_no_children(
        self, user_hierarchy, mock_grpc_client
    ):
        # Arrange
        current_user_id = 103
        mock_grpc_client.get_user_child_details.return_value = []
        mock_grpc_client.get_user_child_hierarchy.return_value = {}

        request_data = MagicMock()
        request_data.agents = []

        # Act
        result = await user_hierarchy.get_user_hierarchy_data(
            request_data, current_user_id
        )

        # Assert
        assert result == [103]  # only current user remains

    async def test_get_user_hierarchy_data_request_data_none(
        self, user_hierarchy, mock_grpc_client
    ):
        # Arrange
        current_user_id = 104
        mock_grpc_client.get_user_child_details.return_value = [204]
        mock_grpc_client.get_user_child_hierarchy.return_value = {
            204: {"user_id": 204, "child_ids": []}
        }

        request_data = None  # no filtering at all

        # Act
        result = await user_hierarchy.get_user_hierarchy_data(
            request_data, current_user_id
        )

        # Assert
        assert sorted(result) == [104, 204]
