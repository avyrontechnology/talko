from typing import Any, Dict, List, Union

import grpc
from grpc.aio import AioRpcError

from src.components.common.responses import InternalServerErrorResponse
from src.grpc_client.grpc_client import GRPCClient
from src.loggers.holler_service_logger import HollerServiceLogger
from src.pub import auth_pb2, auth_pb2_grpc

logger = HollerServiceLogger.get_logger()


class AuthServiceClient(GRPCClient):

    def __init__(self):
        super().__init__()
        self.stub = auth_pb2_grpc.AuthServiceStub(self.channel)

    @GRPCClient.call_with_retry
    async def validate_token(self, token, correlation_id="12345"):
        logger.info(
            "Sending ValidateToken request for token: {} correlation_id: {}".format(
                token, correlation_id
            )
        )

        # Create the nested request with MContext and MBody
        mcontext = auth_pb2.MContext(correlation_id=correlation_id)
        mbody = auth_pb2.MBody(token=token)
        request = auth_pb2.ValidateTokenRequest(mcontext=mcontext, mbody=mbody)
        try:
            response = await self.stub.ValidateToken(request)
            logger.info("Received response for user: {}".format(response.is_active))
            if not response.is_active:
                return None
            return {
                "is_active": response.is_active,
                "user_session_id": response.session_id,
                "user_id": response.user_id,
                "partner_id": response.partner_id,
            }
        except AioRpcError as exc:
            logger.error("gRPC error during ValidateToken: {}".format(exc))
            if exc.code() == grpc.StatusCode.UNAVAILABLE:
                return InternalServerErrorResponse(
                    detail="Authentication service unavailable"
                )
            raise

    @GRPCClient.call_with_retry
    async def get_user_child_hierarchy(
        self, user_ids: Union[int, List[int]]
    ) -> Dict[int, Dict[str, Any]]:
        """Fetches child user hierarchies for one or multiple user IDs."""
        user_ids_list = [user_ids] if isinstance(user_ids, int) else user_ids
        # mcontext = auth_pb2.MContext(correlation_id=correlation_id)
        logger.info(
            f"Sending GetUserChildHierarchy request for user_ids: {user_ids_list}"
        )

        request = auth_pb2.GetUserChildHierarchyRequest(user_ids=user_ids_list)

        try:
            response = await self.stub.GetUserChildHierarchy(request)
            logger.info(f"Received child hierarchies for user_ids: {user_ids_list}")

            child_hierarchy_dict = {
                hierarchy.user_id: {
                    "user_id": hierarchy.user_id,
                    "child_ids": list(hierarchy.child_ids),
                }
                for hierarchy in response.child_hierarchy
            }
            return child_hierarchy_dict
        except AioRpcError as exc:
            logger.error(f"Error during GetUserChildHierarchy call: {exc}")
            return {}

    @GRPCClient.call_with_retry
    async def get_user_child_details(self, user_id):
        logger.info(
            "Sending GetUserChildHierarchy request for user_id: {}".format(user_id)
        )

        # Create the request with MContext and user_id
        # mcontext = auth_pb2.MContext(correlation_id=correlation_id)
        request = auth_pb2.GetUserChildDetailsRequest(user_id=user_id)

        try:
            response = await self.stub.GetUserChildDetails(request)
            logger.info(
                "Received child user list for user_id: {}: {}".format(
                    user_id, response.user_detail
                )
            )

            child_user_dict = {
                user.user_id: {
                    "user_id": user.user_id,
                    "name": user.name,
                    "is_active": user.is_active,
                    "is_suspended": user.is_suspended,
                }
                for user in response.user_detail
            }
            return child_user_dict
        except AioRpcError as exc:
            logger.error("Error during GetUserChildHierarchy call: {}".format(exc))
            return {}

    @GRPCClient.call_with_retry
    async def get_user_details(self, user_id):
        logger.info("Sending GetUserDetails request for user_id: {}".format(user_id))

        # Create the request with MContext and user_id
        # mcontext = auth_pb2.MContext(correlation_id=correlation_id)
        request = auth_pb2.GetUserDetailsRequest(user_id=user_id)

        try:
            response = await self.stub.GetUserDetails(request)
            logger.info(
                "Received user details for user_id: {}: {}".format(
                    user_id, response.user_profile
                )
            )
            user = response.user_profile
            user_details = {
                "user_id": user.user_id,
                "name": user.name,
                "email": user.email,
                "partner_id": user.partner_id,
                "role_hierarchy_level": user.role_hierarchy_level,
            }
            return user_details
        except AioRpcError as exc:
            logger.error("Error during GetUserDetails call: {}".format(exc))
            return {}

    @GRPCClient.call_with_retry
    async def get_user_permissions(self, user_id):
        logger.info(
            "Sending GetUserPermissions request for user_id: {}".format(user_id)
        )

        # Create the request with MContext and user_id
        request = auth_pb2.GetUserPermissionsRequest(user_id=user_id)

        try:
            response = await self.stub.GetUserPermissions(request)
            logger.info(
                "Received permissions for user_id: {}: {}".format(
                    user_id, response.permissions
                )
            )
            return list(response.permissions)
        except AioRpcError as exc:
            logger.error("Error during GetUserPermissions call: {}".format(exc))
            return []

    @GRPCClient.call_with_retry
    async def get_user_roles(self, user_id):
        logger.info("Sending GetUserRoles request for user_id: {}".format(user_id))

        # Create the request with MContext and user_id
        request = auth_pb2.GetUserRoleRequest(user_id=user_id)

        try:
            response = await self.stub.GetUserRole(request)
            logger.info(
                "Received roles for user_id: {}: {}".format(user_id, response.role)
            )
            return {
                "hierarchy": response.hierarchy,
                "roles": response.role,
            }
        except AioRpcError as exc:
            logger.error("Error during GetUserRoles call: {}".format(exc))
            return {}

    @GRPCClient.call_with_retry
    async def get_service_board_users_details(self, user_ids):
        user_ids: list = (
            [user_ids]
            if isinstance(user_ids, int)
            else [uid for uid in user_ids if isinstance(uid, int)]
        )

        logger.info(f"Sending GetUserChildHierarchy request for user_id: {user_ids}")

        request = auth_pb2.GetUsersDetailsRequest(user_ids=user_ids)

        try:
            response = await self.stub.GetServiceBoardUsersDetails(request)
            logger.info(
                f"Received child user list for user_id: {user_ids}: {response.user_detail}"
            )

            child_user_dict = {
                user.user_id: {
                    "user_id": user.user_id,
                    "name": user.name,
                    "is_active": user.is_active,
                    "is_suspended": user.is_suspended,
                    "role": getattr(user, "role", None),
                    "role_hierarchy": getattr(user, "role_hierarchy", None),
                    "email": user.email,
                }
                for user in response.user_detail
            }
            return child_user_dict
        except AioRpcError as exc:
            logger.error(f"Error during GetUserChildHierarchy call: {exc}")
            return {}

    @GRPCClient.call_with_retry
    async def get_partner_api_key(self, partner_id):
        logger.info(f"Getting API Key for Partner ID: {partner_id}")

        request = auth_pb2.GetPartnerApiKeyRequest(partner_id=partner_id)

        try:
            response = await self.stub.GetPartnerApiKey(request)
            logger.debug(f"Got the response for Partner API Key: {request}")

            if response.api_key == "None":
                return None
            return response.api_key
        except AioRpcError as exc:
            logger.error(f"Error during GetPartnerApiKey call: {exc}")
            return None
