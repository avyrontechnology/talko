from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TalkoContract:
    class PartnerConfigCreate(BaseModel):
        partner_id: int
        vendor_id: str
        vendor_config_id: str
        ai_vendor_config_id: Optional[str] = None
        enable_round_robin: bool = False
        enable_agent_mapping: bool = False
        enable_service_board: bool = False
        service_board_ids: Optional[List[int]] = (
            None  # Service boards for DID assignment
        )
        board_did_counts: Optional[Dict[str, int]] = (
            None  # DID counts per service board
        )
        agent_mapping_ids: Optional[List[int]] = (
            None  # Agent IDs for mapping (one DID per ID)
        )
        round_robin_did_count: Optional[int] = (
            None  # DID count for round-robin (deferred)
        )
        dialer_enabled: bool = False
        enable_agent_reassignment_on_inactive: bool = False
        enable_inbound_round_robin: bool = False

    class PartnerConfigUpdate(BaseModel):
        is_active: Optional[bool] = None
        ai_vendor_config_id: Optional[str] = None
        enable_round_robin: Optional[bool] = None
        enable_agent_mapping: Optional[bool] = None
        enable_service_board: Optional[bool] = None
        service_board_ids: Optional[List[int]] = None
        board_did_counts: Optional[Dict[str, int]] = None
        agent_mapping_ids: Optional[List[int]] = None
        round_robin_did_count: Optional[int] = None
        dialer_enabled: Optional[bool] = None
        enable_agent_reassignment_on_inactive: Optional[bool] = None
        enable_inbound_round_robin: Optional[bool] = None

    class PartnerConfigCreationUpdationResponse(BaseModel):
        id: str
        message: str

    class PartnerConfigResponse(BaseModel):
        id: str
        message: str

    class PartnerDataConfigResponse(BaseModel):
        # NOTE: every Optional field defaults to None. Older DB documents
        # legitimately lack newer keys (message, did_index, ...); without
        # defaults Pydantic v2 treats Optional-without-default as REQUIRED
        # and a single legacy doc 500s the entire list endpoint.
        id: str
        partner_id: int
        vendor_id: str
        ai_vendor_config_id: Optional[str] = None
        is_active: bool
        did_index: Optional[int] = None
        enable_round_robin: bool
        enable_agent_mapping: bool
        enable_service_board: bool
        dialer_enabled: bool
        service_board_ids: Optional[List[int]] = None
        board_did_counts: Optional[Dict[str, int]] = None
        agent_mapping_ids: Optional[List[int]] = None
        round_robin_did_count: Optional[int] = None
        enable_agent_reassignment_on_inactive: bool = False
        enable_inbound_round_robin: bool = False
        inbound_round_robin_index: Optional[int] = None
        created_at: Optional[int] = None
        updated_at: Optional[int] = None
        message: Optional[str] = None
