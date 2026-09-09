from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, status

from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoForbiddenPermissionResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceCreatedResponse,
    TalkoSuccessResponse,
    TalkoUnauthorizedResponse,
)
from src.components.rbac.superadmin import is_superadmin
from src.components.user_auth.dto import TalkoContract
from src.components.user_auth.services import (
    TalkoInactiveUserError,
    TalkoInvalidCredentialsError,
    TalkoUserAuthService,
    TalkoUserExistsError,
)
from src.core.container import TalkoContainer
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoUserAuthController:
    """Talko-native accounts: public signup/login, superadmin user mgmt."""

    router = APIRouter()

    @router.post(
        "/auth/signup",
        response_model=TalkoContract.UserResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @inject
    async def signup(
        payload: TalkoContract.Signup,
        user_auth_service: TalkoUserAuthService = Depends(
            Provide[TalkoContainer.user_auth_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        try:
            user = await user_auth_service.signup(payload)
            return TalkoResourceCreatedResponse(data=user)
        except TalkoUserExistsError as exc:
            talko_service_logger.warning("Talko signup conflict: {}".format(exc))
            return TalkoBadRequestResponse(detail=str(exc))
        except ValueError as exc:
            return TalkoBadRequestResponse(detail=str(exc))
        except Exception as exc:
            talko_service_logger.error("Unexpected error on talko signup: {}".format(exc))
            return TalkoInternalServerErrorResponse()

    @router.post("/auth/login", response_model=TalkoContract.TokenResponse)
    @inject
    async def login(
        payload: TalkoContract.Login,
        user_auth_service: TalkoUserAuthService = Depends(
            Provide[TalkoContainer.user_auth_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        try:
            token = await user_auth_service.login(payload)
            return TalkoSuccessResponse(data=token)
        except TalkoInvalidCredentialsError as exc:
            return TalkoUnauthorizedResponse(detail=str(exc))
        except TalkoInactiveUserError as exc:
            return TalkoForbiddenPermissionResponse(detail=str(exc))
        except Exception as exc:
            talko_service_logger.error("Unexpected error on talko login: {}".format(exc))
            return TalkoInternalServerErrorResponse()

    @router.post(
        "/auth/users",
        response_model=TalkoContract.UserResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @inject
    async def create_user(
        payload: TalkoContract.AdminCreateUser,
        request: Request,
        user_auth_service: TalkoUserAuthService = Depends(
            Provide[TalkoContainer.user_auth_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        """Superadmin-provisioned account (credentials handed over offline)."""
        try:
            grpc_client = TalkoRPCServiceFactory.get_service(TalkoGrpcServices.AUTH)
            if not await is_superadmin(request, grpc_client, talko_service_logger):
                return TalkoForbiddenPermissionResponse(
                    detail="User provisioning requires superadmin"
                )
            user = await user_auth_service.create_user(payload)
            return TalkoResourceCreatedResponse(data=user)
        except TalkoUserExistsError as exc:
            return TalkoBadRequestResponse(detail=str(exc))
        except ValueError as exc:
            return TalkoBadRequestResponse(detail=str(exc))
        except Exception as exc:
            talko_service_logger.error("Unexpected error provisioning user: {}".format(exc))
            return TalkoInternalServerErrorResponse()

    @router.get("/auth/users")
    @inject
    async def list_users(
        request: Request,
        user_auth_service: TalkoUserAuthService = Depends(
            Provide[TalkoContainer.user_auth_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        try:
            grpc_client = TalkoRPCServiceFactory.get_service(TalkoGrpcServices.AUTH)
            if not await is_superadmin(request, grpc_client, talko_service_logger):
                return TalkoForbiddenPermissionResponse(
                    detail="User management requires superadmin"
                )
            return TalkoSuccessResponse(data=await user_auth_service.list_users())
        except Exception as exc:
            talko_service_logger.error("Unexpected error listing users: {}".format(exc))
            return TalkoInternalServerErrorResponse()

    @router.patch("/auth/users/{user_id}")
    @inject
    async def update_user(
        user_id: str,
        payload: TalkoContract.UpdateUser,
        request: Request,
        user_auth_service: TalkoUserAuthService = Depends(
            Provide[TalkoContainer.user_auth_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        try:
            grpc_client = TalkoRPCServiceFactory.get_service(TalkoGrpcServices.AUTH)
            if not await is_superadmin(request, grpc_client, talko_service_logger):
                return TalkoForbiddenPermissionResponse(
                    detail="User management requires superadmin"
                )
            updated = await user_auth_service.update_user(user_id, payload)
            if updated is None:
                return TalkoBadRequestResponse(detail="User not found")
            return TalkoSuccessResponse(data=updated)
        except ValueError as exc:
            return TalkoBadRequestResponse(detail=str(exc))
        except Exception as exc:
            talko_service_logger.error("Unexpected error updating user: {}".format(exc))
            return TalkoInternalServerErrorResponse()
