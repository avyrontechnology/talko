import asyncio
import base64
import importlib
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest
from grpc.aio import UnaryUnaryClientInterceptor
from starlette_context import context

from src.grpc_client.grpc_client import TalkoGRPCClient, logger
from src.grpc_interceptor.auth_interceptor import TalkoApiKeyClientInterceptor


class TalkoDummyAioRpcError(grpc.aio.AioRpcError):
    def __init__(self, message="Simulated error"):
        self._message = message

    def __str__(self):
        return self._message

    def code(self):
        return grpc.StatusCode.UNAVAILABLE

    def details(self):
        return self._message


class TalkoMockInterceptor(UnaryUnaryClientInterceptor):
    """Mock interceptor that inherits from UnaryUnaryClientInterceptor."""

    def __init__(self, api_key):
        self.api_key = api_key

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        return await continuation(client_call_details, request)


class TestGRPCClient:
    @pytest.fixture
    def mock_env_secure(self):
        # Clear environment variables
        os.environ.pop("CONSOLE_GRPC_HOST", None)
        os.environ.pop("CONSOLE_GRPC_PORT", None)
        os.environ.pop("CA", None)
        # Reload the environment module to clear cached values
        importlib.reload(
            sys.modules.get(
                "src.core.environment", importlib.import_module("src.core.environment")
            )
        )
        with patch("src.core.environment") as mock_env:
            mock_env.CONSOLE_GRPC_HOST = "localhost"
            mock_env.CONSOLE_GRPC_PORT = "50051"
            mock_env.CA = base64.b64encode(b"dummy_ca_cert").decode("utf-8")
            yield mock_env

    @pytest.fixture
    def mock_env_insecure(self):
        os.environ.pop("CONSOLE_GRPC_HOST", None)
        os.environ.pop("CONSOLE_GRPC_PORT", None)
        os.environ.pop("CA", None)
        importlib.reload(
            sys.modules.get(
                "src.core.environment", importlib.import_module("src.core.environment")
            )
        )
        with patch("src.core.environment") as mock_env:
            mock_env.CONSOLE_GRPC_HOST = "localhost"
            mock_env.CONSOLE_GRPC_PORT = "50051"
            mock_env.CA = "None"
            yield mock_env

    @pytest.fixture(autouse=True)
    def mock_starlette_context(self):
        """Mock the starlette_context to avoid KeyError."""
        with patch(
            "starlette_context.ctx._request_scope_context_storage"
        ) as mock_context_storage:
            mock_context_storage.get.return_value = {"X-Request-ID": "test-request-id"}
            yield mock_context_storage

    @pytest.fixture(autouse=True)
    def disable_dotenv(self):
        """Disable dotenv loading to prevent .env file interference."""
        with patch("src.core.environment.load_dotenv") as mock_load_dotenv:
            mock_load_dotenv.return_value = None
            yield

    @pytest.fixture
    def mock_logger(self):
        """Fixture to provide a mocked logger."""
        with patch("src.grpc_client.grpc_client.logger") as mock_logger:
            yield mock_logger

    def test_create_insecure_channel(self, mock_logger, mock_env_insecure):
        with patch(
            "src.grpc_client.grpc_client.grpc.aio.insecure_channel"
        ) as mock_insecure_channel:
            with patch(
                "src.grpc_client.grpc_client.TalkoApiKeyClientInterceptor",
                return_value=TalkoMockInterceptor(api_key="maglo-key"),
            ) as mock_interceptor:
                with patch("os.getenv") as mock_getenv:
                    mock_getenv.side_effect = lambda key, default=None: {
                        "CONSOLE_GRPC_HOST": "localhost",
                        "CONSOLE_GRPC_PORT": "50051",
                        "CA": "None",
                    }.get(key, default)
                    client = TalkoGRPCClient()
                    channel = client._create_insecure_channel("localhost:50051")

                mock_interceptor.assert_called_with(api_key="maglo-key")
                mock_insecure_channel.assert_called_with(
                    "localhost:50051", interceptors=[mock_interceptor.return_value]
                )
                assert isinstance(channel, MagicMock)

    @pytest.mark.asyncio
    async def test_close_channel(self, mock_logger, mock_env_secure):
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                "CONSOLE_GRPC_HOST": "localhost",
                "CONSOLE_GRPC_PORT": "50051",
                "CA": base64.b64encode(b"dummy_ca_cert").decode("utf-8"),
            }.get(key, default)
            client = TalkoGRPCClient()
            client.channel = AsyncMock()
            await client.close_channel()

            client.channel.close.assert_called_once()
            mock_logger.info.assert_called_with(
                f"Closing the gRPC channel: {client.channel}"
            )
            mock_logger.debug.assert_called_with("gRPC channel closed successfully")

    @pytest.mark.asyncio
    async def test_call_with_retry_success(self, mock_logger):
        mock_func = AsyncMock(return_value="success")
        wrapped_func = TalkoGRPCClient.call_with_retry(mock_func)
        result = await wrapped_func()

        assert result == "success"
        mock_func.assert_called_once()
        mock_logger.debug.assert_called_with(
            f"Calling {mock_func.__name__} (attempt 1)"
        )

    @pytest.mark.asyncio
    async def test_call_with_retry_failure(self, mock_logger):
        with patch("asyncio.sleep", new=AsyncMock()):
            mock_func = AsyncMock(side_effect=TalkoDummyAioRpcError())
            wrapped_func = TalkoGRPCClient.call_with_retry(mock_func)
            result = await wrapped_func()

            assert result is None
            assert mock_func.call_count == TalkoGRPCClient.MAX_RETRIES
            mock_logger.error.assert_called_with(
                f"Failed to execute {mock_func.__name__} after {TalkoGRPCClient.MAX_RETRIES} attempts"
            )

    @pytest.mark.asyncio
    async def test_call_with_retry_partial_success(self, mock_logger):
        with patch("asyncio.sleep", new=AsyncMock()):
            mock_func = AsyncMock(side_effect=[TalkoDummyAioRpcError(), "success"])
            wrapped_func = TalkoGRPCClient.call_with_retry(mock_func)
            result = await wrapped_func()

            assert result == "success"
            assert mock_func.call_count == 2
            mock_logger.info.assert_called_with(
                f"Retrying {mock_func.__name__} (attempt 2/{TalkoGRPCClient.MAX_RETRIES})"
            )
