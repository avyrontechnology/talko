import asyncio
import base64
import importlib
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest
from grpc.aio import UnaryUnaryClientInterceptor
from starlette_context import context

from src.components.common.responses import InternalServerErrorResponse
from src.grpc_client.client_services.auth_service_client import (
    AuthServiceClient,
    logger,
)


class DummyAioRpcError(grpc.aio.AioRpcError):
    def __init__(self, message="Simulated error"):
        self._message = message

    def __str__(self):
        return self._message

    def code(self):
        return grpc.StatusCode.UNAVAILABLE

    def details(self):
        return self._message


class MockInterceptor(UnaryUnaryClientInterceptor):
    """Mock interceptor that inherits from UnaryUnaryClientInterceptor."""

    def __init__(self, api_key):
        self.api_key = api_key

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        return await continuation(client_call_details, request)


@pytest.mark.asyncio
class TestAuthServiceClient:
    @pytest.fixture
    def mock_env_secure(self):
        # Clear environment variables
        for key in ["CONSOLE_GRPC_HOST", "CONSOLE_GRPC_PORT", "CA"]:
            os.environ.pop(key, None)
        # Force reload of environment module
        importlib.reload(
            sys.modules.get(
                "src.core.environment", importlib.import_module("src.core.environment")
            )
        )
        with patch("src.core.environment") as mock_env:
            mock_env.CONSOLE_GRPC_HOST = "localhost"
            mock_env.CONSOLE_GRPC_PORT = "50051"
            mock_env.CA = base64.b64encode(b"dummy_ca_cert").decode("utf-8")
            print(
                f"Mocked environment: host={mock_env.CONSOLE_GRPC_HOST}, port={mock_env.CONSOLE_GRPC_PORT}, ca={mock_env.CA}"
            )
            yield mock_env

    @pytest.fixture(autouse=True)
    def mock_starlette_context(self):
        with patch(
            "starlette_context.ctx._request_scope_context_storage"
        ) as mock_context_storage:
            mock_context_storage.get.return_value = {"X-Request-ID": "test-request-id"}
            yield mock_context_storage

    @pytest.fixture(autouse=True)
    def disable_dotenv(self):
        with patch("src.core.environment.load_dotenv") as mock_load_dotenv:
            mock_load_dotenv.return_value = None
            print("Disabled dotenv loading")
            yield

    @pytest.fixture
    def mock_logger(self):
        with patch(
            "src.grpc_client.client_services.auth_service_client.logger"
        ) as mock_logger:
            yield mock_logger

    @pytest.fixture
    def mock_auth_stub(self):
        with patch("src.pub.auth_pb2_grpc.AuthServiceStub") as mock_stub:
            yield mock_stub.return_value

    @pytest.fixture
    def client(self, mock_env_secure, mock_auth_stub):
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                "CONSOLE_GRPC_HOST": "localhost",
                "CONSOLE_GRPC_PORT": "50051",
                "CA": base64.b64encode(b"dummy_ca_cert").decode("utf-8"),
            }.get(key, default)
            print(
                f"Mocked os.getenv: CONSOLE_GRPC_HOST={mock_getenv('CONSOLE_GRPC_HOST')}"
            )
            client = AuthServiceClient()
            print(f"Client initialized with server address: {client.server_address}")
            yield client

    async def test_validate_token_success(self, client, mock_logger, mock_auth_stub):
        token = "test-token"
        correlation_id = "test-corr-id"
        mock_response = MagicMock()
        mock_response.is_active = True
        mock_response.session_id = "session-123"
        mock_response.user_id = 123  # Integer to match gRPC response
        mock_response.partner_id = "partner-123"
        mock_auth_stub.ValidateToken = AsyncMock(return_value=mock_response)

        result = await client.validate_token(token, correlation_id)

        mock_auth_stub.ValidateToken.assert_called_once()
        assert (
            mock_auth_stub.ValidateToken.call_args[0][0].mcontext.correlation_id
            == correlation_id
        )
        assert mock_auth_stub.ValidateToken.call_args[0][0].mbody.token == token
        assert result == {
            "is_active": True,
            "user_session_id": "session-123",
            "user_id": 123,  # Integer
            "partner_id": "partner-123",
        }
        mock_logger.info.assert_any_call(
            f"Sending ValidateToken request for token: {token} correlation_id: {correlation_id}"
        )
        mock_logger.info.assert_any_call("Received response for user: True")

    async def test_validate_token_failure(self, client, mock_logger, mock_auth_stub):
        token = "test-token"
        correlation_id = "test-corr-id"
        mock_auth_stub.ValidateToken = AsyncMock(side_effect=DummyAioRpcError())

        await client.validate_token(token, correlation_id)

        mock_auth_stub.ValidateToken.assert_called_once()
        assert (
            mock_auth_stub.ValidateToken.call_args[0][0].mcontext.correlation_id
            == correlation_id
        )
        assert mock_auth_stub.ValidateToken.call_args[0][0].mbody.token == token

    async def test_get_user_child_hierarchy_success(
        self, client, mock_logger, mock_auth_stub
    ):
        user_id = 123
        mock_hierarchy = MagicMock()
        mock_hierarchy.user_id = user_id
        mock_hierarchy.child_ids = [1, 2]
        mock_response = MagicMock()
        mock_response.child_hierarchy = [mock_hierarchy]
        mock_auth_stub.GetUserChildHierarchy = AsyncMock(return_value=mock_response)

        result = await client.get_user_child_hierarchy(user_id)

        mock_auth_stub.GetUserChildHierarchy.assert_called_once()
        # ✅ FIX: Check user_ids (list), not user_id
        assert mock_auth_stub.GetUserChildHierarchy.call_args[0][0].user_ids == [123]
        assert result == {
            123: {"user_id": 123, "child_ids": [1, 2]},
        }
        mock_logger.info.assert_any_call(
            f"Sending GetUserChildHierarchy request for user_ids: {[user_id]}"
        )
        mock_logger.info.assert_any_call(
            f"Received child hierarchies for user_ids: {[user_id]}"
        )

    async def test_get_user_child_hierarchy_failure(
        self, client, mock_logger, mock_auth_stub
    ):
        user_id = 123
        mock_auth_stub.GetUserChildHierarchy = AsyncMock(side_effect=DummyAioRpcError())

        result = await client.get_user_child_hierarchy(user_id)

        mock_auth_stub.GetUserChildHierarchy.assert_called_once()
        # ✅ FIX: Check user_ids
        assert mock_auth_stub.GetUserChildHierarchy.call_args[0][0].user_ids == [123]
        assert result == {}
        mock_logger.info.assert_called_once_with(
            f"Sending GetUserChildHierarchy request for user_ids: {[user_id]}"
        )
        mock_logger.error.assert_called_once_with(
            "Error during GetUserChildHierarchy call: Simulated error"
        )

    async def test_get_user_child_details_success(
        self, client, mock_logger, mock_auth_stub
    ):
        user_id = 123  # Integer
        mock_user = MagicMock()
        mock_user.user_id = 1  # Integer
        mock_user.name = "Child One"
        mock_user.is_active = True
        mock_user.is_suspended = False
        mock_response = MagicMock()
        mock_response.user_detail = [mock_user]
        mock_auth_stub.GetUserChildDetails = AsyncMock(return_value=mock_response)

        result = await client.get_user_child_details(user_id)

        mock_auth_stub.GetUserChildDetails.assert_called_once()
        assert mock_auth_stub.GetUserChildDetails.call_args[0][0].user_id == 123
        assert result == {
            1: {
                "user_id": 1,
                "name": "Child One",
                "is_active": True,
                "is_suspended": False,
            }
        }
        mock_logger.info.assert_any_call(
            f"Sending GetUserChildHierarchy request for user_id: {user_id}"
        )

    async def test_get_user_child_details_failure(
        self, client, mock_logger, mock_auth_stub
    ):
        user_id = 123  # Integer
        mock_auth_stub.GetUserChildDetails = AsyncMock(side_effect=DummyAioRpcError())

        result = await client.get_user_child_details(user_id)

        mock_auth_stub.GetUserChildDetails.assert_called_once()
        assert mock_auth_stub.GetUserChildDetails.call_args[0][0].user_id == 123
        assert result == {}
        mock_logger.info.assert_called_once_with(
            f"Sending GetUserChildHierarchy request for user_id: {user_id}"
        )
        mock_logger.error.assert_called_once_with(
            "Error during GetUserChildHierarchy call: Simulated error"
        )

    async def test_get_user_details_success(self, client, mock_logger, mock_auth_stub):
        user_id = 123  # Integer
        mock_user = MagicMock()
        mock_user.user_id = 123  # Integer
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"
        mock_user.partner_id = "partner-123"
        mock_user.role_hierarchy_level = 1
        mock_response = MagicMock()
        mock_response.user_profile = mock_user
        mock_auth_stub.GetUserDetails = AsyncMock(return_value=mock_response)

        result = await client.get_user_details(user_id)

        mock_auth_stub.GetUserDetails.assert_called_once()
        assert mock_auth_stub.GetUserDetails.call_args[0][0].user_id == 123
        assert result == {
            "user_id": 123,
            "name": "Test User",
            "email": "test@example.com",
            "partner_id": "partner-123",
            "role_hierarchy_level": 1,
        }
        mock_logger.info.assert_any_call(
            f"Sending GetUserDetails request for user_id: {user_id}"
        )

    async def test_get_user_details_failure(self, client, mock_logger, mock_auth_stub):
        user_id = 123  # Integer
        mock_auth_stub.GetUserDetails = AsyncMock(side_effect=DummyAioRpcError())

        result = await client.get_user_details(user_id)

        mock_auth_stub.GetUserDetails.assert_called_once()
        assert mock_auth_stub.GetUserDetails.call_args[0][0].user_id == 123
        assert result == {}
        mock_logger.info.assert_called_once_with(
            f"Sending GetUserDetails request for user_id: {user_id}"
        )
        mock_logger.error.assert_called_once_with(
            "Error during GetUserDetails call: Simulated error"
        )

    async def test_get_user_permissions_success(
        self, client, mock_logger, mock_auth_stub
    ):
        user_id = 123  # Integer
        mock_response = MagicMock()
        mock_response.permissions = ["perm1", "perm2"]
        mock_auth_stub.GetUserPermissions = AsyncMock(return_value=mock_response)

        result = await client.get_user_permissions(user_id)

        mock_auth_stub.GetUserPermissions.assert_called_once()
        assert mock_auth_stub.GetUserPermissions.call_args[0][0].user_id == 123
        assert result == ["perm1", "perm2"]
        mock_logger.info.assert_any_call(
            f"Sending GetUserPermissions request for user_id: {user_id}"
        )
        mock_logger.info.assert_any_call(
            f"Received permissions for user_id: {user_id}: ['perm1', 'perm2']"
        )

    async def test_get_user_permissions_failure(
        self, client, mock_logger, mock_auth_stub
    ):
        user_id = 123  # Integer
        mock_auth_stub.GetUserPermissions = AsyncMock(side_effect=DummyAioRpcError())

        result = await client.get_user_permissions(user_id)

        mock_auth_stub.GetUserPermissions.assert_called_once()
        assert mock_auth_stub.GetUserPermissions.call_args[0][0].user_id == 123
        assert result == []
        mock_logger.info.assert_called_once_with(
            f"Sending GetUserPermissions request for user_id: {user_id}"
        )
        mock_logger.error.assert_called_once_with(
            "Error during GetUserPermissions call: Simulated error"
        )

    async def test_get_user_roles_success(self, client, mock_logger, mock_auth_stub):
        user_id = 123  # Integer
        mock_response = MagicMock()
        mock_response.hierarchy = 2
        mock_response.role = ["role1", "role2"]
        mock_auth_stub.GetUserRole = AsyncMock(return_value=mock_response)

        result = await client.get_user_roles(user_id)

        mock_auth_stub.GetUserRole.assert_called_once()
        assert mock_auth_stub.GetUserRole.call_args[0][0].user_id == 123
        assert result == {
            "hierarchy": 2,
            "roles": ["role1", "role2"],
        }
        mock_logger.info.assert_any_call(
            f"Sending GetUserRoles request for user_id: {user_id}"
        )
        mock_logger.info.assert_any_call(
            f"Received roles for user_id: {user_id}: ['role1', 'role2']"
        )

    async def test_get_user_roles_failure(self, client, mock_logger, mock_auth_stub):
        user_id = 123  # Integer
        mock_auth_stub.GetUserRole = AsyncMock(side_effect=DummyAioRpcError())

        result = await client.get_user_roles(user_id)

        mock_auth_stub.GetUserRole.assert_called_once()
        assert mock_auth_stub.GetUserRole.call_args[0][0].user_id == 123
        assert result == {}
        mock_logger.info.assert_called_once_with(
            f"Sending GetUserRoles request for user_id: {user_id}"
        )
        mock_logger.error.assert_called_once_with(
            "Error during GetUserRoles call: Simulated error"
        )

    async def test_get_service_board_users_details_success(
        self, client, mock_logger, mock_auth_stub
    ):
        user_ids = [1, 2]  # Integer list
        mock_user = MagicMock()
        mock_user.user_id = 1  # Integer
        mock_user.name = "User One"
        mock_user.is_active = True
        mock_user.is_suspended = False
        mock_user.role = "admin"
        mock_user.role_hierarchy = 1
        mock_user.email = "user1@example.com"
        mock_response = MagicMock()
        mock_response.user_detail = [mock_user]
        mock_auth_stub.GetServiceBoardUsersDetails = AsyncMock(
            return_value=mock_response
        )

        result = await client.get_service_board_users_details(user_ids)

        mock_auth_stub.GetServiceBoardUsersDetails.assert_called_once()
        assert mock_auth_stub.GetServiceBoardUsersDetails.call_args[0][0].user_ids == [
            1,
            2,
        ]
        assert result == {
            1: {
                "user_id": 1,
                "name": "User One",
                "is_active": True,
                "is_suspended": False,
                "role": "admin",
                "role_hierarchy": 1,
                "email": "user1@example.com",
            }
        }
        mock_logger.info.assert_any_call(
            f"Sending GetUserChildHierarchy request for user_id: {user_ids}"
        )

    async def test_get_service_board_users_details_failure(
        self, client, mock_logger, mock_auth_stub
    ):
        user_ids = [1, 2]  # Integer list
        mock_auth_stub.GetServiceBoardUsersDetails = AsyncMock(
            side_effect=DummyAioRpcError()
        )

        result = await client.get_service_board_users_details(user_ids)

        mock_auth_stub.GetServiceBoardUsersDetails.assert_called_once()
        assert mock_auth_stub.GetServiceBoardUsersDetails.call_args[0][0].user_ids == [
            1,
            2,
        ]
        assert result == {}
        mock_logger.info.assert_called_once_with(
            f"Sending GetUserChildHierarchy request for user_id: {user_ids}"
        )
        mock_logger.error.assert_called_once_with(
            "Error during GetUserChildHierarchy call: Simulated error"
        )

    async def test_validate_token_inactive(self, client, mock_logger, mock_auth_stub):
        token = "test-token"
        correlation_id = "test-corr-id"
        mock_response = MagicMock()
        mock_response.is_active = False
        mock_response.session_id = "session-123"
        mock_response.user_id = 123
        mock_response.partner_id = "partner-123"
        mock_auth_stub.ValidateToken = AsyncMock(return_value=mock_response)

        result = await client.validate_token(token, correlation_id)

        mock_auth_stub.ValidateToken.assert_called_once()
        assert (
            mock_auth_stub.ValidateToken.call_args[0][0].mcontext.correlation_id
            == correlation_id
        )
        assert mock_auth_stub.ValidateToken.call_args[0][0].mbody.token == token
        assert result is None
        mock_logger.info.assert_any_call(
            f"Sending ValidateToken request for token: {token} correlation_id: {correlation_id}"
        )
        mock_logger.info.assert_any_call("Received response for user: False")
