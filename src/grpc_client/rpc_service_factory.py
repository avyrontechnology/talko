import os

from src.grpc_client.client_services.api_key_service_client import ApiKeyServiceClient
from src.grpc_client.client_services.auth_service_client import AuthServiceClient
from src.grpc_client.client_services.user_service_client import UserServiceClient
from src.grpc_client.constants import GrpcServices
from src.grpc_client.grpc_client import GRPCClient
from src.loggers.holler_rpc_logger import HollerRPCLogger

logger = HollerRPCLogger.get_logger()


class RPCServiceFactory:
    """Factory to centralize the creation of service clients."""

    @staticmethod
    def get_service(service_name: str) -> GRPCClient:

        if service_name == GrpcServices.AUTH:
            return AuthServiceClient()
        if service_name == GrpcServices.API_KEY:
            return ApiKeyServiceClient()
        if service_name == GrpcServices.USER:
            return UserServiceClient()

        # Future services can be added here.
        else:
            raise ValueError(f"Unknown service: {service_name}")
