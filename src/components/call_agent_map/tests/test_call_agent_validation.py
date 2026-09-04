from unittest.mock import AsyncMock, Mock

import pytest

from src.components.call_agent_map.validation import AgentMapperValidator


@pytest.mark.asyncio
class TestAgentMapperValidator:

    @pytest.fixture
    def mock_repository(self):
        repo = Mock()
        repo.get_agent_did_mapping = AsyncMock()
        return repo

    @pytest.fixture
    def mock_logger(self):
        return Mock()

    @pytest.fixture
    def validator(self, mock_repository, mock_logger):
        return AgentMapperValidator(repository=mock_repository, logger=mock_logger)

    async def test_validate_agent_not_already_mapped_success(
        self, validator, mock_repository, mock_logger
    ):
        """
        Test case where the agent is not already mapped.
        """
        mock_repository.get_agent_did_mapping.return_value = None

        await validator.validate_agent_not_already_mapped(agent_id=101)

        mock_repository.get_agent_did_mapping.assert_awaited_once_with(101)
        mock_logger.error.assert_not_called()

    async def test_validate_agent_already_mapped_raises_error(
        self, validator, mock_repository, mock_logger
    ):
        """
        Test case where the agent is already mapped and should raise ValueError.
        """
        mock_repository.get_agent_did_mapping.return_value = {
            "agent_id": 101,
            "partner_id": 2001,
        }

        with pytest.raises(
            ValueError, match="Agent ID is already mapped to another partner."
        ):
            await validator.validate_agent_not_already_mapped(agent_id=101)

        mock_repository.get_agent_did_mapping.assert_awaited_once_with(101)
        mock_logger.error.assert_called_once()
