from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.call_management.messages import (
    AGENT_NUMBER_IS_REQUIRED,
    HANGUP_URL_HANDLER_NOT_CONFIGURED,
    INVALID_PARAMETER,
    UNEXPECTED_API_RESPONSE,
)
from src.components.call_management.tata_tele.call_service import TalkoTataTeleCallHandler


@pytest.mark.asyncio
class TestTataTeleCallHandler:

    @pytest.fixture
    def handler(self):
        mock_logger = MagicMock()
        config = {
            "generic_url_handler": {
                "call_api": {
                    "endpoint": "https://fake-endpoint.com",
                    "auth_credentials": {"token": "Bearer fake-token"},
                }
            },
            "hangup_url_handler": {
                "endpoint": "https://fake-endpoint.com/hangup",
                "auth_credentials": {"token": "Bearer fake-hangup-token"},
                "headers": {"accept": "application/json"},
            },
            "live_calls_url_handler": {
                "endpoint": "https://fake-endpoint.com/live_calls",
                "auth_credentials": {"token": "Bearer fake-live-calls-token"},
                "headers": {"accept": "application/json"},
            },
        }
        return TalkoTataTeleCallHandler(
            config=config, logger=mock_logger, vendor_type="TATA"
        )

    async def test_make_call_success(self, handler):
        response_data = {"status": "success", "call_id": "abc123"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value=response_data)
            mock_post.return_value = mock_response

            result = await handler.make_call(
                to_number="9876543210",
                from_number="1234567890",
                agent_number="1122334455",
            )

            assert result == response_data
            handler.logger.info.assert_called()

    async def test_make_call_missing_agent_number(self, handler):
        with pytest.raises(ValueError) as exc_info:
            await handler.make_call(
                to_number="9876543210", from_number="1234567890", agent_number=None
            )
        assert AGENT_NUMBER_IS_REQUIRED in str(exc_info.value)
        handler.logger.error.assert_called_with(
            f"Failed to make TATA API call: {AGENT_NUMBER_IS_REQUIRED}"
        )

    async def test_make_call_invalid_parameter(self, handler):
        error_message = "Invalid phone number"
        error_response = {"message": error_message}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 400
            mock_response.json = MagicMock(return_value=error_response)
            mock_post.return_value = mock_response

            with pytest.raises(ValueError) as exc_info:
                await handler.make_call(
                    to_number="9876543210",
                    from_number="1234567890",
                    agent_number="1122334455",
                )

            assert INVALID_PARAMETER.format(error_message) in str(exc_info.value)
            handler.logger.error.assert_called()

    async def test_make_call_unexpected_response(self, handler):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response

            with pytest.raises(ValueError) as exc_info:
                await handler.make_call(
                    to_number="9876543210",
                    from_number="1234567890",
                    agent_number="1122334455",
                )

            assert UNEXPECTED_API_RESPONSE.format(500) in str(exc_info.value)
            handler.logger.error.assert_called()

    async def test_make_call_exception_handling(self, handler):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Connection timeout")

            with pytest.raises(ValueError) as exc_info:
                await handler.make_call(
                    to_number="9876543210",
                    from_number="1234567890",
                    agent_number="1122334455",
                )

            assert "TATA API call failed" in str(exc_info.value)
            handler.logger.error.assert_called()

    async def test_hangup_call_success(self, handler):
        response_data = {"Success": True, "Message": "Call hangup successfully"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value=response_data)
            mock_post.return_value = mock_response

            result = await handler.hangup_call(call_id="1627373566.350603")

            assert result == response_data
            called_kwargs = mock_post.call_args.kwargs
            assert called_kwargs["json"] == {"call_id": "1627373566.350603"}
            assert (
                called_kwargs["headers"]["Authorization"] == "Bearer fake-hangup-token"
            )

    async def test_hangup_call_missing_config(self):
        mock_logger = MagicMock()
        handler = TalkoTataTeleCallHandler(
            config={"generic_url_handler": {"call_api": {}}},
            logger=mock_logger,
            vendor_type="TATA",
        )

        with pytest.raises(ValueError) as exc_info:
            await handler.hangup_call(call_id="abc123")

        assert HANGUP_URL_HANDLER_NOT_CONFIGURED in str(exc_info.value)

    async def test_hangup_call_invalid_parameter(self, handler):
        error_message = "Invalid call_id"
        error_response = {"message": error_message}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 400
            mock_response.json = MagicMock(return_value=error_response)
            mock_post.return_value = mock_response

            with pytest.raises(ValueError) as exc_info:
                await handler.hangup_call(call_id="abc123")

            assert INVALID_PARAMETER.format(error_message) in str(exc_info.value)

    async def test_hangup_call_unexpected_response(self, handler):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response

            with pytest.raises(ValueError) as exc_info:
                await handler.hangup_call(call_id="abc123")

            assert UNEXPECTED_API_RESPONSE.format(500) in str(exc_info.value)

    async def test_hangup_call_exception_handling(self, handler):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Connection timeout")

            with pytest.raises(ValueError) as exc_info:
                await handler.hangup_call(call_id="abc123")

            assert "TATA hangup API call failed" in str(exc_info.value)

    async def test_find_live_call_id_resolved_on_first_attempt(self, handler):
        response_data = {
            "results": [
                {"customer_number": "0918103492952", "call_id": "CAXX-123"},
            ]
        }
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value=response_data)
            mock_get.return_value = mock_response

            result = await handler.find_live_call_id(
                did_number="917965802977",
                customer_number="+918103492952",
                poll_interval=0,
            )

            assert result == "CAXX-123"
            assert mock_get.call_count == 1

    async def test_find_live_call_id_resolved_as_raw_list_response(self, handler):
        response_data = [{"customer_number": "918103492952", "call_id": "CAXX-999"}]
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value=response_data)
            mock_get.return_value = mock_response

            result = await handler.find_live_call_id(
                did_number="917965802977",
                customer_number="918103492952",
                poll_interval=0,
            )

            assert result == "CAXX-999"

    async def test_find_live_call_id_resolved_on_retry(self, handler):
        empty_response = AsyncMock()
        empty_response.status_code = 200
        empty_response.json = MagicMock(return_value={"results": []})

        found_response = AsyncMock()
        found_response.status_code = 200
        found_response.json = MagicMock(
            return_value={
                "results": [{"customer_number": "918103492952", "call_id": "CAXX-456"}]
            }
        )

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [empty_response, found_response]

            result = await handler.find_live_call_id(
                did_number="917965802977",
                customer_number="918103492952",
                max_attempts=3,
                poll_interval=0,
            )

            assert result == "CAXX-456"
            assert mock_get.call_count == 2

    async def test_find_live_call_id_no_match_within_attempts(self, handler):
        empty_response = AsyncMock()
        empty_response.status_code = 200
        empty_response.json = MagicMock(return_value={"results": []})

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = empty_response

            result = await handler.find_live_call_id(
                did_number="917965802977",
                customer_number="918103492952",
                max_attempts=3,
                poll_interval=0,
            )

            assert result is None
            assert mock_get.call_count == 3

    async def test_find_live_call_id_not_configured_skips_http_call(self):
        mock_logger = MagicMock()
        handler = TalkoTataTeleCallHandler(
            config={"generic_url_handler": {"call_api": {}}},
            logger=mock_logger,
            vendor_type="TATA",
        )

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            result = await handler.find_live_call_id(
                did_number="917965802977", customer_number="918103492952"
            )

            assert result is None
            mock_get.assert_not_called()

    async def test_find_live_call_id_request_exception_returns_none(self, handler):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("connection reset")

            result = await handler.find_live_call_id(
                did_number="917965802977",
                customer_number="918103492952",
                max_attempts=2,
                poll_interval=0,
            )

            assert result is None
            assert mock_get.call_count == 2
