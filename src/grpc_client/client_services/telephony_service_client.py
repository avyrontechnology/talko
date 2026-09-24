from collections.abc import AsyncIterator

import grpc
from grpc.aio import AioRpcError

from src.grpc_client.grpc_client import TalkoGRPCClient
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.pub import telephony_pb2, telephony_pb2_grpc

logger = TalkoServiceLogger.get_logger()


class TalkoTelephonyServiceClient(TalkoGRPCClient):
    """gRPC client for the vendor telephony plane (control + media pipe).

    Mirrors REST semantics (POST /call/hangup, POST /call/transfer) so the
    same call_id / destination_number flows work over gRPC for vendors
    whose control plane is gRPC (e.g. OTOBA) instead of HTTP (Tata).
    """

    def __init__(self):
        super().__init__()
        self.control = telephony_pb2_grpc.TelephonyControlStub(self.channel)
        self.media = telephony_pb2_grpc.MediaPipeStub(self.channel)

    @TalkoGRPCClient.call_with_retry
    async def hangup_call(
        self,
        call_id: str,
        vendor_config_id: str = "",
        enable_ai_bridge: bool = False,
    ) -> dict | None:
        request = telephony_pb2.HangupRequest(
            call_id=call_id,
            vendor_config_id=vendor_config_id,
            enable_ai_bridge=enable_ai_bridge,
        )
        try:
            response = await self.control.Hangup(request)
            return {
                "success": response.success,
                "message": response.message,
                "call_id": response.call_id or call_id,
            }
        except AioRpcError as exc:
            logger.error(f"gRPC Hangup failed for {call_id}: {exc}")
            raise

    @TalkoGRPCClient.call_with_retry
    async def transfer_call(
        self,
        call_id: str,
        destination_number: str,
        vendor_config_id: str = "",
        enable_ai_bridge: bool = False,
    ) -> dict | None:
        request = telephony_pb2.TransferRequest(
            call_id=call_id,
            destination_number=destination_number,
            vendor_config_id=vendor_config_id,
            enable_ai_bridge=enable_ai_bridge,
        )
        try:
            response = await self.control.Transfer(request)
            return {
                "success": response.success,
                "message": response.message,
                "call_id": response.call_id or call_id,
            }
        except AioRpcError as exc:
            logger.error(f"gRPC Transfer failed for {call_id}: {exc}")
            raise

    @TalkoGRPCClient.call_with_retry
    async def hold_call(self, call_id: str, hold: bool = True, vendor_config_id: str = "") -> dict | None:
        request = telephony_pb2.HoldRequest(call_id=call_id, hold=hold, vendor_config_id=vendor_config_id)
        try:
            response = await self.control.Hold(request)
            return {"success": response.success, "message": response.message}
        except AioRpcError as exc:
            logger.error(f"gRPC Hold failed for {call_id}: {exc}")
            raise

    @TalkoGRPCClient.call_with_retry
    async def mute_call(self, call_id: str, mute: bool = True, vendor_config_id: str = "") -> dict | None:
        request = telephony_pb2.MuteRequest(call_id=call_id, mute=mute, vendor_config_id=vendor_config_id)
        try:
            response = await self.control.Mute(request)
            return {"success": response.success, "message": response.message}
        except AioRpcError as exc:
            logger.error(f"gRPC Mute failed for {call_id}: {exc}")
            raise

    @TalkoGRPCClient.call_with_retry
    async def get_call_status(self, call_id: str, vendor_config_id: str = "") -> dict | None:
        request = telephony_pb2.CallStatusRequest(call_id=call_id, vendor_config_id=vendor_config_id)
        try:
            response = await self.control.GetCallStatus(request)
            return {
                "call_id": response.call_id or call_id,
                "call_status": response.call_status,
                "connected": response.connected,
            }
        except AioRpcError as exc:
            logger.error(f"gRPC GetCallStatus failed for {call_id}: {exc}")
            raise

    async def stream_audio(
        self, chunks: AsyncIterator[dict], call_id: str, codec: str = "mulaw_8k"
    ) -> AsyncIterator[dict]:
        """Bidirectional media pipe. Yields downlink frames as dicts.

        chunks: async iterator of {"payload": bytes, "seq": int}.
        Reuses the mulaw_8k/pcm_48k codec labels from TalkoAudioBridge
        (pstn/services.py) so the pipe negotiates the same formats.
        """

        async def _request_gen():
            async for chunk in chunks:
                yield telephony_pb2.AudioChunk(
                    call_id=call_id,
                    payload=chunk.get("payload", b""),
                    codec=chunk.get("codec", codec),
                    seq=int(chunk.get("seq", 0)),
                    end_of_stream=bool(chunk.get("end_of_stream", False)),
                )

        try:
            async for reply in self.media.StreamAudio(_request_gen()):
                yield {
                    "call_id": reply.call_id,
                    "payload": reply.payload,
                    "codec": reply.codec,
                    "seq": reply.seq,
                    "end_of_stream": reply.end_of_stream,
                }
        except grpc.aio.AioRpcError as exc:
            logger.error(f"gRPC StreamAudio failed for {call_id}: {exc}")
            raise
