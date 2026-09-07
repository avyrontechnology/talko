"""Tata Tele <-> voiceai media-event translation.

Talko stays the WebSocket endpoint for Tata Tele; for voiceai-routed calls
the media is relayed to voiceai's ``/chat/v1/{agent_id}`` socket, whose
Twilio-compatibility input handler (``TwilioInputHandler``) expects
Twilio Media Streams shaped events.

Tata's protocol is already ~Twilio-shaped with two gaps this module closes:

1. Tata ``media`` events carry ``media.chunk`` but no ``media.timestamp`` —
   voiceai does ``int(media["timestamp"])`` unconditionally, so a missing
   field would kill the stream. We inject ``timestamp`` derived from the
   chunk counter (20 ms per chunk).
2. Tata ``connected``/``clear`` events have no voiceai consumer and are
   dropped on the Tata -> voiceai leg (barge-in flows the other way:
   voiceai ``clear`` -> Tata ``send_clear``).

Reverse leg (voiceai -> Tata) normalises to ``(kind, payload)`` tuples the
relay sends via the provider interface; Tata mark names are preserved
verbatim so voiceai's playout-ack tracking keeps working.
"""

import base64
import copy
import json
from typing import Any, Dict, Optional, Tuple

# 20 ms of mulaw @ 8kHz per chunk — matches Tata's chunk counter semantics.
CHUNK_DURATION_MS = 20


def forward_to_voiceai(event: Dict[str, Any], chunk_hint: int = 0) -> Optional[str]:
    """Translate one Tata-side event into a voiceai WS text frame.

    Returns the JSON string to send, or None when the event has no
    voiceai consumer and must be dropped.

    Args:
        event: Parsed Tata event dict (``{"event": ..., ...}``).
        chunk_hint: Fallback timestamp base (ms) when the event carries
            neither ``media.timestamp`` nor ``media.chunk``.
    """
    etype = event.get("event")

    if etype == "start":
        # Tata start already has start.callSid / start.streamSid, exactly
        # what TwilioInputHandler.call_start reads. Forward verbatim.
        return json.dumps(event)

    if etype == "media":
        out = copy.deepcopy(event)
        media = out.setdefault("media", {})
        if "timestamp" not in media:
            chunk = media.get("chunk")
            if isinstance(chunk, int):
                media["timestamp"] = chunk * CHUNK_DURATION_MS
            else:
                media["timestamp"] = chunk_hint
        return json.dumps(out)

    if etype == "mark":
        # Tata mark acks are {event: mark, streamSid, mark: {name}} —
        # identical to Twilio, forwarded verbatim.
        return json.dumps(event)

    if etype == "stop":
        return json.dumps(event)

    if etype == "dtmf":
        return json.dumps(event)

    # "connected" acks and Tata barge-in "clear" have no voiceai consumer.
    return None


def parse_from_voiceai(raw: str) -> Tuple[Optional[str], Any]:
    """Parse one voiceai WS text frame into a (kind, payload) action.

    Returns:
        ("media", bytes)  — mulaw 8kHz audio to play to the caller.
        ("mark", str)     — mark name: request a Tata playout-ack with the
                            SAME name so voiceai's ack tracking works.
        ("clear", None)   — barge-in: flush Tata's outbound buffer.
        (None, None)      — ignore (unknown / housekeeping frames).
    """
    try:
        event = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, None

    etype = event.get("event")
    if etype == "media":
        try:
            return "media", base64.b64decode(event["media"]["payload"])
        except (KeyError, TypeError, ValueError):
            return None, None
    if etype == "mark":
        name = event.get("mark", {}).get("name", "")
        return ("mark", name) if name else (None, None)
    if etype == "clear":
        return "clear", None
    return None, None
