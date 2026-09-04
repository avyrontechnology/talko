import asyncio
from datetime import datetime, timezone

import psutil
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from src.components.health import messages as health_messages
from src.core.container import TalkoContainer
from src.core.environment import TalkoENV
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoHealthController:
    """Controller to handle health check API endpoints."""

    router = APIRouter()

    @router.get(
        "",
        summary="Health Check",
    )
    @inject
    async def health_check(
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            talko_service_logger.info("Received health check request")

            memory, disk = await asyncio.gather(
                TalkoHealthController._check_memory(),
                TalkoHealthController._check_disk(),
            )

            checks = {
                "memory": memory,
                "disk": disk,
            }

            statuses = [c["status"] for c in checks.values()]

            if any(s in ("unreachable", "error") for s in statuses):
                overall, http_status = "unhealthy", status.HTTP_503_SERVICE_UNAVAILABLE
            elif any(s in ("warning", "starting") for s in statuses):
                overall, http_status = "degraded", status.HTTP_200_OK
            else:
                overall, http_status = "healthy", status.HTTP_200_OK

            talko_service_logger.info(
                "Health check completed with status: {}".format(overall)
            )

            return JSONResponse(
                status_code=http_status,
                content={
                    "status": overall,
                    "service": TalkoENV.SERVICE_NAME,
                    "environment": TalkoENV.ENVIRONMENT,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "checks": checks,
                },
            )

        except Exception as e:
            talko_service_logger.error(
                "Unexpected error occurred during health check: {}".format(str(e))
            )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "unhealthy",
                    "service": TalkoENV.SERVICE_NAME,
                    "environment": TalkoENV.ENVIRONMENT,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": health_messages.EXCEPTION_ERROR,
                },
            )

    # Private Helpers

    @staticmethod
    async def _check_memory() -> dict:
        try:
            memory = psutil.virtual_memory()
            return {
                "status": "ok" if memory.percent < 90 else "warning",
                "used_percent": memory.percent,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    async def _check_disk() -> dict:
        try:
            disk = psutil.disk_usage("/")
            return {
                "status": "ok" if disk.percent < 90 else "warning",
                "used_percent": disk.percent,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
