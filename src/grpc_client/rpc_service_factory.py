# NOTE (grpc disabled for now): all client imports commented out — see
# get_service below. Uncomment to re-enable a plane.
# from src.grpc_client.client_services.api_key_service_client import TalkoApiKeyServiceClient
# from src.grpc_client.client_services.auth_service_client import TalkoAuthServiceClient
# from src.grpc_client.client_services.telephony_service_client import (
#     TalkoTelephonyServiceClient,
# )
# from src.grpc_client.client_services.user_service_client import TalkoUserServiceClient
from src.grpc_client.grpc_client import TalkoGRPCClient
from src.loggers.talko_rpc_logger import TalkoRPCLogger

logger = TalkoRPCLogger.get_logger()


class TalkoRPCServiceFactory:
    """Factory to centralize the creation of service clients."""

    @staticmethod
    def get_service(service_name: str) -> TalkoGRPCClient:
        # NOTE (grpc disabled for now): we will not use gRPC anywhere in our
        # code for now. All planes commented out — uncomment the branch you
        # need to re-enable it. Talko-native JWT + partner API keys keep
        # working (they verify locally, no gRPC hop).
        #
        # if service_name == TalkoGrpcServices.AUTH:
        #     return TalkoAuthServiceClient()
        # if service_name == TalkoGrpcServices.API_KEY:
        #     return TalkoApiKeyServiceClient()
        # if service_name == TalkoGrpcServices.USER:
        #     return TalkoUserServiceClient()
        # if service_name == TalkoGrpcServices.TELEPHONY:
        #     return TalkoTelephonyServiceClient()

        # Future services can be added here.
        raise RuntimeError(f"gRPC disabled for now (requested service: {service_name})")

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
