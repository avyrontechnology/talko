from bson import ObjectId
from pydantic import ConfigDict, Field, model_validator

from src.components.did_management.constants import (
    TalkoDIDLayer,
    TalkoDIDStatus,
    TalkoDIDType,
)
from src.utils.datetime_util import TalkoDateTimeUtil
from src.utils.timestamped_model import TalkoTimestampedModel


def _is_set(value) -> bool:
    """Treat None and 0 as unset (legacy docs use 0 for 'no agent')."""
    return value is not None and value != 0


class TalkoPhoneNumberManagement(TalkoTimestampedModel):
    workspace_id: int  # Workspace identifier
    did_number: str  # DID number
    partner_id: int  # Partner identifier
    vendor_id: ObjectId  # Vendor identifier
    vendor_config_id: ObjectId | None = Field(default=None, description="Vendor configuration identifier")
    agent_id: int | None = None  # Agent identifier, optional
    assign_date: int | None = None  # Timestamp of assignment
    mapped_date: int | None = None  # Timestamp of mapping to agent
    status: TalkoDIDStatus = Field(default=TalkoDIDStatus.AVAILABLE)
    status_changed_at: int = Field(default_factory=TalkoDateTimeUtil().get_current_time)
    cooldown_until: int | None = None
    spam_count: int = 0
    last_spam_detected_at: int | None = None
    is_active: bool = True  # Whether the DID is currently active
    did_type: TalkoDIDType = Field(default=TalkoDIDType.NORMAL)
    agent_bot_id: int | None = Field(0, description="AI agent bot ID owning this DID")
    display_name: str | None = Field(default=None, description="Human-friendly display name for this DID")
    did_layer: TalkoDIDLayer = Field(
        default=TalkoDIDLayer.EXTERNAL,
        description="EXTERNAL=wholesaler inventory, INTERNAL=partner-routable clone",
    )
    parent_did_id: ObjectId | None = Field(
        default=None, description="EXTERNAL _id this INTERNAL DID was provisioned from"
    )
    parent_did_number: str | None = Field(default=None, description="Denormalized EXTERNAL DID number for fast lookup")

    @model_validator(mode="after")
    def check_agent_assignment(self) -> "TalkoPhoneNumberManagement":
        """Ensure agent_id and agent_bot_id are never both set."""
        if self.did_type == TalkoDIDType.NORMAL and _is_set(self.agent_bot_id):
            raise ValueError("agent_bot_id must be None for did_type='normal'.")
        if self.did_type == TalkoDIDType.AI_AGENT and _is_set(self.agent_id):
            raise ValueError("agent_id must be None for did_type='ai_agent'.")
        if self.did_layer == TalkoDIDLayer.INTERNAL and not (self.parent_did_id or self.parent_did_number):
            raise ValueError("parent_did_id or parent_did_number is required for did_layer='internal'.")
        if self.did_layer == TalkoDIDLayer.EXTERNAL and (_is_set(self.parent_did_id) or self.parent_did_number):
            raise ValueError("parent_did must be empty for did_layer='external'.")
        return self

    class CollectionName:
        PHONE_NUMBER_MANAGEMENT = "phone_number"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)


class TalkoDidHistoryModel(TalkoTimestampedModel):
    did_number: str  # DID number
    partner_id: int  # Partner identifier
    vendor_id: ObjectId  # Vendor identifier
    vendor_config_id: ObjectId | None = Field(default=None, description="Vendor configuration identifier")
    agent_id: int | None = None  # Agent identifier, optional
    assign_date: int  # Timestamp of assignment
    unassign_date: int | None = None  # Timestamp of unassignment
    workspace_id: int | None = None  # Workspace identifier, optional

    class CollectionName:
        DID_HISTORY = "did_history"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)
