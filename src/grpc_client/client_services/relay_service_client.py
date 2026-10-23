from collections.abc import AsyncIterator

import grpc
from grpc.aio import AioRpcError

from src.grpc_client.grpc_client import TalkoGRPCClient
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.pub import relay_pb2, relay_pb2_grpc

logger = TalkoServiceLogger.get_logger()


class TalkoRelayServiceClient(TalkoGRPCClient):
    """Relay client: talko -> console-core -> target plane.

    Contract owner console-core hai (proto wahan se copy).
    Yahan sirf caller hai — servicer console-core par serve hota hai.
    Template: TalkoTelephonyServiceClient (same base, same retry style).
    """

    def __init__(self, server_address: str = ""):
        super().__init__(server_address=server_address)
        self.relay = relay_pb2_grpc.RelayServiceStub(self.channel)

    @TalkoGRPCClient.call_with_retry
    async def route_call_status(
        self, call_id: str, vendor_config_id: str = "", target: str = "telephony"
    ) -> dict | None:
        request = relay_pb2.RouteCallStatusRequest(
            call_id=call_id, vendor_config_id=vendor_config_id, target=target
        )
        try:
            response = await self.relay.RouteCallStatus(request)
            return {
                "call_id": response.call_id or call_id,
                "call_status": response.call_status,
                "connected": response.connected,
                "via": response.via,
            }
        except AioRpcError as exc:
            logger.error(f"gRPC RouteCallStatus failed for {call_id}: {exc}")
            raise

    async def watch_call_status(
        self,
        call_id: str,
        vendor_config_id: str = "",
        target: str = "telephony",
        max_updates: int = 3,
        poll_interval_ms: int = 200,
    ) -> AsyncIterator[dict]:
        """Server-streaming caller. Retry decorator NAHI (generator par
        retry ka matlab adhura stream dobara — seq gap chhup jayega).
        Fail ho to caller dobara `watch` bulaye, fresh stream milega."""
        request = relay_pb2.WatchCallStatusRequest(
            call_id=call_id,
            vendor_config_id=vendor_config_id,
            target=target,
            max_updates=max_updates,
            poll_interval_ms=poll_interval_ms,
        )
        try:
            async for update in self.relay.WatchCallStatus(request):
                yield {
                    "call_id": update.call_id,
                    "call_status": update.call_status,
                    "connected": update.connected,
                    "seq": update.seq,
                }
        except grpc.aio.AioRpcError as exc:
            logger.error(f"gRPC WatchCallStatus failed for {call_id}: {exc}")
            raise
