from typing import Any

from pydantic import Field

from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoCDR(TalkoTimestampedModel):
    # Call identifiers and context
    entity_type: str | None = None  # "Lead" or "Contact"
    entity_id: int | None = None  # the actual ID regardless of type
    entity_name: str | None = None  # the name of the lead/contact, if available

    # Partner-related identifiers
    partner_id: int | None = None
    vendor_id: str | None = None
    vendor_config_id: str | None = None
    call_id: str | None = None
    call_uuid: str
    number_type: str | None = None
    outbound_type: str | None = None
    inbound_type: str | None = None
    is_dialer_call: bool = False

    # Call meta information
    action: str
    calling_mode: str | None = None
    call_status: str
    call_recording: str | None = None
    date_time: int | None = None

    # Service information
    solution: str
    sr_number: str

    # Participants
    customer: int | str | None = None  # Interpreted from "$numberLong"
    agent: int | None = None
    customer_status: str
    agent_status: str

    # Call durations
    total_call_duration: int | None = 0  # "12" → int
    talk_time: int | None = 0

    # Call actions and dispositions
    call_actions: list[str]
    hangup_by: str
    disposition: str | None = None
    sub_disposition: str | None = None
    notes: str | None = None

    # Additional metadata
    voice_email: str | None = None
    dtmf_extension: str | None = None
    queue: str | None = None

    # Agent details
    agent_number: str | None = None
    cloud_agent_number: str | None = None
    agent_number_with_prefix: str | None = None
    agent_name: str | None = None

    # Customer/caller details
    client_number: str | None = None
    did_number: str | None = None
    reason: str | None = None
    hangup_cause: str | None = None

    # Additional call context
    contact_details: dict[str, Any] | None = None
    missed_agents: list[Any] = []
    call_flow: list[Any] = []
    accountid: str | None = None

    # Timing and billing
    agent_ring_time: str | None = None
    billing_circle: str | dict[str, str | None] | None = None
    agent_hangup_data: Any | None = None
    transfer_missed_agent: list[Any] = []
    call_hint: str | None = None
    support_api_call: bool = False
    lead_id: int | None = None
    lead_name: str | None = None
    workspace_id: int | None = None
    sid: str | None = None
    sname: str | None = None

    # Flags and indicators
    is_incoming_from_broadcast: bool = False
    caller_id_number: str | None = None
    sip_agent_ids: Any | None = None
    dialer_call_details: Any | None = None
    custom_status: str | None = None
    is_whatsapp: int | None = 0

    # Lead and voicemail
    lead_data: list[Any] = []
    voicemail_recording: bool = False

    # Duration and billing metrics
    call_duration: int | None = 0
    answered_seconds: int | None = 0
    minutes_consumed: int | None = 0
    charges: int | None = 0

    # Department and campaign details
    department_name: str | None = None
    detailed_description: str | None = None
    start_stamp: int | None = None
    end_stamp: int | None = None
    ivr_id: str | None = None
    ivr_name: str | list[Any] | None = None

    # Answering agent
    answer_agent_number: str | None = None
    answer_stamp: int | None = None
    billsec: str | None = None
    digits_dialed: str | None = None
    outbound_sec: str | None = None
    call_connected: int | str | None = None
    aws_call_recording_identifier: str | None = None
    agent_ids: list[dict] | None = None

    # Campaign tracking
    campaign_name: str | None = None
    campaign_id: int | str | None = None
    customer_ring_time: str | None = None
    reason_key: str | None = None

    # check to ensure if its recordings is saved or not
    is_recording_saved: bool = False
    path_for_recording: str = None

    # Dialer specific – high value
    campaign_id: str | int | None = None
    campaign_name: str | None = None
    broadcast_lead_fields: dict | None = None
    missed_agents: list[dict] = Field(default_factory=list)
    answered_agent_number: str | None = None
    answered_agent_name: str | None = None
    reason_key: str | None = None
    hangup_cause_key: str | None = None
    hangup_cause_description: str | None = None
    customer_ring_time: str | None = None
    agent_ring_time: str | None = None
    customer_no_with_prefix: str | None = None

    # Disposition & scheduling
    disposition: str | None = None
    sub_disposition: str | None = None
    schedule_timestamp: int | None = None
    schedule_assigned_agent_id: int | None = None
    schedule_note: str | None = None

    # Post-call analysis
    stt: str | None = None  # speech-to-text
    llm_analysis: dict | None = None
    call_hint: str | None = None

    # Partner-defined custom fields, keyed by field_slug (see
    # src.components.custom_field for field definitions)
    custom_fields: dict[str, Any] | None = None

    # Set on an outbound TalkoCDR created by the missed-call auto-callback flow —
    # points back at the call_uuid of the missed inbound TalkoCDR that triggered it.
    callback_for_call_uuid: str | None = None

    class CollectionName:
        TalkoCDR = "cdr"
