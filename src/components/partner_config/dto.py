from pydantic import BaseModel


class TalkoContract:
    class PartnerConfigCreate(BaseModel):
        partner_id: int
        client_id: str | None = None
        vendor_id: str
        vendor_config_id: str
        ai_vendor_config_id: str | None = None
        enable_round_robin: bool = False
        enable_agent_mapping: bool = False
        enable_workspace: bool = False
        workspace_ids: list[int] | None = None  # Workspaces for DID assignment
        workspace_did_counts: dict[str, int] | None = None  # DID counts per workspace
        agent_mapping_ids: list[int] | None = None  # Agent IDs for mapping (one DID per ID)
        round_robin_did_count: int | None = None  # DID count for round-robin (deferred)
        dialer_enabled: bool = False
        enable_agent_reassignment_on_inactive: bool = False
        enable_inbound_round_robin: bool = False

    class PartnerConfigUpdate(BaseModel):
        is_active: bool | None = None
        client_id: str | None = None
        ai_vendor_config_id: str | None = None
        enable_round_robin: bool | None = None
        enable_agent_mapping: bool | None = None
        enable_workspace: bool | None = None
        workspace_ids: list[int] | None = None
        workspace_did_counts: dict[str, int] | None = None
        agent_mapping_ids: list[int] | None = None
        round_robin_did_count: int | None = None
        dialer_enabled: bool | None = None
        enable_agent_reassignment_on_inactive: bool | None = None
        enable_inbound_round_robin: bool | None = None

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
        client_id: str | None = None
        vendor_id: str
        ai_vendor_config_id: str | None = None
        is_active: bool
        did_index: int | None = None
        enable_round_robin: bool
        enable_agent_mapping: bool
        enable_workspace: bool
        dialer_enabled: bool
        workspace_ids: list[int] | None = None
        workspace_did_counts: dict[str, int] | None = None
        agent_mapping_ids: list[int] | None = None
        round_robin_did_count: int | None = None
        enable_agent_reassignment_on_inactive: bool = False
        enable_inbound_round_robin: bool = False
        inbound_round_robin_index: int | None = None
        created_at: int | None = None
        updated_at: int | None = None
        message: str | None = None
