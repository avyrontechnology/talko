from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware

import os

# from .auth import JWTMiddleware
from src.middlewares.context import TalkoContextMiddleware

from .allowed_host import TalkoAllowedHostsMiddleware
from .authentication import TalkoAuthMiddleware
from .logging_request_and_response import TalkoRequestResponseLoggingMiddleware

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
    "https://talko-preprod-service.makunaiglobal.ai",
    "https://talko-service.makunaiglobal.ai",
    "https://ai.makunaiglobal.ai",
    "https://int-makun-ai-ui.makunaiglobal.ai",
    "http://maglo-service.console-preprod:8000",
    "http://talko-service.console-preprod:8003",
    "http://maglo-service.console-prod:8000",
    "http://talko-service.console-prod:8003",
    "https://agentglo.makunaiglobal.ai",
]

# Extra browser origins (comma-separated), e.g. a Vercel preview URL for the
# Talko UI: CORS_EXTRA_ORIGINS=https://talko-ui.vercel.app
_extra_origins = os.getenv("CORS_EXTRA_ORIGINS", "")
origins += [o.strip() for o in _extra_origins.split(",") if o.strip()]

allow_methods = ["*"]
allow_headers = ["*"]
allow_hosts = [
    "localhost:8003",
    "int-talko-service.makunaiglobal.ai",
    "qa-talko-service.makunaiglobal.ai",
    "talko-preprod-service.makunaiglobal.ai",
    "talko-service.makunaiglobal.ai",
    "ai.makunaiglobal.ai",
    "int-makun-ai-ui.makunaiglobal.ai",
    "maglo-service.console-prod:8000",
    "talko-service.console-preprod:8003",
    "talko-service.console-prod:8003",
    "maglo-service.console-prod:8000",
    "agentglo.makunaiglobal.ai",
    "talko-service.onrender.com",
]

# Extra allowed Host headers (comma-separated), e.g. a Render domain:
# ALLOWED_HOSTS_EXTRA=talko-service.onrender.com
_extra_hosts = os.getenv("ALLOWED_HOSTS_EXTRA", "")
allow_hosts += [h.strip() for h in _extra_hosts.split(",") if h.strip()]

allowed_middlewares = [
    Middleware(TalkoContextMiddleware),
    Middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_headers=allow_headers,
        allow_methods=allow_methods,
    ),
    Middleware(TalkoAllowedHostsMiddleware, allowed_hosts=allow_hosts),
    Middleware(TalkoRequestResponseLoggingMiddleware),
    Middleware(TalkoAuthMiddleware),
]
