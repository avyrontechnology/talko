import base64
import asyncio
import json
from unittest.mock import MagicMock

import pytest

from src.components.pstn.constants import TalkoCallDirection, TalkoPSTNProvider
from src.components.pstn.dto import TalkoCallContext
from src.components.pstn.providers.tata_tele.handler import TalkoTataTeleProvider
from src.components.pstn.voiceai_relay import TalkoVoiceaiRelay


def make_ctx(**overrides):
    defaults = dict(
        provider=TalkoPSTNProvider.TATA_TELE,
        call_sid="CA123",
        did_number="918045678901",
        caller_number="919812345678",
        direction=TalkoCallDirection.OUTBOUND,
        stream_sid="MZ123",
        partner_id=2,
    )
    defaults.update(overrides)
    return TalkoCallContext(**defaults)


class FakeTataWs:
    """Collects what the relay sends toward Tata."""

    def __init__(self):
        self.sent = []
        self.closed = False

    async def send_text(self, data: str):
        self.sent.append(json.loads(data))

    async def close(self):
        self.closed = True


class FakeVoiceaiSocket:
    """Queue-driven stand-in for the voiceai agent socket.

    Behaves like a real socket: queued frames are delivered, then receive
    parks until close() (local) — unless remote_close_when_empty, which
    simulates the agent hanging up (remote close -> receive returns None).
    """

    def __init__(self, inbound_frames, remote_close_when_empty=False):
        self.inbound = list(inbound_frames)
        self.remote_close_when_empty = remote_close_when_empty
        self.sent = []
        self.closed = False
        self.__unblocked = asyncio.Event()

    async def send_str(self, data: str):
        self.sent.append(json.loads(data))

    async def receive_str(self):
        if self.inbound:
            return self.inbound.pop(0)
        if self.remote_close_when_empty:
            return None
        await self.__unblocked.wait()
        return None

    async def close(self):
        self.closed = True
        self.__unblocked.set()


def tata_media(chunk, payload=b"\x01\x02"):
    return json.dumps(
        {
            "event": "media",
            "streamSid": "MZ123",
            "media": {"payload": base64.b64encode(payload).decode(), "chunk": chunk},
        }
    )


async def fake_raw_events(frames):
    for f in frames:
        yield f


def make_relay(vws, ticket="tick"):
    async def ticket_provider():
        return ticket

    async def ws_connector(url):
        assert url == "wss://voiceai.local/chat/v1/agent_1?token=tick"
        return vws

    return TalkoVoiceaiRelay(
        ws_base_url="wss://voiceai.local",
        api_base_url="https://voiceai.local",
        api_key="key",
        logger=MagicMock(),
        ticket_provider=ticket_provider,
        ws_connector=ws_connector,
    )


class TestVoiceaiRelayOutbound:
    @pytest.mark.asyncio
    async def test_full_call_flow(self):
        """Tata start+media+mark-ack+stop; voiceai media+mark+clear.

        Asserts translation both ways incl. timestamp injection, mark-name
        preservation, and stop forwarding.
        """
        agent_audio = base64.b64encode(b"\xaa" * 160).decode()
        vws = FakeVoiceaiSocket(
            [
                json.dumps({"event": "media", "streamSid": "MZ123", "media": {"payload": agent_audio}}),
                json.dumps({"event": "mark", "streamSid": "MZ123", "mark": {"name": "m-uuid-1"}}),
                json.dumps({"event": "clear", "streamSid": "MZ123"}),
                # then socket closes (agent done) — but Tata stop ends first
            ]
        )
        tata = FakeTataWs()
        relay = make_relay(vws)

        start = {
            "event": "start",
            "streamSid": "MZ123",
            "start": {
                "callSid": "CA123",
                "streamSid": "MZ123",
                "from": "918045678901",
                "to": "919812345678",
                "direction": "outbound",
            },
        }
        frames = [
            tata_media(1),
            tata_media(2),
            json.dumps({"event": "mark", "streamSid": "MZ123", "mark": {"name": "m-uuid-1"}}),
            json.dumps({"event": "stop", "streamSid": "MZ123", "stop": {"reason": "hangup"}}),
        ]
        await relay.run(tata, TalkoTataTeleProvider(), make_ctx(), start, fake_raw_events(frames), "agent_1")

        # ── Tata -> voiceai ──
        first = vws.sent[0]
        assert first["event"] == "start"  # start forwarded first
        assert first["start"]["callSid"] == "CA123"
        medias = [m for m in vws.sent if m["event"] == "media"]
        assert [m["media"]["timestamp"] for m in medias] == [20, 40]
        # voiceai's own mark ack routed back to it
        assert {"event": "mark", "streamSid": "MZ123", "mark": {"name": "m-uuid-1"}} in vws.sent
        assert vws.sent[-1]["event"] == "stop"
        assert vws.closed

        # ── voiceai -> Tata ──
        tata_medias = [m for m in tata.sent if m["event"] == "media"]
        assert len(tata_medias) == 1
        assert tata_medias[0]["streamSid"] == "MZ123"
        assert tata_medias[0]["media"]["chunk"] == 1
        assert base64.b64decode(tata_medias[0]["media"]["payload"]) == b"\xaa" * 160
        tata_marks = [m["mark"]["name"] for m in tata.sent if m["event"] == "mark"]
        assert "m-uuid-1" in tata_marks  # voiceai mark name preserved verbatim
        assert any(m["event"] == "clear" for m in tata.sent)  # barge-in clear
        assert not tata.closed  # Tata ended the call itself via stop

    @pytest.mark.asyncio
    async def test_voiceai_hangup_closes_tata_leg(self):
        """voiceai socket close (agent hangup) ends the relay + Tata socket."""
        vws = FakeVoiceaiSocket([], remote_close_when_empty=True)
        tata = FakeTataWs()
        relay = make_relay(vws)

        async def tata_idles_then_stops():
            # Tata leg idles until the relay closes it; afterwards Tata
            # would send stop — model by yielding stop once closed.
            while not tata.closed:
                await asyncio.sleep(0.01)
            yield json.dumps({"event": "stop", "streamSid": "MZ123"})

        await relay.run(tata, TalkoTataTeleProvider(), make_ctx(), {"event": "start", "start": {}}, tata_idles_then_stops(), "agent_1")
        assert tata.closed
        assert vws.closed

    @pytest.mark.asyncio
    async def test_own_mark_ack_consumed_without_forward_or_delay(self):
        """Acks for the relay's own per-chunk marks must not hit voiceai
        and must not incur the grace wait (they arrive ~50/sec)."""
        vws = FakeVoiceaiSocket([], remote_close_when_empty=False)
        tata = FakeTataWs()
        relay = make_relay(vws)
        start = {"event": "start", "start": {}}
        frames = [
            json.dumps({"event": "mark", "streamSid": "MZ123", "mark": {"name": "voiceai-chunk-7"}}),
            json.dumps({"event": "stop", "streamSid": "MZ123"}),
        ]
        import time

        t0 = time.perf_counter()
        await asyncio.wait_for(
            relay.run(tata, TalkoTataTeleProvider(), make_ctx(), start, fake_raw_events(frames), "agent_1"),
            timeout=10,
        )
        elapsed = time.perf_counter() - t0
        assert elapsed < 5, "own-mark ack must not grace-wait (took {:.2f}s)".format(elapsed)
        assert all(m["event"] != "mark" for m in vws.sent)

    def test_ws_url(self):
        relay = TalkoVoiceaiRelay(
            ws_base_url="wss://v.local/", api_base_url="https://v.local",
            api_key="k", logger=MagicMock(),
        )
        assert relay.ws_url("a1", "t") == "wss://v.local/chat/v1/a1?token=t"


class TestFrameSplitting:
    @pytest.mark.asyncio
    async def test_large_voiceai_blob_splits_into_160b_tata_frames(self):
        """voiceai emits multi-hundred-ms audio blobs per message; Tata's
        contract is exactly 160 B per media event. A 400 B blob must cross
        as 3 frames (160 + 160 + 80 padded with μ-law silence), chunks 1-3."""
        agent_audio = base64.b64encode(b"\xaa" * 400).decode()
        vws = FakeVoiceaiSocket(
            [json.dumps({"event": "media", "streamSid": "MZ123", "media": {"payload": agent_audio}})],
            remote_close_when_empty=True,
        )
        tata = FakeTataWs()
        relay = make_relay(vws)
        start = {"event": "start", "start": {}}

        async def tata_idles_then_stops():
            while not tata.closed:
                await asyncio.sleep(0.01)
            yield json.dumps({"event": "stop", "streamSid": "MZ123"})

        await asyncio.wait_for(
            relay.run(tata, TalkoTataTeleProvider(), make_ctx(), start, tata_idles_then_stops(), "agent_1"),
            timeout=10,
        )
        tata_medias = [m for m in tata.sent if m["event"] == "media"]
        assert len(tata_medias) == 3
        assert [m["media"]["chunk"] for m in tata_medias] == [1, 2, 3]
        payloads = [base64.b64decode(m["media"]["payload"]) for m in tata_medias]
        assert all(len(p) == 160 for p in payloads)
        assert payloads[0] == b"\xaa" * 160
        assert payloads[1] == b"\xaa" * 160
        assert payloads[2] == b"\xaa" * 80 + b"\xff" * 80
