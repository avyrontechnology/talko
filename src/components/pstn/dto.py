from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from src.components.pstn.constants import TalkoCallDirection, TalkoPSTNProvider


@dataclass
class TalkoCallContext:
    """Normalized call metadata passed between service layers during a live call."""

    provider: TalkoPSTNProvider
    call_sid: str
    did_number: str
    caller_number: str
    direction: TalkoCallDirection
    stream_sid: str = ""
    context_data: dict[str, Any] | None = None
    pending_context_found: bool = False
    # Filled after DID lookup
    makunai_agent_id: int | None = None
    partner_id: int | None = None
    vendor_config_id: str | None = None
    # VoiceAI DID agent resolved in Step 2 (Redis-cached engine lookup).
    # Cached here so the fast-path / outbound fast-path / Step 4b / session
    # skip don't each pay another Redis round trip for the same DID.
    voiceai_agent_id: str | None = None
    # Filled after Session API call
    livekit_url: str | None = None
    caller_token: str | None = None
    room_name: str | None = None
    # Filled after recording starts
    egress_id: str | None = None
    vendor_call_id: str | None = None


# API Request / Response Schemas


class TalkoCreatePSTNAgentConfigRequest(BaseModel):
    did_number: str
    makunai_agent_id: int
    partner_id: int
    phone_number_id: str  # ObjectId as string from API
    vendor_config_id: str
    provider: str = "tata_tele"
    language: str | None = None
    welcome_message: str | None = None


class TalkoPSTNAgentConfigResponse(BaseModel):
    id: str
    did_number: str
    makunai_agent_id: int
    partner_id: int
    provider: str
    is_active: bool
    language: str | None = None
    welcome_message: str | None = None


class TalkoCallContextResponse(BaseModel):
    """For logging/debugging active calls via admin API."""

    call_sid: str
    did_number: str
    caller_number: str
    provider: str
    room_name: str | None = None
    makunai_agent_id: int | None = None
    partner_id: int | None = None
