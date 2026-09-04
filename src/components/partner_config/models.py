from typing import Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.utils.enums import RingType
from src.utils.timestamped_model import TimestampedModel


class PartnerConfigModel(TimestampedModel):
    partner_id: Optional[int] = None  # ID of the partner
    is_active: bool  # Active status
    vendor_id: ObjectId  # Associated vendor ID
    vendor_config_id: Optional[str] = None  # Associated vendor config ID
    ai_vendor_config_id: Optional[str] = (
        None  # Vendor config used for AI-bridge calls (falls back to vendor_config_id)
    )
    did_indices: Dict[str | int, int] = Field(
        default_factory=lambda: {"round_robin": 0}
    )  # Indices for round-robin and service boards
    enable_round_robin: bool = False  # Flag to enable round-robin DID assignment
    enable_agent_mapping: bool = False  # Flag to enable agent-specific DID mapping
    enable_service_board: bool = False  # Flag to enable service board DID assignment
    service_board_ids: Optional[List[int]] = (
        None  # Service board IDs for DID assignment
    )
    board_did_counts: Optional[Dict[str, int]] = None  # DID counts per service board
    agent_mapping_ids: Optional[List[int]] = (
        None  # Agent IDs for mapping (one DID per ID)
    )
    round_robin_did_count: Optional[int] = None  # DID count for round-robin (deferred)
    service_default_attendance: Dict[int, List[Dict[str, Any]]] = Field(
        default_factory=dict
    )  # Default attendance per service board
    round_robin_default_attendance: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=lambda: {"default": []}
    )  # Default attendance for round-robin
    ring_type: Optional[RingType] = None
    dialer_enabled: bool = Field(False, description="Enable dialer for this partner")
    enable_inbound_lead_creation: bool = Field(
        default=True,
        description=(
            "When True and no CDR exists for an inbound call, "
            "attempt to create a new lead in Maglo/CRM before routing"
        ),
    )
    enable_ai_agent: bool = Field(
        False, description="Master switch — enable AI agent routing for this partner"
    )
    enable_agent_reassignment_on_inactive: bool = Field(
        False,
        description=(
            "When True, an inbound call whose lead is assigned to an inactive "
            "agent is rerouted to another active agent on the service board, "
            "and Maglo is notified to reassign lead ownership"
        ),
    )
    enable_inbound_round_robin: bool = Field(
        False,
        description=(
            "When True, an inbound call with no single assigned agent rings "
            "the service board's agents one rotation position at a time "
            "(ring_type=order_by) instead of ringing all of them at once"
        ),
    )
    inbound_round_robin_index: int = Field(
        0,
        description=(
            "Cursor for inbound round-robin agent ringing order, shared "
            "across all of this partner's service boards"
        ),
    )
    enable_missed_call_callback: bool = Field(
        False,
        description=(
            "When True, a missed inbound call with an assigned agent triggers "
            "an automatic outbound callback ~100s later, provided the customer "
            "hasn't already connected on another call in the meantime"
        ),
    )

    class CollectionName:
        PARTNER_CONFIG = "partner_config"  # Collection name

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def check_mutual_exclusivity_and_config(self) -> "PartnerConfigModel":
        if self.enable_round_robin and self.enable_service_board:
            raise ValueError(
                "Round-robin and service board cannot be enabled simultaneously."
            )
        if self.enable_service_board and not self.service_board_ids:
            raise ValueError(
                "Service board IDs are required when service board is enabled."
            )
        if self.enable_round_robin and self.round_robin_did_count is None:
            raise ValueError(
                "round_robin_did_count is required when enable_round_robin is true."
            )
        if self.enable_service_board:
            for board_id in self.service_board_ids or []:
                if board_id not in self.did_indices:
                    self.did_indices[board_id] = 0
        elif self.enable_round_robin and "round_robin" not in self.did_indices:
            self.did_indices["round_robin"] = 0
        if (
            self.enable_service_board
            and any(
                len(attendance) > 1
                for attendance in self.service_default_attendance.values()
            )
        ) or (
            self.enable_round_robin
            and len(self.round_robin_default_attendance["default"]) > 1
        ):
            if not self.ring_type:
                raise ValueError(
                    "ring_type is required for multiple default attendance numbers."
                )
        return self
