from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status

from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoForbiddenPermissionResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceCreatedResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.partner_auth.dto import TalkoContract
from src.components.partner_auth.message import SOMETHING_WENT_WRONG
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.rbac.superadmin import (
    TalkoSuperadminDenied,
    is_superadmin,
    resolve_effective_partner_id,
)
from src.core.container import TalkoContainer
from src.exceptions import TalkoResourceNotFound
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger

from .services import TalkoPartnerApiKeyService


class TalkoPartnerApiKeyController:
    """Admin-only endpoints for issuing/listing/revoking partner API keys.
    Protected by the existing JWT+RBAC stack — no partner self-serve.
    """

    router = APIRouter()

    @router.post(
        "",
        response_model=TalkoContract.ApiKeyCreateResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def create_api_key(
        request: Request,
        data: TalkoContract.ApiKeyCreate,
        partner_api_key_service: TalkoPartnerApiKeyService = Depends(Provide[TalkoContainer.partner_api_key_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            current_user_data: dict = request.state.user
            user_id = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            talko_service_logger.info(
                f"User: {user_id}, create partner api key api initiated for partner_id: {data.partner_id}"
            )
            # Keys are issued into the body partner: superadmins may onboard
            # any partner, everyone else only their own scope.
            grpc_client = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.AUTH)
            try:
                await resolve_effective_partner_id(request, grpc_client, talko_service_logger, data.partner_id)
            except TalkoSuperadminDenied as denied:
                return TalkoForbiddenPermissionResponse(detail=str(denied))
            created = await partner_api_key_service.create_api_key(data, user_id)
            return TalkoResourceCreatedResponse(data=created)
        except Exception as e:
            talko_service_logger.error(f"Unexpected error creating partner api key: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.get("", response_model=list[TalkoContract.ApiKeyListItem])
    @permission_check(TalkoPermissionDependency)
    @inject
    async def list_api_keys(
        request: Request,
        partner_id: int | None = Query(None),
        partner_api_key_service: TalkoPartnerApiKeyService = Depends(Provide[TalkoContainer.partner_api_key_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            current_user_data: dict = request.state.user
            grpc_client = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.AUTH)
            is_admin = await is_superadmin(request, grpc_client, talko_service_logger)
            # Empty partner_id = all keys for superadmin, own keys otherwise.
            if partner_id is None:
                if is_admin:
                    talko_service_logger.info("Listing all partner api keys (superadmin default)")
                    keys = await partner_api_key_service.list_all_api_keys()
                    return TalkoSuccessResponse(data=keys)
                own = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
                if own is None:
                    return TalkoSuccessResponse(data=[])
                partner_id = own
            talko_service_logger.info(f"Listing partner api keys for partner_id: {partner_id}")
            # Segregation: non-superadmins may only list their own partner's keys.
            if not is_admin:
                own = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
                if own is not None:
                    partner_id = own
            keys = await partner_api_key_service.list_api_keys(partner_id)
            return TalkoSuccessResponse(data=keys)
        except Exception as e:
            talko_service_logger.error(f"Unexpected error listing partner api keys: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.post("/{id}/revoke", response_model=TalkoContract.ApiKeyRevokeResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def revoke_api_key(
        request: Request,
        id: str,
        partner_api_key_service: TalkoPartnerApiKeyService = Depends(Provide[TalkoContainer.partner_api_key_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            talko_service_logger.info(f"Revoking partner api key {id}")
            revoked = await partner_api_key_service.revoke_api_key(id)
            return TalkoSuccessResponse(data=revoked)
        except TalkoResourceNotFound:
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except ValueError:
            return TalkoBadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            talko_service_logger.error(f"Unexpected error revoking partner api key {id}: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
