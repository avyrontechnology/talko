from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware

# from .auth import JWTMiddleware
from src.middlewares.context import ContextMiddleware

from .allowed_host import AllowedHostsMiddleware
from .authentication import AuthMiddleware
from .logging_request_and_response import RequestResponseLoggingMiddleware

# All these values will come from env file
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8003",
    "https://int-maglo-ui.makunaiglobal.ai",
    "https://qa-maglo-ui.makunaiglobal.ai",
    "https://maglo.makunaiglobal.ai",
    "https://maglo-preprod.makunaiglobal.ai",
    "https://maglo.makunaiglobal.ai",
    "https://holler-preprod-service.makunaiglobal.ai",
    "https://holler-service.makunaiglobal.ai",
    "https://ai.makunaiglobal.ai",
    "https://int-makun-ai-ui.makunaiglobal.ai",
    "http://maglo-service.console-preprod:8000",
    "http://holler-service.console-preprod:8003",
    "http://maglo-service.console-prod:8000",
    "http://holler-service.console-prod:8003",
    "https://agentglo.makunaiglobal.ai",
]

allow_methods = ["*"]
allow_headers = ["*"]
allow_hosts = [
    "localhost:8003",
    "int-holler-service.makunaiglobal.ai",
    "qa-holler-service.makunaiglobal.ai",
    "holler-preprod-service.makunaiglobal.ai",
    "holler-service.makunaiglobal.ai",
    "ai.makunaiglobal.ai",
    "int-makun-ai-ui.makunaiglobal.ai",
    "maglo-service.console-prod:8000",
    "holler-service.console-preprod:8003",
    "holler-service.console-prod:8003",
    "maglo-service.console-prod:8000",
    "agentglo.makunaiglobal.ai",
]

allowed_middlewares = [
    Middleware(ContextMiddleware),
    Middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_headers=allow_headers,
        allow_methods=allow_methods,
    ),
    Middleware(AllowedHostsMiddleware, allowed_hosts=allow_hosts),
    Middleware(RequestResponseLoggingMiddleware),
    Middleware(AuthMiddleware),
]
