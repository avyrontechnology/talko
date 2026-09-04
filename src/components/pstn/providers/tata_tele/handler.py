import base64

from src.components.pstn.constants import CallDirection, PSTNProvider
from src.components.pstn.dto import CallContext
from src.components.pstn.providers.base import AbstractPSTNProvider
from src.components.pstn.providers.tata_tele.events import TataTeleEvents


class TataTeleProvider(AbstractPSTNProvider):
    """
    Tata Tele SmartFlo PSTN provider implementation.

    Implements AbstractPSTNProvider for the Tata SmartFlo bi-directional
    audio streaming WebSocket protocol.

    Key protocol requirements (from Tata SmartFlo docs):
        - Every outbound event (media, mark, clear) MUST include streamSid.
        - streamSid comes from start.streamSid (MZXX...), not callSid (CAXX...).
        - Outbound media events MUST include a monotonically increasing chunk counter.
        - Audio format: μ-law 8kHz mono, 160 bytes per chunk (20 ms), base64-encoded.
        - Inbound audio format: identical — μ-law 8kHz mono, base64-encoded.
    """

    async def parse_start_event(self, raw_event: dict) -> CallContext:
        """
        Parse a Tata Tele 'start' WebSocket event into a CallContext.

        Extracts callSid, streamSid, DID, caller number, and direction
        from the event payload. streamSid is required for all subsequent
        outbound events on this call.

        Args:
            raw_event: Raw parsed JSON dict of the start event from Tata.

        Returns:
            Populated CallContext with provider, call_sid, stream_sid,
            did_number, caller_number, and direction set.
        """
        parsed = TataTeleEvents.parse_start(raw_event)
        return CallContext(
            provider=PSTNProvider.TATA_TELE,
            call_sid=parsed["call_sid"],
            stream_sid=parsed["stream_sid"],
            did_number=parsed["did_number"],
            caller_number=parsed["caller_number"],
            direction=CallDirection(parsed["direction"]),
        )

    async def send_audio(
        self,
        ws,
        audio_bytes: bytes,
        label: str,
        stream_sid: str = "",
        chunk: int = 1,
    ) -> None:
        """
        Send one μ-law audio chunk followed by a mark event to Tata.

        The media event carries the audio payload. The mark event requests
        a playback acknowledgement, which Tata echoes back once the audio
        has finished playing — used for barge-in / turn-taking.

        Args:
            ws:          WebSocket connection to Tata.
            audio_bytes: 160 bytes of μ-law 8kHz audio (20 ms per chunk).
            label:       Unique mark label for this chunk (e.g. "chunk_000001").
            stream_sid:  streamSid from the start event. Required by Tata.
            chunk:       Monotonically increasing chunk counter. Required by Tata.
        """
        await ws.send_text(TataTeleEvents.build_media(audio_bytes, stream_sid, chunk))
        await ws.send_text(TataTeleEvents.build_mark(label, stream_sid))

    async def send_clear(self, ws, stream_sid: str = "") -> None:
        """
        Send a clear event to flush Tata's outbound audio buffer.

        Called when a barge-in (inbound clear event) is received to
        immediately stop playback of the current agent audio on the caller's end.

        Args:
            ws:         WebSocket connection to Tata.
            stream_sid: streamSid from the start event. Required by Tata.
        """
        await ws.send_text(TataTeleEvents.build_clear(stream_sid))

    def is_media_event(self, event: dict) -> bool:
        """Return True if the event carries inbound audio from the caller."""
        return event.get("event") == "media"

    def get_audio_payload(self, event: dict) -> bytes:
        """
        Decode base64 μ-law audio payload from an inbound media event.

        Args:
            event: Parsed media event dict from Tata.

        Returns:
            Raw μ-law 8kHz bytes.
        """
        return base64.b64decode(event["media"]["payload"])

    def is_stop_event(self, event: dict) -> bool:
        """Return True if the event signals call termination."""
        return event.get("event") == "stop"

    def get_stop_reason(self, event: dict) -> str:
        """
        Extract the stop reason from a stop event.

        Args:
            event: Parsed stop event dict from Tata.

        Returns:
            Reason string, or "unknown" if not present.
        """
        return event.get("stop", {}).get("reason", "unknown")

    def is_mark_ack(self, event: dict) -> bool:
        """Return True if the event is a playback acknowledgement for a mark."""
        return event.get("event") == "mark"

    def get_mark_label(self, event: dict) -> str:
        """
        Extract the mark label from an inbound mark acknowledgement event.

        Args:
            event: Parsed mark event dict from Tata.

        Returns:
            Label string matching the one sent in the outbound mark event.
        """
        return event.get("mark", {}).get("name", "")
