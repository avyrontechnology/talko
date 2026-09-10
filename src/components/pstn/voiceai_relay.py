"""Bidirectional media relay: Tata Tele <-> voiceai agent engine.

For voiceai-routed calls Talko stays the WebSocket endpoint for Tata, but
instead of bridging audio into a makun-ai LiveKit room it opens a second
WebSocket to voiceai's ``/chat/v1/{agent_id}`` and shuttles frames both
ways (see ``voiceai_events`` for the Tata<->Twilio-shape translation).

Lifeline:

1. Mint a single-use voiceai WS ticket
   (``POST {VOICEAI_API_BASE_URL}/auth/ws-ticket``, Bearer ``VOICEAI_API_KEY``).
2. Open ``{VOICEAI_WS_BASE_URL}/chat/v1/{agent_id}?token={ticket}`` and
   forward Tata's ``start`` event first — voiceai requires ``start``
   (``callSid``/``streamSid``) before any ``media``.
3. Pump Tata -> voiceai (caller audio, mark acks, stop) and
   voiceai -> Tata (agent audio, marks, barge-in clears) concurrently.
4. End: Tata ``stop`` is forwarded to voiceai and the relay returns; a
   voiceai-side close (agent hangup) closes the Tata socket best-effort
   and returns. Either way the caller (``TalkoPSTNBridgeService``) then
   runs its normal cleanup.

v1 limitations (documented, not silent):
- Agent-initiated hangup ends the media path only; it does not issue a
  Tata hangup API call (no vendor call-control handle in this path yet).
- Outbound framing assumes a Twilio-shaped provider (Tata Tele today).
"""

import asyncio
import audioop
import collections
import json
import time
from typing import Any, Awaitable, Callable, Deque, Dict, Optional, Set, Tuple

import aiohttp
import httpx

from src.components.pstn.dto import TalkoCallContext
from src.components.pstn.providers.base import TalkoAbstractPSTNProvider
from src.components.pstn.voiceai_events import forward_to_voiceai, parse_from_voiceai

VOICEAI_AGENT_ID_KEY = "voiceai_agent_id"
SEND_TIMEOUT_SECONDS = 5.0
# Prefix for the relay's own sparse marks (see RELAY_MARK_EVERY_N_FRAMES).
# Acks carrying this prefix are consumed immediately WITHOUT the grace wait.
OWN_MARK_PREFIX = "voiceai-chunk-"
# Tata's audio contract (see TalkoAbstractPSTNProvider): exactly 160 bytes of
# μ-law 8kHz per media event (20 ms). voiceai emits larger per-message blobs
# (hundreds of ms of audio); forwarding those 1:1 breaks Tata's playout
# (buffer bloat, growing ack lag, garbled/silent audio), so split them here.
# Short final frames are padded with μ-law silence (0xFF).
TATA_FRAME_BYTES = 160
_MULAW_SILENCE = b"\xff"

# Keep-alive HTTP clients keyed by running loop (one loop per worker
# process for the service lifetime). Never closed explicitly; the process
# owns them, same as the Redis pools elsewhere in the codebase.
_pooled_http_clients: Dict[int, "httpx.AsyncClient"] = {}


async def _pooled_http_client(timeout_seconds: float) -> "httpx.AsyncClient":
    """Shared httpx client for engine API calls (ticket minting).

    A per-call client redoes DNS+TCP+TLS (~1.4s to the engine); pooled
    connections reuse them. Falls back to a throwaway client outside a
    running loop (pure safety — callers always run looped).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return httpx.AsyncClient(timeout=timeout_seconds)
    key = id(loop)
    client = _pooled_http_clients.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=timeout_seconds)
        _pooled_http_clients[key] = client
    return client
# Outbound pacing toward Tata (relay-specific; the LiveKit path in
# services.py uses MAX_PENDING_MARKS=8 because its audio already arrives at
# realtime rate so the window never binds).
#
# Tata acks engine marks in ~0.7 s at low rates, but processes inbound marks
# at only a few per second: 50 marks/s (one per 20 ms frame) backs its ack
# queue up ~16 s deep, and any ack-sized window then throttles audio down to
# Tata's mark-processing rate (~5 frames/s — caller hears silence although
# every mark is eventually acked). So the relay:
# - sends at most 1 frame per 20 ms (realtime rate cap — the pacer, not the
#   acks, sets the rate),
# - marks only every MARK_EVERY_N_FRAMES-th frame (liveness signal without
#   flooding Tata's mark path), and
# - keeps up to ~1 s of audio in flight as pure backpressure for a truly
#   stalled Tata leg.
RELAY_MAX_PENDING_MARKS = 50
RELAY_FRAME_INTERVAL_SECONDS = 0.02
RELAY_ACK_WAIT_SECONDS = 2.0
RELAY_MARK_EVERY_N_FRAMES = 50


def _split_frames(payload: bytes):
    """Split one voiceai audio blob into Tata-sized 160B frames.

    Yields ``bytes`` objects of exactly ``TATA_FRAME_BYTES``; a short final
    frame is padded with μ-law silence (0xFF). Empty payloads yield nothing.
    """
    for offset in range(0, len(payload), TATA_FRAME_BYTES):
        frame = payload[offset : offset + TATA_FRAME_BYTES]
        if len(frame) < TATA_FRAME_BYTES:
            frame += _MULAW_SILENCE * (TATA_FRAME_BYTES - len(frame))
        yield frame


def _mulaw_rms(payload: bytes) -> int:
    """RMS energy of μ-law bytes on the 16-bit scale (0 = digital silence)."""
    if not payload:
        return 0
    try:
        return audioop.rms(audioop.ulaw2lin(payload, 2), 2)
    except Exception:
        return -1


class TalkoVoiceaiRelay:
    """Relays one live call between a Tata socket and a voiceai agent socket."""

    def __init__(
        self,
        ws_base_url: str,
        api_base_url: str,
        api_key: str,
        logger,
        ticket_timeout_seconds: float = 10.0,
        connect_timeout_seconds: float = 15.0,
        ticket_provider: Optional[Callable[[], Awaitable[str]]] = None,
        ws_connector: Optional[Callable[[str], Awaitable[Any]]] = None,
        max_pending_marks: int = RELAY_MAX_PENDING_MARKS,
        ack_wait_seconds: float = RELAY_ACK_WAIT_SECONDS,
        frame_interval_seconds: float = RELAY_FRAME_INTERVAL_SECONDS,
        mark_every_n_frames: int = RELAY_MARK_EVERY_N_FRAMES,
    ) -> None:
        self.__ws_base_url = ws_base_url.rstrip("/")
        self.__api_base_url = api_base_url.rstrip("/")
        self.__api_key = api_key
        self.__logger = logger
        self.__ticket_timeout = ticket_timeout_seconds
        self.__connect_timeout = connect_timeout_seconds
        self.__ticket_provider = ticket_provider or self.__mint_ticket
        self.__ws_connector = ws_connector or self.__connect_socket
        # Realtime pacing (see RELAY_* constants above): the frame interval
        # caps the send rate at 50/s; the ack window only backpressures a
        # genuinely stalled Tata leg and must NOT be the rate limiter.
        self.__max_pending_marks = max(1, max_pending_marks)
        self.__ack_wait_seconds = ack_wait_seconds
        self.__frame_interval = frame_interval_seconds
        self.__mark_every_n = max(1, mark_every_n_frames)
        self.__next_send_ts = 0.0

    # ── setup helpers ────────────────────────────────────────────────

    def ws_url(self, agent_id: str, ticket: str) -> str:
        return "{}/chat/v1/{}?token={}".format(self.__ws_base_url, agent_id, ticket)

    async def __mint_ticket(self) -> str:
        # Pooled client: a fresh AsyncClient per call pays a full TCP+TLS
        # handshake to the engine (~1.4s measured) on every call. Keep-alive
        # connections amortize that to a plain request (~0.2s).
        url = "{}/auth/ws-ticket".format(self.__api_base_url)
        client = await _pooled_http_client(self.__ticket_timeout)
        resp = await client.post(
            url, headers={"Authorization": "Bearer {}".format(self.__api_key)}
        )
        resp.raise_for_status()
        return resp.json()["ticket"]

    async def __connect_socket(self, url: str) -> "_AiohttpVoiceaiSocket":
        session = aiohttp.ClientSession()
        try:
            ws = await session.ws_connect(url, timeout=self.__connect_timeout)
        except Exception:
            await session.close()
            raise
        return _AiohttpVoiceaiSocket(session, ws)

    # ── main entry ───────────────────────────────────────────────────

    async def run(
        self,
        tata_ws,
        provider: TalkoAbstractPSTNProvider,
        ctx: TalkoCallContext,
        start_event: Dict[str, Any],
        raw_events,
        voiceai_agent_id: str,
    ) -> None:
        """Bridge one call. Returns when either leg ends."""
        sid = ctx.call_sid
        self.__logger.info(
            "[VOICEAI][RELAY] Starting sid={} agent={}".format(sid, voiceai_agent_id)
        )
        # Phase-0 latency spans (monotonic ms). first_media/first_send are
        # filled by the pump and reported in the timings line at Ended.
        t_run = time.monotonic()
        ticket = await self.__ticket_provider()
        t_ticket = time.monotonic()
        vws = await self.__ws_connector(self.ws_url(voiceai_agent_id, ticket))
        t_ws = time.monotonic()
        self.__logger.info("[VOICEAI][RELAY] voiceai socket open sid={}".format(sid))

        # Mark names voiceai asked Tata to ack — written by the outbound
        # pump, read by the inbound loop to route acks back to voiceai.
        # Set add/contains are GIL-atomic; ack routing is best-effort.
        voiceai_marks: Set[str] = set()
        # In-flight per-frame marks of our own (label -> ack event), in send
        # order. Bounds how far ahead of Tata's playout the pump may run —
        # without this the engine's bursts pile up in Tata's buffer and the
        # caller hears nothing (or everything minutes late).
        pending_marks: Dict[str, asyncio.Event] = {}
        # Wakes the pump's sender the moment an ack frees a pacing slot.
        pacing_wake = asyncio.Event()
        # Set when the Tata leg ended on its own (stop event) so the pump
        # doesn't redundantly close an already-dead Tata socket.
        tata_ended = False
        pump_stats: Dict[str, Any] = {}
        try:
            await self.__send_voiceai(vws, json.dumps(start_event), sid)
            pump = asyncio.create_task(
                self.__pump_voiceai_to_tata(
                    vws,
                    tata_ws,
                    provider,
                    ctx,
                    voiceai_marks,
                    pending_marks,
                    pacing_wake,
                    lambda: tata_ended,
                    t_ws,
                ),
                name="voiceai_out_{}".format(sid),
            )
            try:
                async for raw in raw_events:
                    try:
                        event = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    if provider.is_stop_event(event):
                        await self.__send_voiceai(vws, json.dumps(event), sid)
                        self.__logger.info(
                            "[VOICEAI][RELAY] Tata stop forwarded sid={}".format(sid)
                        )
                        tata_ended = True
                        break

                    if provider.is_mark_ack(event):
                        label = provider.get_mark_label(event)
                        if label.startswith(OWN_MARK_PREFIX):
                            # Ack for our own per-chunk mark — release the
                            # pacing slot and wake the sender; never
                            # grace-wait these (50/sec).
                            ev = pending_marks.pop(label, None)
                            if ev is not None:
                                ev.set()
                            pacing_wake.set()
                            continue
                        if label not in voiceai_marks:
                            # The pump may not have registered voiceai's mark
                            # yet (concurrent tasks) — brief grace period.
                            await self.__wait_for_mark(voiceai_marks, label)
                        if label in voiceai_marks:
                            # Ack for a mark voiceai itself requested —
                            # forward so its playout tracking completes.
                            # Discard: the mark may be acked twice (an early
                            # grace-wait hit plus Tata's real ack once the
                            # ordered mark is actually forwarded) and the
                            # engine must see each mark only once.
                            voiceai_marks.discard(label)
                            await self.__send_voiceai(vws, raw, sid)
                        # else: unknown mark, consume locally.
                        continue

                    translated = forward_to_voiceai(event)
                    if translated is not None:
                        await self.__send_voiceai(vws, translated, sid)
            finally:
                try:
                    # Unblock the pump's receive so it can drain and exit.
                    await vws.close()
                except Exception:
                    pass
                try:
                    pump_stats = await pump
                except Exception:
                    pump_stats = {}
        finally:
            try:
                await vws.close()
            except Exception:
                pass
            # TEMP DEBUG (silent-reply investigation): per-call audio flow —
            # voiceai_msgs/bytes + rms_* describe what the engine sent
            # (rms ~0 ⇒ engine sent silence); fwd_frames what Tata got.
            msgs = (pump_stats or {}).get("voiceai_msgs", 0)
            avg_rms = (
                (pump_stats or {}).get("rms_sum", 0) / msgs if msgs else 0
            )
            self.__logger.info(
                "[VOICEAI][RELAY] Ended sid={} stats={} avg_rms={:.0f}".format(
                    sid, pump_stats, avg_rms
                )
            )
            # Phase-0 latency spans: every number is ms since run() entry.
            # ticket/ws/first_media/first_send must sum to first audible
            # audio; any span dominating points at its owner (Talko ticket /
            # engine connect+gen / relay pacing / Tata playout).
            first_media = (pump_stats or {}).get("first_media_ms")
            first_send = (pump_stats or {}).get("first_send_ms")
            self.__logger.info(
                "[VOICEAI][RELAY] voiceai timings sid={} ticket_ms={:.0f} "
                "ws_ms={:.0f} first_media_ms={} first_send_ms={}".format(
                    sid,
                    (t_ticket - t_run) * 1000,
                    (t_ws - t_ticket) * 1000,
                    "{:.0f}".format(first_media)
                    if first_media is not None
                    else "none",
                    "{:.0f}".format(first_send)
                    if first_send is not None
                    else "none",
                )
            )

    # ── pumps ────────────────────────────────────────────────────────
    #
    # Reader and sender run as separate tasks sharing ONE ordered outbox.
    # Split deliberately: the sender blocks on pacing / Tata's ack window,
    # but voiceai control messages must be honoured promptly even when it
    # is blocked. A single task would stall behind a full window and
    # process controls seconds late.
    #
    # Ordering guarantee: voiceai's pre/post marks travel IN ORDER with
    # their audio (queued, not forwarded instantly). Tata sees each mark
    # adjacent to the audio it brackets — exactly like a Twilio-native
    # endpoint — instead of a pre-mark seconds ahead of its (paced) audio.
    #
    # Outbox item shapes: ("media", chunk_no, frame_bytes), ("clear",).
    # (Voiceai turn marks are acked locally, never queued — see reader.)

    async def __pump_voiceai_to_tata(
        self,
        vws,
        tata_ws,
        provider: TalkoAbstractPSTNProvider,
        ctx: TalkoCallContext,
        voiceai_marks: Set[str],
        pending_marks: Dict[str, asyncio.Event],
        wake: asyncio.Event,
        tata_ended: Callable[[], bool],
        t_origin: float = 0.0,
    ) -> Dict[str, Any]:
        """Forward agent audio / marks / clears to Tata. Ends on WS close.

        Returns TEMP DEBUG audio-flow stats (see ``stats`` below), logged by
        the caller in the Ended summary.
        """
        outbox: Deque[Tuple[Any, ...]] = collections.deque()
        finished = False  # reader drained the voiceai socket (nonlocal below)
        send_failed = False
        # TEMP DEBUG (silent-reply investigation): audio flow counters + RMS
        # energy of what voiceai actually sent. Logged in the Ended summary.
        stats = {
            "voiceai_msgs": 0,
            "voiceai_bytes": 0,
            "rms_min": None,
            "rms_max": 0,
            "rms_sum": 0,
            "fwd_frames": 0,
            "dropped_on_clear": 0,
        }

        async def reader() -> int:
            """voiceai socket -> outbox. Returns next chunk number to use."""
            nonlocal finished
            chunk = 0
            try:
                while True:
                    try:
                        data = await vws.receive_str()
                    except Exception as e:
                        self.__logger.warning(
                            "[VOICEAI][RELAY] voiceai recv failed sid={}: {}".format(
                                ctx.call_sid, e
                            )
                        )
                        break
                    if data is None:
                        break
                    kind, payload = parse_from_voiceai(data)
                    if kind == "media":
                        rms = _mulaw_rms(payload)
                        stats["voiceai_msgs"] += 1
                        if stats["voiceai_msgs"] == 1:
                            stats["first_media_ms"] = (
                                time.monotonic() - t_origin
                            ) * 1000
                        stats["voiceai_bytes"] += len(payload)
                        stats["rms_sum"] += rms
                        stats["rms_max"] = max(stats["rms_max"], rms)
                        if stats["rms_min"] is None or rms < stats["rms_min"]:
                            stats["rms_min"] = rms
                        # TEMP DEBUG: per-message energy+size+head-bytes. The
                        # aggregate avg hides bimodal distributions (loud
                        # greeting + silent replies). ~26 msgs/call: cheap to
                        # log all. Speech RMS reads in the hundreds-thousands;
                        # ~0 = silence. Head bytes distinguish μ-law speech
                        # from mis-encoded audio (PCM-as-μ-law shows runs of
                        # 0x00/0xFF every other byte).
                        self.__logger.info(
                            "[VOICEAI][RELAY] voiceai audio sid={} msg={} bytes={} rms={} head={}".format(
                                ctx.call_sid,
                                stats["voiceai_msgs"],
                                len(payload),
                                rms,
                                payload[:16].hex(),
                            )
                        )
                        for frame in _split_frames(payload):
                            chunk += 1
                            outbox.append(("media", chunk, frame))
                        wake.set()
                    elif kind == "mark":
                        # TEMP DEBUG (silent-reply diagnosis): do NOT forward
                        # voiceai's turn-boundary marks to Tata — ack them
                        # locally instead. Tata's docs frame marks as
                        # end-of-input signaling; if its gateway gates
                        # playout on turn marks, the greeting's post-mark
                        # would arm "turn over" and mute all replies while
                        # acks keep flowing — exactly our symptom. Holler
                        # sends no turn marks (chunk marks only) and plays
                        # fine, so Tata here sees holler-shaped traffic.
                        # Engine tracking stays green via the instant local
                        # ack (delay≈0, which the engine already tolerates).
                        await self.__send_voiceai(
                            vws,
                            json.dumps(
                                {
                                    "event": "mark",
                                    "streamSid": ctx.stream_sid,
                                    "mark": {"name": payload},
                                }
                            ),
                            ctx.call_sid,
                        )
                    elif kind == "clear":
                        # Barge-in: release pacing slots at once (their acks
                        # will never arrive) and drop queued-but-unsent items
                        # — the stale reply tail. The drop happens HERE, at
                        # arrival, so only pre-clear items go; anything the
                        # engine sends after stays queued behind the clear
                        # marker the sender forwards next, in order.
                        dropped = len(outbox)
                        outbox.clear()
                        stats["dropped_on_clear"] += dropped
                        for ev in pending_marks.values():
                            ev.set()
                        pending_marks.clear()
                        outbox.append(("clear",))
                        self.__logger.info(
                            "[VOICEAI][RELAY] clear queued sid={} dropped_queued={}".format(
                                ctx.call_sid, dropped
                            )
                        )
                        wake.set()
            finally:
                finished = True
                wake.set()
            return chunk

        async def sender() -> None:
            """Outbox -> Tata at realtime rate, ack window as backpressure.

            Items flow in arrival order: media frames (paced), voiceai marks
            (forwarded where they sit — adjacent to their audio), clears
            (forwarded, buffer already dropped at arrival). Only media is
            gated on the ack window; control items always flow so a full
            window can never trap a clear behind unsent audio.
            """
            nonlocal send_failed
            while True:
                wake.clear()
                # No await between clear() and these checks, so no wake-up
                # can interleave and get lost.
                while outbox:
                    kind = outbox[0][0]
                    if kind == "media" and len(pending_marks) >= self.__max_pending_marks:
                        break  # backpressure gates audio only, never control
                    item = outbox.popleft()
                    if item[0] == "media":
                        _, chunk_no, frame = item
                        await self.__pace_frame()
                        # Mark sparsely: Tata's mark path handles only a few
                        # marks/s, so a mark per frame would flood it (see
                        # RELAY_* constants). Frame 1 is always marked.
                        if (chunk_no - 1) % self.__mark_every_n == 0:
                            label: Optional[str] = "{}-{}".format(
                                OWN_MARK_PREFIX.rstrip("-"), chunk_no
                            )
                            pending_marks[label] = asyncio.Event()
                        else:
                            label = None
                        try:
                            await provider.send_audio(
                                tata_ws,
                                frame,
                                label=label,
                                stream_sid=ctx.stream_sid,
                                chunk=chunk_no,
                            )
                            stats["fwd_frames"] += 1
                            if stats["fwd_frames"] == 1:
                                stats["first_send_ms"] = (
                                    time.monotonic() - t_origin
                                ) * 1000
                        except Exception:
                            if label is not None:
                                pending_marks.pop(label, None)
                            raise
                    elif item[0] == "clear":
                        await provider.send_clear(
                            tata_ws, stream_sid=ctx.stream_sid
                        )
                        self.__logger.info(
                            "[VOICEAI][RELAY] clear forwarded sid={}".format(
                                ctx.call_sid
                            )
                        )
                if finished and not outbox:
                    break
                try:
                    await asyncio.wait_for(
                        wake.wait(), timeout=self.__ack_wait_seconds
                    )
                    timed_out = False
                except asyncio.TimeoutError:
                    timed_out = True
                wake.clear()
                if (
                    timed_out
                    and outbox
                    and len(pending_marks) >= self.__max_pending_marks
                ):
                    # Acks for wiped/lost frames never arrive — drop the
                    # oldest slot so one lost ack can't stall the call
                    # (same tradeoff as the LiveKit path in services.py).
                    oldest_label = next(iter(pending_marks))
                    if pending_marks.pop(oldest_label, None) is not None:
                        self.__logger.warning(
                            "[VOICEAI][RELAY] Ack timeout label={} pending={} sid={}".format(
                                oldest_label, len(pending_marks), ctx.call_sid
                            )
                        )

        reader_task = asyncio.create_task(reader(), name="voiceai_in_{}".format(ctx.call_sid))
        try:
            await sender()
        except Exception as e:
            send_failed = True
            self.__logger.warning(
                "[VOICEAI][RELAY] Tata send failed sid={}: {}".format(ctx.call_sid, e)
            )
        finally:
            if not reader_task.done():
                reader_task.cancel()
                try:
                    await reader_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
        if not tata_ended() and not send_failed:
            # voiceai closed first (agent hangup) — end the Tata leg.
            self.__logger.info(
                "[VOICEAI][RELAY] voiceai socket closed sid={} — "
                "closing Tata leg".format(ctx.call_sid)
            )
            try:
                await tata_ws.close()
            except Exception:
                pass
        return stats

    async def __pace_frame(self) -> None:
        """Cap outbound audio at realtime rate (1 frame per 20 ms).

        The engine emits bursts; Tata plays 50 frames/s. Without this cap
        the ack window alone sets the rate (window/latency ≈ 12/s observed),
        starving Tata's playout. Re-anchored every frame so wake-ups and
        ack waits can't accumulate drift.
        """
        now = time.monotonic()
        delay = self.__next_send_ts - now
        if delay > 0:
            await asyncio.sleep(delay)
            now = time.monotonic()
        self.__next_send_ts = now + self.__frame_interval

    async def __wait_for_mark(self, voiceai_marks: Set[str], label: str) -> None:
        """Brief grace period for the pump to register voiceai's mark."""
        for _ in range(20):  # ~200ms total
            if label in voiceai_marks:
                return
            await asyncio.sleep(0.01)

    async def __send_voiceai(self, vws, data: str, sid: str) -> None:
        await asyncio.wait_for(vws.send_str(data), timeout=SEND_TIMEOUT_SECONDS)

    async def __send_tata(self, tata_ws, data: str, sid: str) -> None:
        await asyncio.wait_for(tata_ws.send_text(data), timeout=SEND_TIMEOUT_SECONDS)


class _AiohttpVoiceaiSocket:
    """Minimal send/receive/close adapter over an aiohttp client WebSocket."""

    def __init__(self, session: aiohttp.ClientSession, ws) -> None:
        self.__session = session
        self.__ws = ws

    async def send_str(self, data: str) -> None:
        await self.__ws.send_str(data)

    async def receive_str(self) -> Optional[str]:
        """Next TEXT frame, or None when the socket closed."""
        msg = await self.__ws.receive()
        if msg.type == aiohttp.WSMsgType.TEXT:
            return msg.data
        # voiceai never sends binary frames; anything else means closed/closing.
        return None

    async def close(self) -> None:
        try:
            await self.__ws.close()
        finally:
            await self.__session.close()
