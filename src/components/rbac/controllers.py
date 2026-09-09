from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request

from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoInternalServerErrorResponse,
    TalkoSuccessResponse,
)
from src.components.rbac.superadmin import is_superadmin
from src.core.container import TalkoContainer
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoAuthContextController:
    """Who-am-I for consoles: auth type, scope, and superadmin flag.

    Deliberately outside @permission_check — every authenticated caller may
    ask for their own context; the middleware already enforced auth.
    """

    rbac_router = APIRouter()

    @rbac_router.get("/auth/context")
    @inject
    async def get_auth_context(
        request: Request,
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        try:
            user: dict = getattr(request.state, "user", None) or {}
            grpc_client = TalkoRPCServiceFactory.get_service(TalkoGrpcServices.AUTH)
            superadmin = await is_superadmin(request, grpc_client, talko_service_logger)
            return TalkoSuccessResponse(
                data={
                    "user_id": user.get(TalkoCurrentUserMap.USER_ID),
                    "partner_id": user.get(TalkoCurrentUserMap.PARTNER_ID),
                    "auth_type": "api_key"
                    if user.get("is_api_key_auth")
                    else "jwt",
                    "is_superadmin": superadmin,
                }
            )
        except Exception as exc:
            talko_service_logger.error(
                "Unexpected error building auth context: {}".format(exc)
            )
            return TalkoInternalServerErrorResponse()
