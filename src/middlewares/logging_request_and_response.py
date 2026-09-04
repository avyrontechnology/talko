import json
import time
from src.components.common.responses import TalkoInternalServerErrorResponse
from src.core.container import TalkoContainer
from src.loggers.talko_service_logger import TalkoServiceLogger
from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse


class TalkoRequestResponseLoggingMiddleware(BaseHTTPMiddleware):
    @inject
    async def dispatch(
        self,
        request: Request,
        call_next,
        logger: TalkoServiceLogger = Provide[TalkoContainer.logger],
    ):
        excluded_paths = ("/docs", "/openapi.json", "/robots.txt")

        temp_excluded_paths = (
            "/talko-service/v1/upload_digital_asset",
            "/talko-service/v1/update_constant",
            "/talko-service/v1/reports/daily-lead-connection-csv",
            "/reports/daily-lead-connection-csv",
        )

        # Check if the current request path is in the excluded paths
        if any(
            request.url.path.startswith(path)
            for path in excluded_paths + temp_excluded_paths
        ):
            return await call_next(request)
        # Log request details
        start_time: time = time.time()
        request_body: Request = await request.body()
        logger.info(
            json.dumps(
                {
                    "request_method": request.method,
                    "request_url": str(request.url),
                    "request_headers": dict(request.headers),
                    "request_body": (
                        json.loads(request_body.decode("utf-8"))
                        if request_body
                        else "No body"
                    ),
                }
            )
        )

        try:
            # Call the next middleware or endpoint
            response: Response = await call_next(request)
            # Handle 204 No Content response

            if response.status_code == 204:
                logger.info("Response is 204 No Content, no body to log.")
                return Response(status_code=204)  # Return an empty response

            # Read and log the response body for other status codes
            response_body = [section async for section in response.body_iterator]
            response_body_str = b"".join(response_body).decode("utf-8")

            # Log response details
            response_time: time = time.time() - start_time
            logger.info(
                json.dumps(
                    {
                        "response_status_code": response.status_code,
                        "response_body": (
                            json.loads(response_body_str)
                            if response_body_str
                            else "No body"
                        ),
                        "response_time": "{: .4f} seconds".format(response_time),
                    }
                )
            )

            # Create a new StreamingResponse with the same content
            async def response_stream():
                yield response_body_str.encode("utf-8")

            return StreamingResponse(
                response_stream(),
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        except Exception as exec:
            logger.error(
                "Error processing request in the logging request and response middleware: {}".format(
                    exec
                )
            )
            return TalkoInternalServerErrorResponse()
