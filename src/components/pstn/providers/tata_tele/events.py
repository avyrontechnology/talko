import base64
import json


class TalkoTataTeleEvents:
    """
    Tata Tele SmartFlo WebSocket event builder and parser.

    Inbound events (Tata → us):
        - connected : WebSocket handshake established
        - start     : Call metadata — callSid, streamSid, from/to, direction
        - media     : Inbound audio chunk (μ-law 8kHz, base64-encoded payload)
        - mark      : Playback acknowledgement for a previously sent mark label
        - clear     : Barge-in signal — flush pending outbound audio buffer
        - stop      : Call ended

    Outbound events (us → Tata):
        - media     : Outbound audio chunk (μ-law 8kHz, base64-encoded payload)
                      MUST include streamSid and media.chunk counter.
        - mark      : Request playback acknowledgement after an audio chunk.
                      MUST include streamSid.
        - clear     : Instruct Tata to flush its outbound audio buffer.
                      MUST include streamSid.

    Important:
        streamSid (format: MZXXX...) is distinct from callSid (format: CAXX...).
        streamSid is extracted from start.streamSid and MUST be echoed back
        in every outbound event. Without it, Tata silently discards the event.
    """

    @staticmethod
    def parse_start(event: dict) -> dict:
        """
        Parse a Tata Tele 'start' event into a normalised dict.

        Direction semantics:
            inbound  — customer dialled our DID; DID is s["to"]
            outbound — we dialled the customer; DID is s["from"] (our caller-id)

        Returns:
            {
                "call_sid":      str  — unique call identifier  (CAXX...)
                "stream_sid":    str  — unique stream identifier (MZXX...)
                "did_number":    str  — our DID number
                "caller_number": str  — customer's phone number
                "direction":     str  — "inbound" | "outbound"
            }
        """
        s = event["start"]
        direction = s.get("direction", "inbound")

        # Inbound:  DID is "to"   — the number the customer dialled
        # Outbound: DID is "from" — the caller_id (DID) we used to dial
        did_number = s["to"] if direction == "inbound" else s["from"]

        return {
            "call_sid": s["callSid"],
            "stream_sid": s["streamSid"],
            "did_number": did_number,
            "caller_number": s["from"],
            "direction": direction,
        }

    @staticmethod
    def build_media(audio_bytes: bytes, stream_sid: str, chunk: int) -> str:
        """
        Build an outbound media event carrying one μ-law 8kHz audio chunk.

        Args:
            audio_bytes: Raw μ-law 8kHz bytes (160 bytes = 20 ms standard chunk).
            stream_sid:  streamSid from the start event (MZXX...).
                         Required by Tata — omitting causes silent discard.
            chunk:       Monotonically increasing chunk counter starting at 1.
                         Required by Tata for sequencing.

        Returns:
            JSON string ready to send over the WebSocket.
        """
        return json.dumps(
            {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": base64.b64encode(audio_bytes).decode(),
                    "chunk": chunk,
                },
            }
        )

    @staticmethod
    def build_mark(label: str, stream_sid: str) -> str:
        """
        Build an outbound mark event to request a playback acknowledgement.

        Tata echoes this back as an inbound mark event once the corresponding
        audio chunk has finished playing, enabling barge-in / turn-taking logic.

        Args:
            label:      Unique label for this mark (e.g. "chunk_000001").
            stream_sid: streamSid from the start event. Required by Tata.

        Returns:
            JSON string ready to send over the WebSocket.
        """
        return json.dumps(
            {
                "event": "mark",
                "streamSid": stream_sid,
                "mark": {"name": label},
            }
        )

    @staticmethod
    def build_clear(stream_sid: str) -> str:
        """
        Build an outbound clear event to flush Tata's outbound audio buffer.

        Sent when a barge-in (clear inbound event) is received to stop
        the currently playing agent audio on the caller's end.

        Args:
            stream_sid: streamSid from the start event. Required by Tata.

        Returns:
            JSON string ready to send over the WebSocket.
        """
        return json.dumps(
            {
                "event": "clear",
                "streamSid": stream_sid,
            }
        )

    @staticmethod
    def build_connected_ack() -> str:
        """
        Build the connected acknowledgement sent after the WebSocket handshake.

        Returns:
            JSON string ready to send over the WebSocket.
        """
        return json.dumps({"event": "connected"})
