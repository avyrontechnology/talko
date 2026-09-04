import uuid
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import Request
from starlette_context import plugins
from starlette_context.middleware import RawContextMiddleware as BaseContextMiddleware

context_request_id_var = ContextVar("request_id", default=str(uuid.uuid4().hex).lower())


@dataclass
class RequestAuthContext:
    header_name: str
    header_value: str


_request_auth: ContextVar[RequestAuthContext | None] = ContextVar(
    "request_auth", default=None
)


def set_request_auth(header_name: str, header_value: str) -> None:
    _request_auth.set(
        RequestAuthContext(header_name=header_name, header_value=header_value)
    )


def get_request_auth() -> RequestAuthContext | None:
    return _request_auth.get()


class ContextMiddleware(BaseContextMiddleware):
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
