from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class TalkoContract:
    class DidDefaultAttendanceCreate(BaseModel):
        service_board_id: int
        did_number: str
        partner_id: int
        vendor_id: str
        agent_id: Optional[int] = None
        assign_date: Optional[int] = None
        mapped_date: Optional[int] = None

    class DidHistoryCreate(BaseModel):
        did_number: str
        partner_id: int
        vendor_id: str
        agent_id: Optional[int] = None
        assign_date: int
        unassign_date: Optional[int] = None
        service_board_id: Optional[int] = None

    class DIDResponse(BaseModel):
        service_board_id: int
        did_number: str
        partner_id: int
        vendor_id: str
        agent_id: Optional[int] = None
        assign_date: Optional[int] = None
        unassign_date: Optional[int] = None
        display_name: Optional[str] = None

    class DIDDetail(BaseModel):
        number: str
        instance_id: Optional[str] = None

    class DIDSeriesResponse(BaseModel):
        series: str
        dids: List["TalkoContract.DIDDetail"]
        count: int

    class ServiceBoardDIDMapping(BaseModel):
        service_board_id: int
        did_numbers: List[str]

    class AssignDIDToPartner(BaseModel):
        dids_for_service_board: Optional[List["TalkoContract.ServiceBoardDIDMapping"]] = None
        dids_for_agent_mapping: Optional[List[Dict[str, str]]] = None
        dids_for_round_robin: Optional[List[str]] = None

    class UnassignDIDRequest(BaseModel):
        did_numbers: List[str]

    class AdminDIDAction(BaseModel):
        did_numbers: List[str]
        action: Literal["set_available", "set_mapped", "mark_cooling_period"]
        service_board_id: Optional[int] = None
        agent_id: Optional[int] = None

    class AdminDIDActionResponse(BaseModel):
        summary: "TalkoContract.AdminDIDActionSummary"
        results: List["TalkoContract.AdminDIDActionResult"]

    class DIDListItem(BaseModel):
        did_number: str
        status: str
        partner_id: int
        service_board_id: Optional[int] = None
        agent_id: Optional[int] = None
        vendor_id: str  # as string for response
        spam_count: int = 0
        last_spam_detected_at: Optional[int] = None
        cooldown_until: Optional[int] = None
        status_changed_at: int
        assign_date: Optional[int] = None
        mapped_date: Optional[int] = None

    class DIDListResponse(BaseModel):
        total: int
        page: int
        limit: int
        dids: List["TalkoContract.DIDListItem"]

    class ErrorDetail(BaseModel):
        code: str
        message: str

    class AdminDIDActionResult(BaseModel):
        did_number: str
        success: bool
        status: str  # "updated" | "skipped"
        error: Optional["TalkoContract.ErrorDetail"] = None

    class AdminDIDActionSummary(BaseModel):
        total: int
        succeeded: int
        failed: int

    class StatusTransition(BaseModel):
        status: str
        next_eligible_status: list

    class StatusMetadataResponse(BaseModel):
        status: str = "success"
        message: str = "DID status workflow"
        data: List["TalkoContract.StatusTransition"]
        # optional extra info
        metadata: Dict = {}

    class AssignAIAgentDIDRequest(BaseModel):
        partner_id: int
        agent_bot_id: int
        did_number: Optional[str] = None  # auto-pick first available

    class ReleaseAIAgentDIDRequest(BaseModel):
        partner_id: int
        agent_bot_id: int

    class ClaimCampaignDIDRequest(BaseModel):
        partner_id: int
        did_number: str
        agent_bot_id: int

    class ReleaseCampaignDIDRequest(BaseModel):
        partner_id: int
        did_number: str
        agent_bot_id: int
