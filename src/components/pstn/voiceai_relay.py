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
import collections
import json
from typing import Any, Awaitable, Callable, Deque, Dict, Optional, Set, Tuple

import aiohttp
import httpx

from src.components.pstn.dto import TalkoCallContext
from src.components.pstn.providers.base import TalkoAbstractPSTNProvider
from src.components.pstn.voiceai_events import forward_to_voiceai, parse_from_voiceai
from src.core.redis_constants import ACK_WAIT_SECONDS, MAX_PENDING_MARKS

VOICEAI_AGENT_ID_KEY = "voiceai_agent_id"
SEND_TIMEOUT_SECONDS = 5.0
# Prefix for the relay's own per-chunk marks (see __pump_voiceai_to_tata).
# Acks carrying this prefix are consumed immediately WITHOUT the grace wait:
# waiting 200ms on every one of Tata's ~50 acks/sec would stall inbound audio.
OWN_MARK_PREFIX = "voiceai-chunk-"
# Tata's audio contract (see TalkoAbstractPSTNProvider): exactly 160 bytes of
# μ-law 8kHz per media event (20 ms). voiceai emits larger per-message blobs
# (hundreds of ms of audio); forwarding those 1:1 breaks Tata's playout
# (buffer bloat, growing ack lag, garbled/silent audio), so split them here.
# Short final frames are padded with μ-law silence (0xFF).
TATA_FRAME_BYTES = 160
_MULAW_SILENCE = b"\xff"


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
        max_pending_marks: int = MAX_PENDING_MARKS,
        ack_wait_seconds: float = ACK_WAIT_SECONDS,
    ) -> None:
        self.__ws_base_url = ws_base_url.rstrip("/")
        self.__api_base_url = api_base_url.rstrip("/")
        self.__api_key = api_key
        self.__logger = logger
        self.__ticket_timeout = ticket_timeout_seconds
        self.__connect_timeout = connect_timeout_seconds
        self.__ticket_provider = ticket_provider or self.__mint_ticket
        self.__ws_connector = ws_connector or self.__connect_socket
        # Realtime pacing window (mirrors the LiveKit path in services.py):
        # at most this many 20ms frames in flight toward Tata; the pump
        # waits for the oldest ack before sending more.
        self.__max_pending_marks = max(1, max_pending_marks)
        self.__ack_wait_seconds = ack_wait_seconds

    # ── setup helpers ────────────────────────────────────────────────

    def ws_url(self, agent_id: str, ticket: str) -> str:
        return "{}/chat/v1/{}?token={}".format(self.__ws_base_url, agent_id, ticket)

    async def __mint_ticket(self) -> str:
        url = "{}/auth/ws-ticket".format(self.__api_base_url)
        async with httpx.AsyncClient(timeout=self.__ticket_timeout) as client:
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
        ticket = await self.__ticket_provider()
        vws = await self.__ws_connector(self.ws_url(voiceai_agent_id, ticket))
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
                await pump
        finally:
            try:
                await vws.close()
            except Exception:
                pass
            self.__logger.info("[VOICEAI][RELAY] Ended sid={}".format(sid))

    # ── pumps ────────────────────────────────────────────────────────
    #
    # Reader and sender run as separate tasks sharing an outbox queue.
    # Split deliberately: the sender blocks on Tata's ack window (realtime
    # pacing), but voiceai control messages — especially barge-in ``clear``
    # — must be honoured immediately even when the window is full. A single
    # task would stall behind a full window and process the clear seconds
    # late, after Tata already buffered (and then wipes) the reply.

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
    ) -> None:
        """Forward agent audio / marks / clears to Tata. Ends on WS close."""
        outbox: Deque[Tuple[int, bytes]] = collections.deque()
        finished = False  # reader drained the voiceai socket (nonlocal below)
        send_failed = False

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
                        for frame in _split_frames(payload):
                            chunk += 1
                            outbox.append((chunk, frame))
                        wake.set()
                    elif kind == "mark":
                        voiceai_marks.add(payload)
                        await self.__send_tata(
                            tata_ws,
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
                        # Barge-in: Tata wipes its playout buffer, so drop
                        # anything queued-but-unsent (stale reply tail) and
                        # release pacing slots whose acks will never arrive.
                        dropped = len(outbox)
                        outbox.clear()
                        for ev in pending_marks.values():
                            ev.set()
                        pending_marks.clear()
                        await provider.send_clear(
                            tata_ws, stream_sid=ctx.stream_sid
                        )
                        self.__logger.info(
                            "[VOICEAI][RELAY] clear forwarded sid={} dropped_queued={}".format(
                                ctx.call_sid, dropped
                            )
                        )
                        wake.set()
            finally:
                finished = True
                wake.set()
            return chunk

        async def sender() -> None:
            """Outbox -> Tata, paced by Tata's ack window (realtime rate)."""
            nonlocal send_failed
            while True:
                wake.clear()
                # No await between clear() and these checks, so no wake-up
                # can interleave and get lost.
                while outbox and len(pending_marks) < self.__max_pending_marks:
                    chunk_no, frame = outbox.popleft()
                    label = "{}-{}".format(OWN_MARK_PREFIX.rstrip("-"), chunk_no)
                    pending_marks[label] = asyncio.Event()
                    try:
                        await provider.send_audio(
                            tata_ws,
                            frame,
                            label=label,
                            stream_sid=ctx.stream_sid,
                            chunk=chunk_no,
                        )
                    except Exception:
                        pending_marks.pop(label, None)
                        raise
                if finished and not outbox:
                    break
                try:
                    await asyncio.wait_for(
                        wake.wait(), timeout=self.__ack_wait_seconds
                    )
                except asyncio.TimeoutError:
                    pass
                wake.clear()
                if outbox and len(pending_marks) >= self.__max_pending_marks:
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
