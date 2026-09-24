from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import Request
from starlette_context import plugins
from starlette_context.middleware import RawContextMiddleware as BaseContextMiddleware

# Default None: the previous import-time uuid default gave every unset context
# the SAME id. Middleware sets a fresh id per request (see set_context).
context_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


@dataclass
class TalkoRequestAuthContext:
    header_name: str
    header_value: str


_request_auth: ContextVar[TalkoRequestAuthContext | None] = ContextVar("request_auth", default=None)


def set_request_auth(header_name: str, header_value: str) -> None:
    _request_auth.set(TalkoRequestAuthContext(header_name=header_name, header_value=header_value))


def get_request_auth() -> TalkoRequestAuthContext | None:
    return _request_auth.get()


class TalkoContextMiddleware(BaseContextMiddleware):
    def __init__(self, app, propagate_request_id=True) -> None:
        super().__init__(app, plugins=(plugins.request_id.RequestIdPlugin(),))
        self.propagate_request_id = propagate_request_id

    async def set_context(self, request: Request) -> dict:
        context_request = await super().set_context(request)
        request_id = context_request[plugins.request_id.RequestIdPlugin.key]
        context_request_id_var.set(request_id)
        if self.propagate_request_id:
            request.state.request_id = request_id
        return context_request
