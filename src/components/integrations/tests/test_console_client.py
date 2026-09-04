from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.integrations.console.console_client import TalkoConsoleClient


class TestConsoleClient:

    @pytest.fixture
    def mock_logger(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_get_agent_by_ivr_phone_success(self, mock_logger):
        """Test successful agent retrieval with status 'success'."""
        with patch(
            "src.components.integrations.console.console_client.aiohttp.ClientSession"
        ) as mock_session_cls:
            # Setup mock response
            mock_session = mock_session_cls.return_value
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json.return_value = {
                "status": "success",
                "data": {"id": 101, "name": "Test Agent"},
            }
            mock_session.get.return_value.__aenter__.return_value = mock_resp
            # Re-patch API key to ensure it's present
            with patch(
                "src.components.integrations.console.console_constants.TalkoConsoleApiConstants.CONSOLE_API_KEY",
                "test-key",
            ):
                client = TalkoConsoleClient(mock_logger)
                result = await client.get_agent_by_ivr_phone(100, "+919988776655")

                assert result["id"] == 101
                assert result["name"] == "Test Agent"
                mock_session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_agent_by_ivr_phone_empty_input(self, mock_logger):
        """Verify early return when phone number is empty/whitespace."""
        client = TalkoConsoleClient(mock_logger)
        result = await client.get_agent_by_ivr_phone(100, "   ")

        assert result == {}
        mock_logger.warning.assert_called_with(
            "Empty IVR phone — skipping agent lookup"
        )

    @pytest.mark.asyncio
    async def test_get_agent_by_ivr_phone_api_key_missing(self, mock_logger):
        """Verify behavior when API key is not configured."""
        with patch(
            "src.components.integrations.console.console_constants.TalkoConsoleApiConstants.CONSOLE_API_KEY",
            "",
        ):
            client = TalkoConsoleClient(mock_logger)
            client.api_key = None  # Ensure it's None
            result = await client.get_agent_by_ivr_phone(100, "+919988776655")

            assert result == {}
            mock_logger.error.assert_called_with(
                "Console API key missing — cannot fetch agent"
            )

    @pytest.mark.asyncio
    async def test_get_agent_by_ivr_phone_http_error(self, mock_logger):
        """Test handling of non-200 HTTP status codes."""
        with patch(
            "src.components.integrations.console.console_client.aiohttp.ClientSession"
        ) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_resp = AsyncMock()
            mock_resp.status = 404
            mock_resp.text.return_value = "Not Found"
            mock_session.get.return_value.__aenter__.return_value = mock_resp

            client = TalkoConsoleClient(mock_logger)
            client.api_key = "valid-key"
            result = await client.get_agent_by_ivr_phone(100, "+919988776655")

            assert result == {}
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_get_agent_by_ivr_phone_exception(self, mock_logger):
        """Test handling of request exceptions (e.g., timeout)."""
        with patch(
            "src.components.integrations.console.console_client.aiohttp.ClientSession"
        ) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.get.side_effect = Exception("Connection Timeout")

            client = TalkoConsoleClient(mock_logger)
            client.api_key = "valid-key"
            result = await client.get_agent_by_ivr_phone(100, "+919988776655")

            assert result == {}
            mock_logger.exception.assert_called()

    @pytest.mark.asyncio
    async def test_close_session(self, mock_logger):
        """Ensure the session is closed correctly."""
        with patch(
            "src.components.integrations.console.console_client.aiohttp.ClientSession"
        ) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.closed = False
            mock_session.close = AsyncMock()

            client = TalkoConsoleClient(mock_logger)
            await client.close()

            mock_session.close.assert_called_once()
