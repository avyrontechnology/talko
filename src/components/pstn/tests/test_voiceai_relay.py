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

    def __init__(self, inbound_frames, remote_close_when_empty=False, deliver_delay=0.0):
        self.inbound = list(inbound_frames)
        self.remote_close_when_empty = remote_close_when_empty
        self.deliver_delay = deliver_delay
        self.sent = []
        self.closed = False
        self.__unblocked = asyncio.Event()

    async def send_str(self, data: str):
        self.sent.append(json.loads(data))

    async def receive_str(self):
        if self.deliver_delay:
            await asyncio.sleep(self.deliver_delay)
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


def make_relay(vws, ticket="tick", logger=None, **kwargs):
    async def ticket_provider():
        return ticket

    async def ws_connector(url):
        assert url == "wss://voiceai.local/chat/v1/agent_1?token=tick"
        return vws

    return TalkoVoiceaiRelay(
        ws_base_url="wss://voiceai.local",
        api_base_url="https://voiceai.local",
        api_key="key",
        logger=logger or MagicMock(),
        ticket_provider=ticket_provider,
        ws_connector=ws_connector,
        **kwargs,
    )


class TestVoiceaiRelayOutbound:
    @pytest.mark.asyncio
    async def test_full_call_flow(self):
        """Tata start+media+stop; voiceai media+mark.

        Asserts translation both ways incl. timestamp injection and stop
        forwarding. Voiceai turn marks are acked LOCALLY (never forwarded
        to Tata — Tata sees holler-shaped media+sparse-mark traffic only),
        so a Tata-side ack of the voiceai mark name must NOT route back.
        (Barge-in clear semantics live in TestRealtimePacing.)
        """
        agent_audio = base64.b64encode(b"\xaa" * 160).decode()
        vws = FakeVoiceaiSocket(
            [
                json.dumps({"event": "media", "streamSid": "MZ123", "media": {"payload": agent_audio}}),
                json.dumps({"event": "mark", "streamSid": "MZ123", "mark": {"name": "m-uuid-1"}}),
                # then socket parks (agent idle) — Tata stop ends the call
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
            json.dumps({"event": "stop", "streamSid": "MZ123", "stop": {"reason": "hangup"}}),
        ]
        await relay.run(tata, TalkoTataTeleProvider(), make_ctx(), start, fake_raw_events(frames), "agent_1")

        # ── Tata -> voiceai ──
        first = vws.sent[0]
        assert first["event"] == "start"  # start forwarded first
        assert first["start"]["callSid"] == "CA123"
        medias = [m for m in vws.sent if m["event"] == "media"]
        assert [m["media"]["timestamp"] for m in medias] == [20, 40]
        # voiceai's own mark acked locally with the same name
        assert {"event": "mark", "streamSid": "MZ123", "mark": {"name": "m-uuid-1"}} in vws.sent
        assert any(m["event"] == "stop" for m in vws.sent)
        assert vws.closed

        # ── voiceai -> Tata ──
        tata_medias = [m for m in tata.sent if m["event"] == "media"]
        assert len(tata_medias) == 1
        assert tata_medias[0]["streamSid"] == "MZ123"
        assert tata_medias[0]["media"]["chunk"] == 1
        assert base64.b64decode(tata_medias[0]["media"]["payload"]) == b"\xaa" * 160
        tata_marks = [m["mark"]["name"] for m in tata.sent if m["event"] == "mark"]
        # voiceai turn marks never reach Tata (local-ack only); only the
        # relay's own sparse pacing mark for frame 1 goes out
        assert "m-uuid-1" not in tata_marks
        assert tata_marks == ["voiceai-chunk-1"]
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


def _tata_medias(tata):
    return [m for m in tata.sent if m["event"] == "media"]


def _own_mark_names(tata):
    return [
        m["mark"]["name"]
        for m in tata.sent
        if m["event"] == "mark" and m["mark"]["name"].startswith("voiceai-chunk-")
    ]


def _ack(name):
    return json.dumps({"event": "mark", "streamSid": "MZ123", "mark": {"name": name}})


class TestRealtimePacing:
    @pytest.mark.asyncio
    async def test_pump_stalls_when_window_full_until_ack(self):
        """6-frame blob with window=2: the pump must stop after 2 frames and
        resume only as Tata acks — realtime pacing instead of bursts."""
        agent_audio = base64.b64encode(b"\xbb" * 960).decode()
        vws = FakeVoiceaiSocket(
            [json.dumps({"event": "media", "streamSid": "MZ123", "media": {"payload": agent_audio}})],
        )
        tata = FakeTataWs()
        relay = make_relay(vws, max_pending_marks=2, ack_wait_seconds=5, mark_every_n_frames=1)
        start = {"event": "start", "start": {}}

        async def tata_acks_paced():
            acked = set()
            # phase 1: window fills — prove the pump stalls with no acks
            for _ in range(200):
                if len(_tata_medias(tata)) >= 2:
                    break
                await asyncio.sleep(0.01)
            assert len(_tata_medias(tata)) == 2
            await asyncio.sleep(0.2)
            assert len(_tata_medias(tata)) == 2, "pump must not burst past the ack window"
            # phase 2: ack everything as it arrives until all 6 cross
            for _ in range(1000):
                for name in _own_mark_names(tata):
                    if name not in acked:
                        acked.add(name)
                        yield _ack(name)
                if len(_tata_medias(tata)) >= 6:
                    break
                await asyncio.sleep(0.01)
            yield json.dumps({"event": "stop", "streamSid": "MZ123"})

        await asyncio.wait_for(
            relay.run(tata, TalkoTataTeleProvider(), make_ctx(), start, tata_acks_paced(), "agent_1"),
            timeout=15,
        )
        assert [m["media"]["chunk"] for m in _tata_medias(tata)] == [1, 2, 3, 4, 5, 6]

    @pytest.mark.asyncio
    async def test_clear_releases_window_and_drops_stale_queue(self):
        """Barge-in clear with a full window and zero acks: the reader must
        release the pump promptly (delivery is delayed so the sender is
        genuinely blocked when the clear lands), drop queued-but-unsent
        stale audio, and let fresh audio after the clear through — all
        without waiting out the 10 s ack timeout."""
        blob2 = base64.b64encode(b"\xcc" * 320).decode()  # frames 1-2
        blob1 = base64.b64encode(b"\xdd" * 160).decode()  # frame 3 (fresh)
        vws = FakeVoiceaiSocket(
            [
                json.dumps({"event": "media", "streamSid": "MZ123", "media": {"payload": blob2}}),
                json.dumps({"event": "clear", "streamSid": "MZ123"}),
                json.dumps({"event": "media", "streamSid": "MZ123", "media": {"payload": blob1}}),
            ],
            remote_close_when_empty=True,
            deliver_delay=0.05,
        )
        tata = FakeTataWs()
        relay = make_relay(vws, max_pending_marks=1, ack_wait_seconds=10, mark_every_n_frames=1)
        start = {"event": "start", "start": {}}

        async def tata_idles_then_stops():
            while not tata.closed:
                await asyncio.sleep(0.01)
            yield json.dumps({"event": "stop", "streamSid": "MZ123"})

        await asyncio.wait_for(
            relay.run(tata, TalkoTataTeleProvider(), make_ctx(), start, tata_idles_then_stops(), "agent_1"),
            timeout=5,  # needs 10 s+ if the clear didn't release frame 1's slot
        )
        # frame 1 sent, stale frame 2 dropped by the clear, fresh frame 3 sent
        assert [m["media"]["chunk"] for m in _tata_medias(tata)] == [1, 3]
        assert any(m["event"] == "clear" for m in tata.sent)

    @pytest.mark.asyncio
    async def test_send_rate_capped_at_realtime_despite_fast_acks(self):
        """Even with instant acks and a huge window, frames must leave at
        ~50/s realtime — the pacer (not Tata's ack speed) sets the rate, so
        Tata's playout gets a steady stream instead of bursts."""
        import time

        agent_audio = base64.b64encode(b"\xee" * 960).decode()  # 6 frames
        vws = FakeVoiceaiSocket(
            [json.dumps({"event": "media", "streamSid": "MZ123", "media": {"payload": agent_audio}})],
        )
        tata = FakeTataWs()
        relay = make_relay(vws, max_pending_marks=50, ack_wait_seconds=5)
        start = {"event": "start", "start": {}}

        async def tata_acks_instantly():
            acked = set()
            for _ in range(1000):
                for name in _own_mark_names(tata):
                    if name not in acked:
                        acked.add(name)
                        yield _ack(name)
                if len(_tata_medias(tata)) >= 6:
                    break
                await asyncio.sleep(0.005)
            yield json.dumps({"event": "stop", "streamSid": "MZ123"})

        t0 = time.monotonic()
        await asyncio.wait_for(
            relay.run(tata, TalkoTataTeleProvider(), make_ctx(), start, tata_acks_instantly(), "agent_1"),
            timeout=15,
        )
        elapsed = time.monotonic() - t0
        assert [m["media"]["chunk"] for m in _tata_medias(tata)] == [1, 2, 3, 4, 5, 6]
        # first frame immediate + 5 paced intervals of 20 ms (slop allowed)
        assert elapsed >= 0.09, "frames burst out without realtime pacing ({:.3f}s)".format(elapsed)

    @pytest.mark.asyncio
    async def test_marks_sent_sparsely_by_default(self):
        """60-frame blob with defaults: only frames 1 and 51 carry marks —
        Tata's mark path (a few marks/s) must not be flooded."""
        agent_audio = base64.b64encode(b"\xef" * 9600).decode()  # 60 frames
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
        assert [m["media"]["chunk"] for m in _tata_medias(tata)] == list(range(1, 61))
        assert _own_mark_names(tata) == ["voiceai-chunk-1", "voiceai-chunk-51"]


class TestLatencySpans:
    @pytest.mark.asyncio
    async def test_timings_line_logged_with_spans(self):
        """Phase-0 instrumentation: Ended is followed by a machine-readable
        timings line carrying every span (ms since run entry)."""
        agent_audio = base64.b64encode(b"\xaa" * 160).decode()
        vws = FakeVoiceaiSocket(
            [json.dumps({"event": "media", "streamSid": "MZ123", "media": {"payload": agent_audio}})],
            remote_close_when_empty=True,
        )
        tata = FakeTataWs()
        logger = MagicMock()
        relay = make_relay(vws, logger=logger)
        start = {"event": "start", "start": {}}

        async def tata_idles_then_stops():
            while not tata.closed:
                await asyncio.sleep(0.01)
            yield json.dumps({"event": "stop", "streamSid": "MZ123"})

        await asyncio.wait_for(
            relay.run(tata, TalkoTataTeleProvider(), make_ctx(), start, tata_idles_then_stops(), "agent_1"),
            timeout=10,
        )
        lines = [" ".join(str(c) for c in call.args) for call in logger.info.call_args_list]
        timings = [line for line in lines if "voiceai timings" in line]
        assert len(timings) == 1
        for span in ("ticket_ms=", "ws_ms=", "first_media_ms=", "first_send_ms="):
            assert span in timings[0]


class TestPooledHttpClient:
    @pytest.mark.asyncio
    async def test_same_loop_reuses_client(self):
        from src.components.pstn.voiceai_relay import _pooled_http_client

        first = await _pooled_http_client(10.0)
        second = await _pooled_http_client(10.0)
        assert first is second
        await first.aclose()
