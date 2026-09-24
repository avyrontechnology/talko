from typing import Literal, Optional

from pydantic import BaseModel


class TalkoContract:
    class DidDefaultAttendanceCreate(BaseModel):
        workspace_id: int
        did_number: str
        partner_id: int
        vendor_id: str
        agent_id: int | None = None
        assign_date: int | None = None
        mapped_date: int | None = None

    class DidHistoryCreate(BaseModel):
        did_number: str
        partner_id: int
        vendor_id: str
        agent_id: int | None = None
        assign_date: int
        unassign_date: int | None = None
        workspace_id: int | None = None

    class DIDResponse(BaseModel):
        workspace_id: int
        did_number: str
        partner_id: int
        vendor_id: str
        agent_id: int | None = None
        assign_date: int | None = None
        unassign_date: int | None = None
        display_name: str | None = None

    class DIDDetail(BaseModel):
        number: str
        instance_id: str | None = None

    class DIDSeriesResponse(BaseModel):
        series: str
        dids: list["TalkoContract.DIDDetail"]
        count: int

    class WorkspaceDIDMapping(BaseModel):
        workspace_id: int
        did_numbers: list[str]

    class AssignDIDToPartner(BaseModel):
        dids_for_workspace: list["TalkoContract.WorkspaceDIDMapping"] | None = None
        dids_for_agent_mapping: list[dict[str, str]] | None = None
        dids_for_round_robin: list[str] | None = None

    class UnassignDIDRequest(BaseModel):
        did_numbers: list[str]

    class AdminDIDAction(BaseModel):
        did_numbers: list[str]
        action: Literal["set_available", "set_mapped", "mark_cooling_period"]
        workspace_id: int | None = None
        agent_id: int | None = None

    class AdminDIDActionResponse(BaseModel):
        summary: "TalkoContract.AdminDIDActionSummary"
        results: list["TalkoContract.AdminDIDActionResult"]

    class DIDListItem(BaseModel):
        did_number: str
        status: str
        partner_id: int
        workspace_id: int | None = None
        agent_id: int | None = None
        vendor_id: str  # as string for response
        spam_count: int = 0
        last_spam_detected_at: int | None = None
        cooldown_until: int | None = None
        status_changed_at: int
        assign_date: int | None = None
        mapped_date: int | None = None
        did_layer: str | None = "external"
        parent_did_number: str | None = None

    class DIDListResponse(BaseModel):
        total: int
        page: int
        limit: int
        dids: list["TalkoContract.DIDListItem"]

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
        data: list["TalkoContract.StatusTransition"]
        # optional extra info
        metadata: dict = {}

    class AssignAIAgentDIDRequest(BaseModel):
        partner_id: int
        # Optional: 0 / omitted means VoiceAI/engine-routed (partner-only).
        # Talko stores did_number -> partner_id with agent_bot_id=0; the agent
        # lives in the engine Numbers UI and is resolved per call. makun-ai
        # campaign flows still pass a real agent_bot_id here.
        agent_bot_id: int | None = 0
        did_number: str | None = None  # auto-pick first available

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

    class ExternalDIDImportRequest(BaseModel):
        vendor_id: str
        vendor_config_id: str | None = None
        did_numbers: list[str]
        display_name: str | None = None

    class InternalDIDProvisionRequest(BaseModel):
        parent_did_number: str
        partner_id: int
        workspace_id: int | None = None
        agent_id: int | None = None
        vendor_config_id: str | None = None

    class MapExternalInternalRequest(BaseModel):
        external_did_number: str
        internal_did_number: str
        partner_id: int

    class PoolUtilizationItem(BaseModel):
        did_layer: str
        status: str
        count: int
