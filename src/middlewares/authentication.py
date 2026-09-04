import json

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Request
from redis import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from src.components.common.constants import TalkoCurrentUserMap, TalkoErrorPrompt
from src.components.common.responses import (
    TalkoInternalServerErrorResponse,
    TalkoUnauthorizedResponse,
)
from src.core.container import TalkoContainer
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.middlewares.context import set_request_auth


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
    ):
        try:
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
