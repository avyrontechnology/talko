"""gRPC telephony control plane (extracted from call_management/services.py).

Same hangup/transfer/status semantics as the REST path, but over the gRPC
TelephonyControl service instead of vendor HTTP APIs. Kept as a standalone
service so the main TalkoCallService stays focused on the live Tata flow.
Currently dormant (gRPC disabled) — TalkoCallService delegates to it.
"""

from typing import Any

from src.components.call_management.dto import TalkoContract as call_contract
from src.components.call_management.messages import CALL_HANGUP_INITIATED
from src.exceptions import TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoGrpcControlService:
    def __init__(
        self,
        logger: TalkoServiceLogger,
        telephony_client: Any = None,
        telephony_bridge: Any = None,
        channel_pool_service: Any = None,
    ) -> None:
        self.__logger = logger
        self.__telephony_client = telephony_client
        self.__telephony_bridge = telephony_bridge
        self.__channel_pool_service = channel_pool_service

    def _require_telephony(self) -> Any:
        if self.__telephony_client is None:
            raise TalkoResourceNotFound("gRPC telephony client not configured")
        if self.__telephony_bridge is None:
            from src.grpc_client.telephony_bridge import TalkoTelephonyBridge

            self.__telephony_bridge = TalkoTelephonyBridge(logger=self.__logger)
        return self.__telephony_client

    async def grpc_hangup_call(self, call_id: str, vendor_config_id: str) -> call_contract.HangupCallResponse:
        telephony_client = self._require_telephony()
        result = await self.__telephony_bridge.grpc_hangup(telephony_client, call_id, vendor_config_id)
        if self.__channel_pool_service is not None:
            try:
                await self.__channel_pool_service.release(vendor_config_id)
            except Exception as pool_e:
                self.__logger.error(f"Channel pool release failed (non-fatal): {str(pool_e)}")
        return call_contract.HangupCallResponse(
            success=bool(result.get("success", False)),
            message=str(result.get("message", CALL_HANGUP_INITIATED)),
        )

    async def grpc_transfer_call(self, call_id: str, destination_number: str, vendor_config_id: str) -> dict[str, Any]:
        telephony_client = self._require_telephony()
        return await self.__telephony_bridge.grpc_transfer(
            telephony_client, call_id, destination_number, vendor_config_id
        )

    async def grpc_call_status(self, call_id: str, vendor_config_id: str) -> dict[str, Any]:
        telephony_client = self._require_telephony()
        result = await telephony_client.get_call_status(call_id=call_id, vendor_config_id=vendor_config_id)
        return result or {"call_id": call_id, "connected": False}
