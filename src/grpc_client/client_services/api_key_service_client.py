from grpc.aio import AioRpcError

from src.grpc_client.grpc_client import TalkoGRPCClient
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.pub import api_key_service_pb2, api_key_service_pb2_grpc

logger = TalkoServiceLogger.get_logger()


class TalkoApiKeyServiceClient(TalkoGRPCClient):

    def __init__(self):
        super().__init__()
        self.stub = api_key_service_pb2_grpc.ApiKeyServiceStub(self.channel)

    @TalkoGRPCClient.call_with_retry
    async def validate_api_key(self, api_key: str):
        logger.info("Sending ValidateApiKey request")
        request = api_key_service_pb2.ValidateApiKeyRequest(key=api_key)
        try:
            response = await self.stub.ValidateApiKey(request)
            logger.info(
                "ValidateApiKey response: is_active={}".format(response.is_active)
            )
            if not response.is_active:
                return None
            return {
                "id": response.id,
                "key": response.key,
                "partner_id": response.partner_id,
                "is_active": response.is_active,
            }
        except AioRpcError as exc:
            logger.error("gRPC error during ValidateApiKey: {}".format(exc))
            raise
