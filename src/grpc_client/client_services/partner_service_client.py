"""Console partner reads for Talko hot-path gates.

Talko owns no partner master: partner existence, liveness and feature
flags come from console-core. All methods fail closed (None / raise)
so callers gate traffic instead of failing open.
"""
import grpc
from grpc.aio import AioRpcError

from src.grpc_client.console_ids import console_id_str
from src.grpc_client.grpc_client import TalkoGRPCClient
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.pub import auth_pb2, auth_pb2_grpc

logger = TalkoServiceLogger.get_logger()


class TalkoPartnerServiceClient(TalkoGRPCClient):
    def __init__(self, server_address: str = ""):
        super().__init__(server_address=server_address)
        self.stub = auth_pb2_grpc.AuthServiceStub(self.channel)

    @TalkoGRPCClient.call_with_retry
    async def get_partner_details(self, partner_id):
        """Console partner master row (is_active, status, licenses)."""
        pid = console_id_str(partner_id)
        logger.info(f"Sending GetPartnerDetails request for partner_id: {pid}")
        request = auth_pb2.GetPartnerDetailsRequest(partner_id=pid)
        try:
            response = await self.stub.GetPartnerDetails(request)
            detail = response.partner_detail
            return {
                "partner_id": detail.partner_id,
                "name": detail.name,
                "is_active": detail.is_active,
                "partner_status": detail.partner_status,
                "active_license": detail.active_license,
            }
        except AioRpcError as exc:
            logger.error(f"Error during GetPartnerDetails call: {exc}")
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise

    @TalkoGRPCClient.call_with_retry
    async def get_partner_meta_data(self, partner_id):
        """Console partner metadata (feature flags incl. talko enablement)."""
        pid = console_id_str(partner_id)
        logger.info(f"Sending GetPartnerMetaDataDetails request for partner_id: {pid}")
        request = auth_pb2.GetPartnerMetaDataDetailsRequest(partner_id=pid)
        try:
            response = await self.stub.GetPartnerMetaDataDetails(request)
            return {
                "is_talko_enabled": response.is_talko_enabled,
                "type_of_business": response.type_of_business,
                "subscription_mode": response.subscription_mode,
            }
        except AioRpcError as exc:
            logger.error(f"Error during GetPartnerMetaDataDetails call: {exc}")
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise

    @TalkoGRPCClient.call_with_retry
    async def get_partner_services(self, partner_id):
        """Console partner service flags (dialer, GSM, meeting-log, popups)."""
        pid = console_id_str(partner_id)
        logger.info(f"Sending GetPartnerServicesDetails request for partner_id: {pid}")
        request = auth_pb2.GetPartnerServiceRequest(partner_id=pid)
        try:
            response = await self.stub.GetPartnerServicesDetails(request)
            return {
                "is_talko_service_enabled": response.is_talko_service_enabled,
                "is_gsm_calling_enabled": response.is_gsm_calling_enabled,
                "is_meeting_log_enabled": response.is_meeting_log_enabled,
                "enable_dialer": response.enable_dialer,
            }
        except AioRpcError as exc:
            logger.error(f"Error during GetPartnerServicesDetails call: {exc}")
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise

    async def is_partner_live(self, partner_id) -> bool:
        """Single gate for hot paths: exists + active in console."""
        try:
            detail = await self.get_partner_details(partner_id)
        except AioRpcError:
            return False
        if not detail:
            return False
        if detail.get("is_active") is False:
            return False
        status = (detail.get("partner_status") or "").upper()
        if status in ("SUSPENDED", "DELETED", "INACTIVE"):
            return False
        return True
