from typing import Any

from src.loggers.talko_service_logger import TalkoServiceLogger

# Vendor types whose control plane is gRPC (telephony.proto) rather than
# vendor HTTP APIs (Tata). Everything else keeps the existing REST path —
# the live Tata flow is untouched.
GRPC_VENDOR_TYPES = frozenset({"otoba", "telephony"})


class TalkoTelephonyBridge:
    """Routes mid-call signalling to REST vs gRPC by vendor_type."""

    def __init__(self, logger: TalkoServiceLogger) -> None:
        self.__logger = logger

    def should_use_grpc(self, vendor_type: str) -> bool:
        return (vendor_type or "").lower() in GRPC_VENDOR_TYPES

    def resolve_vendor_type(self, vendor_config: dict[str, Any]) -> str:
        return str(vendor_config.get("vendor_type") or "")

    async def grpc_hangup(self, telephony_client: Any, call_id: str, vendor_config_id: str) -> dict[str, Any]:
        self.__logger.info(f"Telephony bridge gRPC hangup call_id={call_id} vendor_config_id={vendor_config_id}")
        result = await telephony_client.hangup_call(call_id=call_id, vendor_config_id=vendor_config_id)
        return result or {"success": False, "message": "empty gRPC response"}

    async def grpc_transfer(
        self,
        telephony_client: Any,
        call_id: str,
        destination_number: str,
        vendor_config_id: str,
    ) -> dict[str, Any]:
        self.__logger.info(f"Telephony bridge gRPC transfer call_id={call_id} dest={destination_number}")
        result = await telephony_client.transfer_call(
            call_id=call_id,
            destination_number=destination_number,
            vendor_config_id=vendor_config_id,
        )
        return result or {"success": False, "message": "empty gRPC response"}
