from src.grpc_client.client_services.wallet_service_client import (
    TalkoWalletServiceClient,
)
from src.grpc_client.client_services.api_key_service_client import TalkoApiKeyServiceClient
from src.grpc_client.client_services.partner_service_client import (
    TalkoPartnerServiceClient,
)
from src.grpc_client.client_services.auth_service_client import TalkoAuthServiceClient
from src.grpc_client.client_services.relay_service_client import TalkoRelayServiceClient
from src.grpc_client.client_services.telephony_service_client import (
    TalkoTelephonyServiceClient,
)
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
        if service_name == TalkoGrpcServices.TELEPHONY:
            return TalkoTelephonyServiceClient()
        if service_name == TalkoGrpcServices.RELAY:
            return TalkoRelayServiceClient()
        if service_name == TalkoGrpcServices.WALLET:
            return TalkoWalletServiceClient()
        if service_name == TalkoGrpcServices.PARTNER:
            return TalkoPartnerServiceClient()

        # Future services can be added here.
        raise RuntimeError(f"Unknown gRPC service: {service_name}")

    @staticmethod
    def get_optional_service(service_name: str) -> TalkoGRPCClient | None:
        """Same as get_service but returns None instead of raising.

        Use at eager call sites so Talko-native flows (which never touch the
        client) keep working while gRPC is disabled. Console-only paths must
        handle None explicitly and fail closed with a clear message.
        """
        try:
            return TalkoRPCServiceFactory.get_service(service_name)
        except RuntimeError as exc:
            logger.warning(f"gRPC unavailable, continuing without client: {exc}")
            return None
