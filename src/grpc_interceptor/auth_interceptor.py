import grpc
from grpc import StatusCode
from grpc.aio import UnaryUnaryClientInterceptor, AioRpcError
from src.components.common.responses import TalkoUnauthorizedResponse


class TalkoApiKeyClientInterceptor(UnaryUnaryClientInterceptor):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def intercept_unary_unary(self, continuation, call_details, request):
        metadata = list(call_details.metadata or [])
        metadata.append(("x-api-key", self.api_key))

        # Use a plain object with required attributes
        class _ClientCallDetails:
            def __init__(self):
                self.method = call_details.method
                self.timeout = call_details.timeout
                self.metadata = metadata
                self.credentials = getattr(call_details, "credentials", None)
                self.wait_for_ready = getattr(call_details, "wait_for_ready", None)
                self.compression = getattr(call_details, "compression", None)

        new_call_details = _ClientCallDetails()
        return await continuation(new_call_details, request)