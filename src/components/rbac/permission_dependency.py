import json
from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import HTTPException, Request

# from src.components.common.auth import AuthUtility
from src.components.rbac.constants import PermissionErrorText
from src.core.container import Container
from src.core.redis import RedisCache
from src.grpc_client.constants import GrpcServices
from src.grpc_client.rpc_service_factory import RPCServiceFactory
from src.loggers.holler_service_logger import HollerServiceLogger


class PermissionDependency:
    """
    This dependency dynamically checks the permission based on its own class name.
    """

    def __init__(self, permission_name: str):
        self.permission_name: str = permission_name

    @inject
    async def __call__(
        self,
        request: Request,
        redis_pool: RedisCache = Provide[Container.redis_pool],
        logger: HollerServiceLogger = Provide[Container.logger],
    ):

        logger.debug("checking permission: {}".format(self.permission_name))

        try:
            #  current_user is available in request's state (Extracted from the token)
            current_user_details = request.state.user
            # API-KEY authenticated requests are partner-scoped, not user-scoped.
            # They have no user_id, so the user-permission RBAC check doesn't apply.
            # Bypass it here and let them through.
            if current_user_details.get("is_api_key_auth"):
                logger.info(
                    "API-KEY auth detected for partner_id={}. Bypassing user-permission "
                    "check for permission: {}".format(
                        current_user_details.get("partner_id"), self.permission_name
                    )
                )
                return
            current_user_id = current_user_details.get("user_id")
            grpc_client = RPCServiceFactory.get_service(GrpcServices.AUTH)
            user_permissions = await grpc_client.get_user_permissions(current_user_id)
            logger.info(
                "user-{} have permissions {}".format(current_user_id, user_permissions)
            )

            # Check if the required permission is in the user's permissions list
            if self.permission_name not in user_permissions:
                logger.error(
                    "Permission denied: {} not in user's permissions".format(
                        self.permission_name
                    )
                )
                raise HTTPException(
                    status_code=403, detail=PermissionErrorText.PERMISSION_DENIED
                )

            logger.info(
                "Permission granted for user: {} with permission: {}".format(
                    current_user_id, self.permission_name
                )
            )
        except HTTPException as http_forbidden:
            raise http_forbidden

        except Exception as exc:
            logger.error("Permission check failed: {}".format(str(exc)))
            raise HTTPException(
                status_code=404, detail=PermissionErrorText.INTERNAL_SERVER_ERROR
            )
