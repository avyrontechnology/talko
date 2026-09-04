import json

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Request
from redis import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from src.components.common.constants import TalkoCurrentUserMap, TalkoErrorPrompt
from src.components.common.responses import (
    TalkoInternalServerErrorResponse,
    TalkoTooManyRequestsResponse,
    TalkoUnauthorizedResponse,
)
from src.components.partner_auth.services import TalkoPartnerApiKeyService
from src.core.container import TalkoContainer
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.middlewares.context import set_request_auth
from src.utils.token_utils import TalkoApiKeyGenerator


async def resolve_user_payload(
    token: str, redis_pool: Redis, logger: TalkoServiceLogger
) -> dict | None:
    """
    Validate a bearer token (cache-first, gRPC fallback) and return the decoded
    user payload, or None if the token is missing/invalid/inactive.

    Shared by TalkoAuthMiddleware (HTTP requests) and any websocket endpoint that needs
    to authenticate its handshake, since Starlette's BaseHTTPMiddleware does not run
    for websocket connections.
    """
    grpc_client = TalkoRPCServiceFactory.get_service(TalkoGrpcServices.AUTH)
    payload = await redis_pool.get(f"token:{token}")

    if payload:
        payload = json.loads(payload)
        logger.debug("Hit the cache for payload: {}".format(payload))
    else:
        logger.debug("Cache missed, validating token via gRPC")
        payload = await grpc_client.validate_token(token=str(token))

    if (not payload) or (not payload.get("is_active")):
        return None

    return payload


# Define Middleware for Authenticating JWT Token
class TalkoAuthMiddleware(BaseHTTPMiddleware):
    @inject
    async def dispatch(
        self,
        request: Request,
        call_next,
        redis_pool: Redis = Depends(Provide[TalkoContainer.redis_pool]),
        logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
        partner_api_key_service: TalkoPartnerApiKeyService = Depends(
            Provide[TalkoContainer.partner_api_key_service]
        ),
    ):
        # List of endpoints to exclude from middleware

        excluded_paths = (
            "/docs",
            "/openapi.json",
            "/robots.txt",
            "/talko-service/v1/call/webhook",
            "/talko-service/v1/call/api/dialplan",
            "/talko-service/v1/reports/daily-lead-connection-csv",
            "/talko-service/v1/health",
            "/talko-service/v1/call/recovery/clicktocall-agent/fix",
            "/talko-service/v1/pstn/tata/stream",
            "/talko-service/v1/ws/inbound-calls/",
            "/talko-service/v1/dids/list-ai-agent-dids",
        )

        # Check if the current request path is in the excluded paths
        logger.debug(
            "Checking if request path is in excluded paths: {}".format(request.url.path)
        )
        if request.url.path in excluded_paths:
            return await call_next(request)

        api_key = request.headers.get("API-KEY")

        if api_key:
            logger.info("API-KEY detected. Starting API Key validation.")
            return await self._handle_api_key(
                request=request,
                api_key=api_key,
                call_next=call_next,
                redis_pool=redis_pool,
                logger=logger,
                partner_api_key_service=partner_api_key_service,
            )

        logger.debug("Extracting Authorization Header...")
        authorization: str = request.headers.get("Authorization")
        try:
            if not authorization:
                logger.error("Token required")
                return TalkoUnauthorizedResponse(detail=TalkoErrorPrompt.TOKEN_REQUIRED)

            if not authorization.startswith("Bearer "):
                logger.error("Missing or invalid Authorization header")
                return TalkoUnauthorizedResponse(
                    detail=TalkoErrorPrompt.UNAUTHORIZED_HEADER
                )
            # Get token from header
            logger.info("Getting token from header at Middleware...")
            token_parts = authorization.split(" ")
            if len(token_parts) != 2:
                logger.error("Invalid Authorization header format")
                return TalkoUnauthorizedResponse(
                    detail=TalkoErrorPrompt.UNAUTHORIZED_HEADER
                )
            token = token_parts[1]

            payload = await resolve_user_payload(token, redis_pool, logger)
            if not payload:
                return TalkoUnauthorizedResponse(detail="Unauthorized User")
            logger.info(
                "Sucessflly Validated through GRPC and get payload: {}".format(payload)
            )

            # extract user_id
            grpc_client = TalkoRPCServiceFactory.get_service(TalkoGrpcServices.AUTH)
            user_id = payload.get(TalkoCurrentUserMap.USER_ID)
            child_ids = await grpc_client.get_user_child_hierarchy(user_id)

            # Add user information to the request state
            request.state.user = payload
            request.state.hierarchy = child_ids
            logger.debug("Added state to request for user {}".format(payload))

        except Exception as exc:
            logger.error("Internal Server Error {}".format(exc))
            return TalkoInternalServerErrorResponse()

        return await call_next(request)

    async def _handle_api_key(
        self,
        request: Request,
        api_key: str,
        call_next,
        redis_pool: Redis,
        logger: TalkoServiceLogger,
        partner_api_key_service: TalkoPartnerApiKeyService,
    ):
        try:
            # Talko-issued partner keys (tkp_live_*) are validated locally —
            # never touch the gRPC/console flow or its api_key:{key} cache
            # namespace below. Old-format keys fall straight through.
            if TalkoApiKeyGenerator.is_partner_key(api_key):
                result = await partner_api_key_service.validate_and_get_partner(
                    api_key
                )
                if result is None:
                    logger.error("Invalid partner API key presented.")
                    return TalkoUnauthorizedResponse(detail="Invalid API Key")

                if not await partner_api_key_service.check_rate_limit(
                    result["partner_id"]
                ):
                    logger.error(
                        "Rate limit exceeded for partner_id: {}".format(
                            result["partner_id"]
                        )
                    )
                    return TalkoTooManyRequestsResponse()

                request.state.user = {
                    "partner_id": result["partner_id"],
                    "api_key_id": result["api_key_id"],
                    "is_api_key_auth": True,
                }
                logger.debug(
                    "Partner API key auth completed. state.user={}".format(
                        request.state.user
                    )
                )
                set_request_auth("API-KEY", api_key)
                return await call_next(request)

            # --- everything below is the existing gRPC-backed flow, unchanged ---

            # Redis cache check — keyed by api_key value
            payload = await redis_pool.get(f"api_key:{api_key}")

            if payload:
                payload = json.loads(payload)
                logger.debug("Cache hit for API key payload: {}".format(payload))
            else:
                logger.debug("Cache missed, validating API key via gRPC")
                grpc_client = TalkoRPCServiceFactory.get_service(TalkoGrpcServices.API_KEY)
                payload = await grpc_client.validate_api_key(api_key=api_key)

                if not payload:
                    logger.error(
                        "API Key validation failed for key: {}".format(api_key)
                    )
                    return TalkoUnauthorizedResponse(detail="Invalid API Key")

                if not payload.get("is_active"):
                    logger.error(
                        "API Key inactive for partner_id: {}".format(
                            payload.get("partner_id")
                        )
                    )
                    return TalkoUnauthorizedResponse(detail="Inactive API Key")

                logger.info(
                    "API Key validated. partner_id={}".format(payload.get("partner_id"))
                )

            # Inject into request.state — same shape downstream code expects
            request.state.user = {
                "partner_id": payload.get("partner_id"),
                "api_key_id": payload.get("id"),
                "is_api_key_auth": True,  # flag so controllers know auth type
            }
            logger.debug(
                "API key auth completed. state.user={}".format(request.state.user)
            )

            set_request_auth("API-KEY", api_key)

        except Exception as exc:
            logger.error("Internal Server Error in _handle_api_key: {}".format(exc))
            return TalkoInternalServerErrorResponse()

        return await call_next(request)
