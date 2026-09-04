from typing import Optional

from bson import ObjectId
from pydantic import ConfigDict, Field, model_validator

from src.components.did_management.constants import DIDStatus, DIDType
from src.utils.datetime_util import DateTimeUtil
from src.utils.timestamped_model import TimestampedModel


class PhoneNumberManagement(TimestampedModel):
    service_board_id: int  # Service board identifier
    did_number: str  # DID number
    partner_id: int  # Partner identifier
    vendor_id: ObjectId  # Vendor identifier
    vendor_config_id: ObjectId  # Vendor configuration identifier
    agent_id: Optional[int] = None  # Agent identifier, optional
    assign_date: Optional[int] = None  # Timestamp of assignment
    mapped_date: Optional[int] = None  # Timestamp of mapping to agent
    status: DIDStatus = Field(default=DIDStatus.AVAILABLE)
    status_changed_at: int = Field(default_factory=DateTimeUtil().get_current_time)
    cooldown_until: Optional[int] = None
    spam_count: int = 0
    last_spam_detected_at: Optional[int] = None
    is_active: bool = True  # Whether the DID is currently active
    did_type: DIDType = Field(default=DIDType.NORMAL)
    agent_bot_id: Optional[int] = Field(
        0, description="AI agent bot ID owning this DID"
    )
    display_name: Optional[str] = Field(
        default=None, description="Human-friendly display name for this DID"
    )

    @model_validator(mode="after")
    def check_agent_assignment(self) -> "PhoneNumberManagement":
        """Ensure agent_id and agent_bot_id are never both set."""
        if self.did_type == DIDType.NORMAL and self.agent_bot_id is not None:
            raise ValueError("agent_bot_id must be None for did_type='normal'.")
        if self.did_type == DIDType.AI_AGENT and self.agent_id is not None:
            raise ValueError("agent_id must be None for did_type='ai_agent'.")
        return self

    class CollectionName:
        PHONE_NUMBER_MANAGEMENT = "phone_number"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)


class DidHistoryModel(TimestampedModel):
    did_number: str  # DID number
    partner_id: int  # Partner identifier
    vendor_id: ObjectId  # Vendor identifier
    vendor_config_id: ObjectId  # Vendor configuration identifier
    agent_id: Optional[int] = None  # Agent identifier, optional
    assign_date: int  # Timestamp of assignment
    unassign_date: Optional[int] = None  # Timestamp of unassignment
    service_board_id: Optional[int] = None  # Service board identifier, optional

    class CollectionName:
        DID_HISTORY = "did_history"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)
