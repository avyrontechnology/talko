from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel

from src.components.pstn.constants import CallDirection, PSTNProvider


@dataclass
class CallContext:
    """Normalized call metadata passed between service layers during a live call."""

    provider: PSTNProvider
    call_sid: str
    did_number: str
    caller_number: str
    direction: CallDirection
    stream_sid: str = ""
    context_data: Optional[Dict[str, Any]] = None
    pending_context_found: bool = False
    # Filled after DID lookup
    makunai_agent_id: Optional[int] = None
    partner_id: Optional[int] = None
    vendor_config_id: Optional[str] = None
    # Filled after Session API call
    livekit_url: Optional[str] = None
    caller_token: Optional[str] = None
    room_name: Optional[str] = None
    # Filled after recording starts
    egress_id: Optional[str] = None
    vendor_call_id: Optional[str] = None


# API Request / Response Schemas


class CreatePSTNAgentConfigRequest(BaseModel):
    did_number: str
    makunai_agent_id: int
    partner_id: int
    phone_number_id: str  # ObjectId as string from API
    vendor_config_id: str
    provider: str = "tata_tele"
    language: Optional[str] = None
    welcome_message: Optional[str] = None


class PSTNAgentConfigResponse(BaseModel):
    id: str
    did_number: str
    makunai_agent_id: int
    partner_id: int
    provider: str
    is_active: bool
    language: Optional[str] = None
    welcome_message: Optional[str] = None


class CallContextResponse(BaseModel):
    """For logging/debugging active calls via admin API."""

    call_sid: str
    did_number: str
    caller_number: str
    provider: str
    room_name: Optional[str] = None
    makunai_agent_id: Optional[int] = None
    partner_id: Optional[int] = None
