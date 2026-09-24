from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.grpc_client.telephony_bridge import GRPC_VENDOR_TYPES, TalkoTelephonyBridge


def _client():
    from src.grpc_client.client_services.telephony_service_client import (
        TalkoTelephonyServiceClient,
    )

    with patch.object(TalkoTelephonyServiceClient, "__init__", lambda self: None):
        c = TalkoTelephonyServiceClient()
    c.control = AsyncMock()
    c.media = AsyncMock()
    return c


class TestBridge:
    def test_routing(self):
        b = TalkoTelephonyBridge(logger=MagicMock())
        assert b.should_use_grpc("otoba") is True
        assert b.should_use_grpc("OTOBA") is True
        assert b.should_use_grpc("tata_tele") is False
        assert b.should_use_grpc("") is False
        assert "otoba" in GRPC_VENDOR_TYPES

    @pytest.mark.asyncio
    async def test_grpc_hangup_passthrough(self):
        b = TalkoTelephonyBridge(logger=MagicMock())
        client = MagicMock()
        client.hangup_call = AsyncMock(return_value={"success": True})
        out = await b.grpc_hangup(client, "C1", "V1")
        assert out["success"] is True
        client.hangup_call.assert_awaited_once_with(call_id="C1", vendor_config_id="V1")


class TestTelephonyClient:
    @pytest.mark.asyncio
    async def test_hangup_maps_response(self):
        c = _client()
        c.control.Hangup = AsyncMock(return_value=MagicMock(success=True, message="bye", call_id="C1"))
        out = await c.hangup_call("C1", vendor_config_id="V1")
        assert out == {"success": True, "message": "bye", "call_id": "C1"}

    @pytest.mark.asyncio
    async def test_transfer_maps_response(self):
        c = _client()
        c.control.Transfer = AsyncMock(return_value=MagicMock(success=True, message="ok", call_id="C1"))
        out = await c.transfer_call("C1", "999", vendor_config_id="V1")
        assert out["call_id"] == "C1"
        req = c.control.Transfer.await_args.args[0]
        assert req.destination_number == "999"

    @pytest.mark.asyncio
    async def test_status_maps_response(self):
        c = _client()
        c.control.GetCallStatus = AsyncMock(
            return_value=MagicMock(call_id="C1", call_status="connected", connected=True)
        )
        out = await c.get_call_status("C1")
        assert out == {
            "call_id": "C1",
            "call_status": "connected",
            "connected": True,
        }

    @pytest.mark.asyncio
    async def test_stream_audio_roundtrip(self):
        c = _client()

        async def fake_stream(_gen):
            from src.pub import telephony_pb2

            yield telephony_pb2.AudioChunk(call_id="C1", payload=b"down", codec="mulaw_8k", seq=1)

        c.media.StreamAudio = MagicMock(side_effect=fake_stream)

        async def uplink():
            yield {"payload": b"up", "seq": 0}

        got = [m async for m in c.stream_audio(uplink(), "C1")]
        assert got[0]["payload"] == b"down"
        assert got[0]["codec"] == "mulaw_8k"


class TestFactoryAndService:
    def test_factory_telephony_disabled(self):
        # gRPC disabled for now — factory must refuse every plane.
        from src.grpc_client.constants import TalkoGrpcServices
        from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory

        with pytest.raises(RuntimeError, match="gRPC disabled"):
            TalkoRPCServiceFactory.get_service(TalkoGrpcServices.TELEPHONY)

    @pytest.mark.asyncio
    async def test_service_grpc_hangup_releases_pool(self):
        from src.components.call_management.services import TalkoCallService

        with patch.object(TalkoCallService, "__init__", lambda self, **k: None):
            svc = TalkoCallService()
        svc._TalkoCallService__logger = MagicMock()
        svc._TalkoCallService__channel_pool_service = AsyncMock()
        bridge = MagicMock()
        bridge.grpc_hangup = AsyncMock(return_value={"success": True, "message": "bye"})
        svc._TalkoCallService__telephony_bridge = bridge
        svc._TalkoCallService__telephony_client = MagicMock()
        out = await svc.grpc_hangup_call("C1", "V1")
        assert out.success is True
        svc._TalkoCallService__channel_pool_service.release.assert_awaited_once_with("V1")

    @pytest.mark.asyncio
    async def test_service_requires_client(self):
        from src.components.call_management.services import TalkoCallService
        from src.exceptions import TalkoResourceNotFound

        with patch.object(TalkoCallService, "__init__", lambda self, **k: None):
            svc = TalkoCallService()
        svc._TalkoCallService__logger = MagicMock()
        svc._TalkoCallService__channel_pool_service = None
        svc._TalkoCallService__telephony_client = None
        svc._TalkoCallService__telephony_bridge = None
        with pytest.raises(TalkoResourceNotFound):
            await svc.grpc_hangup_call("C1", "V1")
