import os

from src.grpc_client.client_services.api_key_service_client import TalkoApiKeyServiceClient
from src.grpc_client.client_services.auth_service_client import TalkoAuthServiceClient
from src.grpc_client.client_services.user_service_client import TalkoUserServiceClient
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.grpc_client import TalkoGRPCClient
from src.loggers.talko_rpc_logger import TalkoRPCLogger

logger = TalkoRPCLogger.get_logger()


class TalkoRPCServiceFactory:
    """Factory to centralize the creation of service clients."""

    @staticmethod
    def get_service(service_name: str) -> TalkoGRPCClient:

        if service_name == TalkoGrpcServices.AUTH:
            return TalkoAuthServiceClient()
        if service_name == TalkoGrpcServices.API_KEY:
            return TalkoApiKeyServiceClient()
        if service_name == TalkoGrpcServices.USER:
            return TalkoUserServiceClient()

        # Future services can be added here.
        else:
            raise ValueError(f"Unknown service: {service_name}")
