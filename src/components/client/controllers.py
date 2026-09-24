from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status

from src.components.client.dto import TalkoContract
from src.components.client.message import SOMETHING_WENT_WRONG
from src.components.client.services import TalkoClientService
from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoForbiddenPermissionResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceCreatedResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.rbac.superadmin import (
    TalkoSuperadminDenied,
    is_superadmin,
    resolve_effective_partner_id,
)
from src.core.container import TalkoContainer
from src.exceptions import (
    TalkoBadRequestError,
    TalkoConflictError,
    TalkoResourceNotFound,
)
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoClientController:
    client_router = APIRouter()

    @client_router.post(
        "",
        response_model=TalkoContract.ClientCreateResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def create_client(
        request: Request,
        payload: TalkoContract.ClientCreate,
        client_service: TalkoClientService = Depends(Provide[TalkoContainer.client_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.ClientCreateResponse:
        try:
            # Partner scope: superadmins may onboard any partner,
            # everyone else only their own scope.
            grpc_client = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.AUTH)
            try:
                scoped = await resolve_effective_partner_id(
                    request, grpc_client, talko_service_logger, payload.partner_id
                )
            except TalkoSuperadminDenied as denied:
                return TalkoForbiddenPermissionResponse(detail=str(denied))
            if scoped is not None:
                payload.partner_id = scoped
            created = await client_service.create_client(payload)
            return TalkoResourceCreatedResponse(data=created)
        except TalkoConflictError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoBadRequestError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Error creating client: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @client_router.get("", response_model=list[TalkoContract.ClientResponse])
    @permission_check(TalkoPermissionDependency)
    @inject
    async def list_clients(
        request: Request,
        partner_id: int | None = Query(None),
        active_only: bool = Query(False),
        client_service: TalkoClientService = Depends(Provide[TalkoContainer.client_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> list[TalkoContract.ClientResponse]:
        try:
            # Empty partner_id = all clients for superadmin, own clients otherwise.
            grpc_client = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.AUTH)
            is_admin = await is_superadmin(request, grpc_client, talko_service_logger)
            if partner_id is None:
                if is_admin:
                    return TalkoSuccessResponse(data=await client_service.list_all_clients(active_only))
                own = request.state.user.get(TalkoCurrentUserMap.PARTNER_ID)
                if own is None:
                    return TalkoSuccessResponse(data=[])
                partner_id = own
            if not is_admin:
                own = request.state.user.get(TalkoCurrentUserMap.PARTNER_ID)
                if own is not None:
                    partner_id = own
            clients = await client_service.list_clients(partner_id, active_only)
            return TalkoSuccessResponse(data=clients)
        except Exception as e:
            talko_service_logger.error(f"Error listing clients: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @client_router.get("/{id}", response_model=TalkoContract.ClientResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_client(
        request: Request,
        id: str,
        client_service: TalkoClientService = Depends(Provide[TalkoContainer.client_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.ClientResponse:
        try:
            client = await client_service.get_client(id)
            return TalkoSuccessResponse(data=client)
        except TalkoResourceNotFound:
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            talko_service_logger.error(f"Error fetching client: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @client_router.patch("/{id}", response_model=TalkoContract.ClientCreateResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def update_client(
        request: Request,
        id: str,
        payload: TalkoContract.ClientUpdate,
        client_service: TalkoClientService = Depends(Provide[TalkoContainer.client_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.ClientCreateResponse:
        try:
            updated = await client_service.update_client(id, payload)
            return TalkoSuccessResponse(data=updated)
        except TalkoResourceNotFound:
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except TalkoBadRequestError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Error updating client: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @client_router.patch("/{id}/activate")
    @permission_check(TalkoPermissionDependency)
    @inject
    async def activate_client(
        request: Request,
        id: str,
        client_service: TalkoClientService = Depends(Provide[TalkoContainer.client_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            result = await client_service.set_active(id, True)
            return TalkoSuccessResponse(data=result)
        except TalkoResourceNotFound:
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            talko_service_logger.error(f"Error activating client: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @client_router.patch("/{id}/deactivate")
    @permission_check(TalkoPermissionDependency)
    @inject
    async def deactivate_client(
        request: Request,
        id: str,
        client_service: TalkoClientService = Depends(Provide[TalkoContainer.client_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            result = await client_service.set_active(id, False)
            return TalkoSuccessResponse(data=result)
        except TalkoResourceNotFound:
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            talko_service_logger.error(f"Error deactivating client: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
