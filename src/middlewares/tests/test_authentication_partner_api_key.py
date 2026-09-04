from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.middlewares.authentication import TalkoAuthMiddleware


@pytest.mark.asyncio
class TestHandleApiKeyPartnerBranch:
    @pytest.fixture
    def middleware(self):
        return TalkoAuthMiddleware(app=AsyncMock())

    @pytest.fixture
    def request_mock(self):
        req = MagicMock()
        req.state = MagicMock()
        return req

    async def test_new_format_key_never_touches_grpc(self, middleware, request_mock):
        partner_api_key_service = AsyncMock()
        partner_api_key_service.validate_and_get_partner.return_value = {
            "partner_id": 42,
            "api_key_id": "abc123",
        }
        partner_api_key_service.check_rate_limit.return_value = True
        call_next = AsyncMock(return_value="response")
        redis_pool = AsyncMock()

        with patch(
            "src.middlewares.authentication.TalkoRPCServiceFactory"
        ) as mock_rpc_factory:
            result = await middleware._handle_api_key(
                request=request_mock,
                api_key="tkp_live_abcdef1234567890",
                call_next=call_next,
                redis_pool=redis_pool,
                logger=MagicMock(),
                partner_api_key_service=partner_api_key_service,
            )

        assert result == "response"
        assert request_mock.state.user == {
            "partner_id": 42,
            "api_key_id": "abc123",
            "is_api_key_auth": True,
        }
        mock_rpc_factory.get_service.assert_not_called()
        redis_pool.get.assert_not_called()
        call_next.assert_awaited_once_with(request_mock)

    async def test_new_format_invalid_key_rejected(self, middleware, request_mock):
        partner_api_key_service = AsyncMock()
        partner_api_key_service.validate_and_get_partner.return_value = None
        call_next = AsyncMock()

        response = await middleware._handle_api_key(
            request=request_mock,
            api_key="tkp_live_invalid",
            call_next=call_next,
            redis_pool=AsyncMock(),
            logger=MagicMock(),
            partner_api_key_service=partner_api_key_service,
        )

        assert response.status_code == 401
        call_next.assert_not_called()

    async def test_new_format_rate_limited(self, middleware, request_mock):
        partner_api_key_service = AsyncMock()
        partner_api_key_service.validate_and_get_partner.return_value = {
            "partner_id": 42,
            "api_key_id": "abc123",
        }
        partner_api_key_service.check_rate_limit.return_value = False
        call_next = AsyncMock()

        response = await middleware._handle_api_key(
            request=request_mock,
            api_key="tkp_live_abcdef1234567890",
            call_next=call_next,
            redis_pool=AsyncMock(),
            logger=MagicMock(),
            partner_api_key_service=partner_api_key_service,
        )

        assert response.status_code == 429
        call_next.assert_not_called()

    async def test_old_format_key_falls_through_to_grpc_unchanged(
        self, middleware, request_mock
    ):
        # Regression guard: an old-style (non "tkp_live_"-prefixed) key must
        # still take the pre-existing gRPC-backed path, byte for byte.
        partner_api_key_service = AsyncMock()
        call_next = AsyncMock(return_value="response")
        redis_pool = AsyncMock()
        redis_pool.get.return_value = None

        with patch(
            "src.middlewares.authentication.TalkoRPCServiceFactory"
        ) as mock_rpc_factory:
            mock_grpc_client = AsyncMock()
            mock_grpc_client.validate_api_key.return_value = {
                "id": "old-key-id",
                "partner_id": 7,
                "is_active": True,
            }
            mock_rpc_factory.get_service.return_value = mock_grpc_client

            result = await middleware._handle_api_key(
                request=request_mock,
                api_key="opaque-console-issued-key",
                call_next=call_next,
                redis_pool=redis_pool,
                logger=MagicMock(),
                partner_api_key_service=partner_api_key_service,
            )

        assert result == "response"
        redis_pool.get.assert_called_once_with("api_key:opaque-console-issued-key")
        mock_grpc_client.validate_api_key.assert_awaited_once_with(
            api_key="opaque-console-issued-key"
        )
        partner_api_key_service.validate_and_get_partner.assert_not_called()
        assert request_mock.state.user == {
            "partner_id": 7,
            "api_key_id": "old-key-id",
            "is_api_key_auth": True,
        }
