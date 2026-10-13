"""Relay client tests: talko -> fake console-core relay (in-process).

Fake servicer yahin hai (console-core ka asli server udhar hota hai
— contract same, isliye test valid). Repo convention: @pytest.mark.asyncio.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest
import pytest_asyncio

from src.grpc_client.client_services.relay_service_client import TalkoRelayServiceClient
from src.pub import relay_pb2
from src.pub.relay_pb2_grpc import (
    RelayServiceServicer,
    add_RelayServiceServicer_to_server,
)


class FakeRelay(RelayServiceServicer):
    calls: int = 0

    async def RouteCallStatus(self, request, context):
        FakeRelay.calls += 1
        if request.target not in ("", "telephony"):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "unknown target")
        return relay_pb2.RouteCallStatusResponse(
            call_id=request.call_id,
            call_status="in-progress",
            connected=True,
            via="grpc",
        )

    async def WatchCallStatus(self, request, context):
        for seq in range(1, (request.max_updates or 3) + 1):
            yield relay_pb2.CallStatusUpdate(
                call_id=request.call_id,
                call_status="in-progress",
                connected=True,
                seq=seq,
            )


@pytest_asyncio.fixture
async def relay_client():
    FakeRelay.calls = 0
    server = grpc.aio.server()
    add_RelayServiceServicer_to_server(FakeRelay(), server)
    port = server.add_insecure_port("localhost:0")
    await server.start()
    client = TalkoRelayServiceClient(server_address=f"localhost:{port}")
    yield client
    await client.close_channel()
    await server.stop(None)


@pytest.mark.asyncio
async def test_route_call_status_via_relay(relay_client):
    res = await relay_client.route_call_status(call_id="T1")
    assert res["call_id"] == "T1"
    assert res["call_status"] == "in-progress"
    assert res["via"] == "grpc"
    assert FakeRelay.calls == 1


@pytest.mark.asyncio
async def test_watch_call_status_streams(relay_client):
    got = [
        u
        async for u in relay_client.watch_call_status(
            call_id="T2", max_updates=3, poll_interval_ms=10
        )
    ]
    assert [u["seq"] for u in got] == [1, 2, 3]


@pytest.mark.asyncio
async def test_route_unknown_target_propagates(relay_client):
    res = await relay_client.route_call_status(call_id="T3", target="nope")
    # talko convention: retry exhausts -> None (fail visible, no crash)
    assert res is None


@pytest.mark.asyncio
async def test_control_service_uses_relay_when_flag_on():
    from src.components.call_management.grpc_control_service import (
        TalkoGrpcControlService,
    )

    relay = AsyncMock()
    relay.route_call_status = AsyncMock(
        return_value={"call_id": "T4", "connected": True, "via": "grpc"}
    )
    svc = TalkoGrpcControlService(logger=MagicMock(), relay_client=relay)
    with patch(
        "src.components.call_management.grpc_control_service.TalkoENV.TALKO_RELAY_ENABLED",
        "true",
    ):
        out = await svc.call_status("T4", "V1")
    assert out["via"] == "grpc"
    relay.route_call_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_control_service_falls_back_when_flag_off():
    from src.components.call_management.grpc_control_service import (
        TalkoGrpcControlService,
    )

    telephony = AsyncMock()
    telephony.get_call_status = AsyncMock(
        return_value={"call_id": "T5", "connected": True}
    )
    svc = TalkoGrpcControlService(
        logger=MagicMock(), telephony_client=telephony, relay_client=AsyncMock()
    )
    with patch(
        "src.components.call_management.grpc_control_service.TalkoENV.TALKO_RELAY_ENABLED",
        "false",
    ):
        out = await svc.call_status("T5", "V1")
    assert out["connected"] is True
    assert "via" not in out
    telephony.get_call_status.assert_awaited_once()
