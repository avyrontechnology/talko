from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoCDR(TalkoTimestampedModel):
    # Call identifiers and context
    entity_type: Optional[str] = None  # "Lead" or "Contact"
    entity_id: Optional[int] = None  # the actual ID regardless of type
    entity_name: Optional[str] = None  # the name of the lead/contact, if available

    # Partner-related identifiers
    partner_id: Optional[int] = None
    vendor_id: Optional[str] = None
    vendor_config_id: Optional[str] = None
    call_id: Optional[str] = None
    call_uuid: str
    number_type: Optional[str] = None
    outbound_type: Optional[str] = None
    inbound_type: Optional[str] = None
    is_dialer_call: bool = False

    # Call meta information
    action: str
    calling_mode: Optional[str] = None
    call_status: str
    call_recording: Optional[str] = None
    date_time: Optional[int] = None

    # Service information
    solution: str
    sr_number: str

    # Participants
    customer: Optional[Union[int, str]] = None  # Interpreted from "$numberLong"
    agent: Optional[int] = None
    customer_status: str
    agent_status: str

    # Call durations
    total_call_duration: Optional[int] = 0  # "12" → int
    talk_time: Optional[int] = 0

    # Call actions and dispositions
    call_actions: List[str]
    hangup_by: str
    disposition: Optional[str] = None
    sub_disposition: Optional[str] = None
    notes: Optional[str] = None

    # Additional metadata
    voice_email: Optional[str] = None
    dtmf_extension: Optional[str] = None
    queue: Optional[str] = None

    # Agent details
    agent_number: Optional[str] = None
    cloud_agent_number: Optional[str] = None
    agent_number_with_prefix: Optional[str] = None
    agent_name: Optional[str] = None

    # Customer/caller details
    client_number: Optional[str] = None
    did_number: Optional[str] = None
    reason: Optional[str] = None
    hangup_cause: Optional[str] = None

    # Additional call context
    contact_details: Optional[Dict[str, Any]] = None
    missed_agents: List[Any] = []
    call_flow: List[Any] = []
    accountid: Optional[str] = None

    # Timing and billing
    agent_ring_time: Optional[str] = None
    billing_circle: Optional[Union[str, Dict[str, Optional[str]]]] = None
    agent_hangup_data: Optional[Any] = None
    transfer_missed_agent: List[Any] = []
    call_hint: Optional[str] = None
    support_api_call: bool = False
    lead_id: Optional[int] = None
    lead_name: Optional[str] = None
    service_board_id: Optional[int] = None
    sid: Optional[str] = None
    sname: Optional[str] = None

    # Flags and indicators
    is_incoming_from_broadcast: bool = False
    caller_id_number: Optional[str] = None
    sip_agent_ids: Optional[Any] = None
    dialer_call_details: Optional[Any] = None
    custom_status: Optional[str] = None
    is_whatsapp: Optional[int] = 0

    # Lead and voicemail
    lead_data: List[Any] = []
    voicemail_recording: bool = False

    # Duration and billing metrics
    call_duration: Optional[int] = 0
    answered_seconds: Optional[int] = 0
    minutes_consumed: Optional[int] = 0
    charges: Optional[int] = 0

    # Department and campaign details
    department_name: Optional[str] = None
    detailed_description: Optional[str] = None
    start_stamp: Optional[int] = None
    end_stamp: Optional[int] = None
    ivr_id: Optional[str] = None
    ivr_name: Optional[Union[str, List[Any]]] = None

    # Answering agent
    answer_agent_number: Optional[str] = None
    answer_stamp: Optional[int] = None
    billsec: Optional[str] = None
    digits_dialed: Optional[str] = None
    outbound_sec: Optional[str] = None
    call_connected: Optional[Union[int, str]] = None
    aws_call_recording_identifier: Optional[str] = None
    agent_ids: Optional[List[Dict]] = None

    # Campaign tracking
    campaign_name: Optional[str] = None
    campaign_id: Optional[Union[int, str]] = None
    customer_ring_time: Optional[str] = None
    reason_key: Optional[str] = None

    # check to ensure if its recordings is saved or not
    is_recording_saved: bool = False
    path_for_recording: str = None

    # Dialer specific – high value
    campaign_id: Optional[Union[str, int]] = None
    campaign_name: Optional[str] = None
    broadcast_lead_fields: Optional[Dict] = None
    missed_agents: List[Dict] = Field(default_factory=list)
    answered_agent_number: Optional[str] = None
    answered_agent_name: Optional[str] = None
    reason_key: Optional[str] = None
    hangup_cause_key: Optional[str] = None
    hangup_cause_description: Optional[str] = None
    customer_ring_time: Optional[str] = None
    agent_ring_time: Optional[str] = None
    customer_no_with_prefix: Optional[str] = None

    # Disposition & scheduling
    disposition: Optional[str] = None
    sub_disposition: Optional[str] = None
    schedule_timestamp: Optional[int] = None
    schedule_assigned_agent_id: Optional[int] = None
    schedule_note: Optional[str] = None

    # Post-call analysis
    stt: Optional[str] = None  # speech-to-text
    llm_analysis: Optional[Dict] = None
    call_hint: Optional[str] = None

    # Partner-defined custom fields, keyed by field_slug (see
    # src.components.custom_field for field definitions)
    custom_fields: Optional[Dict[str, Any]] = None

    # Set on an outbound TalkoCDR created by the missed-call auto-callback flow —
    # points back at the call_uuid of the missed inbound TalkoCDR that triggered it.
    callback_for_call_uuid: Optional[str] = None

    class CollectionName:
        TalkoCDR = "cdr"
