from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Depends, Request
from dependency_injector.wiring import Provide, inject
from src.core.container import Container
from src.components.common.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
)

# from src.loggers.maglo_logger import MagloServiceLogger


class AllowedHostsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_hosts: list[str]):
        super().__init__(app)
        self.allowed_hosts = allowed_hosts
        self.excluded_paths = {
            "/holler-service/v1/health",
        }

    @inject
    async def dispatch(
        self,
        request,
        call_next,
        # logger: BabblerServiceLogger = Depends(
        #     Provide[Container.logger]
        # ),
    ):

        try:
            # logger.debug("Verfying Allowed Hosts at Middleware...")
            if request.url.path in self.excluded_paths:
                return await call_next(request)
            host = request.headers.get("host")
            if host not in self.allowed_hosts:
                # maglo_service_logger.error(f"Host not Allowed Host: {host}")
                return ForbiddenResponse(detail="Host Not Allowed")
            return await call_next(request)
        except Exception as exc:
            # maglo_service_logger.error(f"Got an unexpected Error: {exc}")
            return InternalServerErrorResponse()
