from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from aiohttp import ClientResponseError

from src.components.integrations.console.console_client import TalkoConsoleClient


def make_client(api_key="test-key"):
    logger = MagicMock()
    with patch(
        "src.components.integrations.console.console_client.TalkoConsoleApiConstants"
    ) as mock_constants, patch(
        "src.components.integrations.console.console_client.aiohttp.ClientSession"
    ) as mock_session_cls:
        mock_constants.CONSOLE_API_KEY = api_key
        mock_constants.API_KEY_HEADER = "x-api-key"
        mock_constants.get_agent_by_ivr_phone_url.return_value = "https://console.example.com/console-service/v1/1/user/+911234567890/get_user_details_by_ivr"
        mock_session_cls.return_value = MagicMock()
        client = TalkoConsoleClient(logger=logger)
        client._mock_constants = mock_constants
    return client, logger


class TestConsoleClientInit:

    def test_warns_when_api_key_missing(self):
        logger = MagicMock()
        with patch(
            "src.components.integrations.console.console_client.TalkoConsoleApiConstants"
        ) as mock_constants, patch(
            "src.components.integrations.console.console_client.aiohttp.ClientSession"
        ):
            mock_constants.CONSOLE_API_KEY = ""
            TalkoConsoleClient(logger=logger)
        logger.warning.assert_called_once()
        assert "missing" in logger.warning.call_args[0][0].lower()

    def test_no_warning_when_api_key_present(self):
        logger = MagicMock()
        with patch(
            "src.components.integrations.console.console_client.TalkoConsoleApiConstants"
        ) as mock_constants, patch(
            "src.components.integrations.console.console_client.aiohttp.ClientSession"
        ):
            mock_constants.CONSOLE_API_KEY = "valid-key"
            TalkoConsoleClient(logger=logger)
        logger.warning.assert_not_called()


class TestGetAgentByIvrPhoneGuards:

    @pytest.mark.asyncio
    async def test_returns_empty_for_blank_ivr_phone(self):
        client, logger = make_client()
        result = await client.get_agent_by_ivr_phone(partner_id=1, ivr_phone="   ")
        assert result == {}
        logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_returns_empty_when_api_key_missing(self):
        logger = MagicMock()
        with patch(
            "src.components.integrations.console.console_client.TalkoConsoleApiConstants"
        ) as mock_constants, patch(
            "src.components.integrations.console.console_client.aiohttp.ClientSession"
        ):
            mock_constants.CONSOLE_API_KEY = ""
            mock_constants.API_KEY_HEADER = "x-api-key"
            client = TalkoConsoleClient(logger=logger)

        result = await client.get_agent_by_ivr_phone(
            partner_id=1, ivr_phone="+911234567890"
        )
        assert result == {}
        logger.error.assert_called()


class TestGetAgentByIvrPhoneHttpResponses:

    def _make_response(self, status: int, json_data=None, text_data="error"):
        resp = AsyncMock()
        resp.status = status
        resp.json = AsyncMock(return_value=json_data or {})
        resp.text = AsyncMock(return_value=text_data)
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    @pytest.mark.asyncio
    async def test_returns_agent_data_on_success(self):
        client, logger = make_client()
        agent_payload = {"id": 42, "name": "Test Agent"}
        resp = self._make_response(
            200, json_data={"status": "success", "data": agent_payload}
        )

        mock_session = MagicMock()
        mock_session.get.return_value = resp
        client.session = mock_session

        result = await client.get_agent_by_ivr_phone(
            partner_id=1, ivr_phone="+911234567890"
        )
        assert result == agent_payload
        logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_returns_empty_on_non_200_status(self):
        client, logger = make_client()
        resp = self._make_response(404, text_data="Not Found")

        mock_session = MagicMock()
        mock_session.get.return_value = resp
        client.session = mock_session

        result = await client.get_agent_by_ivr_phone(
            partner_id=1, ivr_phone="+911234567890"
        )
        assert result == {}
        logger.warning.assert_called()
        assert "404" in str(logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_returns_empty_on_non_success_status_field(self):
        client, logger = make_client()
        resp = self._make_response(
            200, json_data={"status": "failure", "message": "user not found"}
        )

        mock_session = MagicMock()
        mock_session.get.return_value = resp
        client.session = mock_session

        result = await client.get_agent_by_ivr_phone(
            partner_id=1, ivr_phone="+911234567890"
        )
        assert result == {}
        logger.info.assert_called()
        assert "user not found" in str(logger.info.call_args)

    @pytest.mark.asyncio
    async def test_returns_empty_on_success_but_missing_data_key(self):
        client, logger = make_client()
        resp = self._make_response(
            200, json_data={"status": "success"}
        )  # no "data" key

        mock_session = MagicMock()
        mock_session.get.return_value = resp
        client.session = mock_session

        result = await client.get_agent_by_ivr_phone(
            partner_id=1, ivr_phone="+911234567890"
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_and_logs_exception_on_network_error(self):
        client, logger = make_client()

        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection refused")
        client.session = mock_session

        result = await client.get_agent_by_ivr_phone(
            partner_id=1, ivr_phone="+911234567890"
        )
        assert result == {}
        logger.exception.assert_called()
        assert "Connection refused" in str(logger.exception.call_args)

    @pytest.mark.asyncio
    async def test_ivr_phone_last_6_digits_used_in_debug_log(self):
        """Sensitive phone numbers should only be partially logged."""
        client, logger = make_client()
        resp = self._make_response(
            200, json_data={"status": "success", "data": {"id": 1}}
        )

        mock_session = MagicMock()
        mock_session.get.return_value = resp
        client.session = mock_session

        await client.get_agent_by_ivr_phone(partner_id=1, ivr_phone="+919988776655")

        # Ensure debug was called and full phone is not logged
        all_debug_calls = str(logger.debug.call_args_list)
        assert "+919988" not in all_debug_calls  # full prefix hidden
        assert "776655" in all_debug_calls  # last 6 digits present


class TestConsoleClientClose:

    @pytest.mark.asyncio
    async def test_close_calls_session_close_when_open(self):
        client, logger = make_client()
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        client.session = mock_session

        await client.close()

        mock_session.close.assert_awaited_once()
        logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_close_skips_session_close_when_already_closed(self):
        client, logger = make_client()
        mock_session = MagicMock()
        mock_session.closed = True
        mock_session.close = AsyncMock()
        client.session = mock_session

        await client.close()

        mock_session.close.assert_not_awaited()
