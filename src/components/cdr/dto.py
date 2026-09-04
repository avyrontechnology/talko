from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, field_validator


class Contract:
    class CDRCreate(BaseModel):
        action: str
        calling_mode: str
        date_time: int
        solution: str
        sr_number: str
        customer: str
        agent: Optional[int] = None
        call_status: str
        customer_status: str
        agent_status: str
        total_call_duration: int
        talk_time: int
        total_call_duration: Any
        talk_time: Any
        call_actions: List[str]
        call_recording: Optional[str] = None
        call_uuid: str
        hangup_by: str
        disposition: Optional[str] = None
        sub_disposition: Optional[str] = None
        notes: Optional[str] = None
        voice_email: Optional[str] = None
        dtmf_extension: Optional[str] = None
        queue: Optional[str] = None
        partner_id: Optional[int] = None
        lead_id: Optional[int] = None
        entity_type: Optional[str] = None
        entity_id: Optional[int] = None

    class CDRResponse(BaseModel):
        id: str
        action: str
        calling_mode: str
        date_time: Optional[int] = None
        solution: str
        sr_number: str
        customer: Optional[Union[int, str]] = None
        agent: Optional[int] = None
        call_status: str
        customer_status: str
        agent_status: str
        total_call_duration: Optional[int] = 0
        talk_time: Optional[int] = 0
        call_actions: List[str]
        call_uuid: str
        hangup_by: str
        partner_id: Optional[int] = None
        created_at: Optional[int] = None
        updated_at: Optional[int] = None

        call_id: Optional[str] = None
        call_recording: Optional[str] = None
        disposition: Optional[str] = None
        sub_disposition: Optional[str] = None
        notes: Optional[str] = None
        voice_email: Optional[str] = None
        dtmf_extension: Optional[str] = None
        queue: Optional[str] = None
        agent_number: Optional[str] = None
        agent_number_with_prefix: Optional[str] = None
        agent_name: Optional[str] = None
        client_number: Optional[str] = None
        did_number: Optional[str] = None
        reason: Optional[str] = None
        hangup_cause: Optional[str] = None
        contact_details: Optional[Dict[str, Any]] = None
        missed_agents: List[Any] = []
        call_flow: List[Any] = []
        accountid: Optional[str] = None
        agent_ring_time: Optional[str] = None
        billing_circle: Optional[Union[str, Dict[str, Optional[str]]]] = None
        agent_hangup_data: Optional[Any] = None
        transfer_missed_agent: List[Any] = []
        call_hint: Optional[str] = None
        support_api_call: Optional[bool] = False
        lead_id: Optional[int] = None
        entity_type: Optional[str] = None
        entity_id: Optional[int] = None
        sid: Optional[str] = None
        sname: Optional[str] = None
        is_incoming_from_broadcast: Optional[bool] = False
        caller_id_number: Optional[str] = None
        sip_agent_ids: Optional[Any] = None
        dialer_call_details: Optional[Any] = None
        custom_status: Optional[str] = None
        is_whatsapp: Optional[int] = 0
        lead_data: List[Any] = []
        lead_name: Optional[str] = None
        voicemail_recording: Optional[bool] = False
        call_duration: Optional[int] = 0
        answered_seconds: Optional[int] = 0
        minutes_consumed: Optional[int] = 0
        charges: Optional[int] = 0
        department_name: Optional[str] = None
        detailed_description: Optional[str] = None
        start_stamp: Optional[Union[int, str]] = None
        end_stamp: Optional[Union[int, str]] = None
        ivr_id: Optional[str] = None
        answer_agent_number: Optional[str] = None
        answer_stamp: Optional[Union[int, str]] = None
        billsec: Optional[str] = None
        outbound_sec: Optional[str] = None
        call_connected: Optional[str] = None
        aws_call_recording_identifier: Optional[str] = None
        campaign_name: Optional[str] = None
        campaign_id: Optional[Union[int, str]] = None
        customer_ring_time: Optional[str] = None
        reason_key: Optional[str] = None
        vendor_id: Optional[str] = None
        vendor_config_id: Optional[str] = None
        custom_fields: Optional[Dict[str, Any]] = None

    class CallLogResponse(BaseModel):
        # Core fields
        id: str
        action: str
        calling_mode: str
        date_time: Optional[int] = None
        solution: str
        sr_number: str
        customer: Optional[Union[int, str]] = None
        agent: Optional[int] = None
        call_status: str
        customer_status: str
        agent_status: str
        total_call_duration: Optional[int] = 0
        talk_time: Optional[int] = 0
        call_actions: List[str]
        call_uuid: str
        hangup_by: str
        partner_id: Optional[int] = None
        created_at: Optional[int] = None
        updated_at: Optional[int] = None

        # Additional fields from CDR
        call_id: Optional[str] = None
        call_recording: Optional[str] = None
        disposition: Optional[str] = None
        sub_disposition: Optional[str] = None
        notes: Optional[str] = None
        voice_email: Optional[str] = None
        dtmf_extension: Optional[str] = None
        queue: Optional[str] = None
        agent_number: Optional[str] = None
        agent_number_with_prefix: Optional[str] = None
        client_number: Optional[str] = None
        did_number: Optional[str] = None
        reason: Optional[str] = None
        hangup_cause: Optional[str] = None
        contact_details: Optional[Dict[str, Any]] = None
        missed_agents: List[Any] = []
        accountid: Optional[str] = None
        agent_ring_time: Optional[str] = None
        billing_circle: Optional[Union[str, Dict[str, Optional[str]]]] = None
        agent_hangup_data: Optional[Any] = None
        transfer_missed_agent: List[Any] = []
        call_hint: Optional[str] = None
        support_api_call: Optional[bool] = False
        lead_id: Optional[int] = None
        entity_type: Optional[str] = None
        entity_id: Optional[int] = None
        sid: Optional[str] = None
        sname: Optional[str] = None
        is_incoming_from_broadcast: Optional[bool] = False
        caller_id_number: Optional[str] = None
        sip_agent_ids: Optional[Any] = None
        dialer_call_details: Optional[Any] = None
        custom_status: Optional[str] = None
        is_whatsapp: Optional[int] = 0
        lead_data: List[Any] = []
        lead_name: Optional[str] = None
        voicemail_recording: Optional[bool] = False
        call_duration: Optional[int] = 0
        answered_seconds: Optional[int] = 0
        minutes_consumed: Optional[int] = 0
        charges: Optional[int] = 0
        department_name: Optional[str] = None
        detailed_description: Optional[str] = None
        start_stamp: Optional[int] = None
        end_stamp: Optional[int] = None
        ivr_id: Optional[str] = None
        answer_agent_number: Optional[str] = None
        answer_stamp: Optional[int] = None
        billsec: Optional[str] = None
        outbound_sec: Optional[str] = None
        call_connected: Optional[str] = None
        aws_call_recording_identifier: Optional[str] = None
        campaign_name: Optional[str] = None
        campaign_id: Optional[Union[int, str]] = None
        customer_ring_time: Optional[str] = None
        reason_key: Optional[str] = None
        answered_agent_number: Optional[str] = None
        event_type: Optional[str] = None
        action_performed_by: Optional[str] = None
        do_recording_url: Optional[str] = None
        vendor_id: Optional[str] = None
        vendor_config_id: Optional[str] = None
        display_name: Optional[str] = None
        custom_fields: Optional[Dict[str, Any]] = None

        @field_validator("total_call_duration", "talk_time", mode="before")
        def handle_int_fields(cls, v):
            """
            Ensures that duration/talk_time fields are always int.
            If None, empty string, or invalid → return 0.
            """
            if v in (None, "", "null", "None"):
                return 0
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0

        @field_validator("start_stamp", "end_stamp", "answer_stamp", mode="before")
        def handle_timestamp_fields(cls, v):
            """
            Ensures that timestamp fields are either int or None.
            If empty/invalid → return None.
            """
            if v in (None, "", "null", "None"):
                return None
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

    class CallRecordHistoryResponse(BaseModel):
        """Slimmed-down response model for call record history with limited fields."""

        partner_id: Optional[int] = None
        agent: Optional[int] = None
        lead_id: Optional[int] = None
        entity_type: Optional[str] = None
        entity_id: Optional[int] = None
        service_board_id: Optional[int] = None
        calling_mode: str
        call_status: str
        call_recording: Optional[str] = None
        lead_number: Optional[Union[int, str]] = None
        total_call_duration: Optional[int] = 0
        talk_time: Optional[int] = 0
        did_number: Optional[str] = None
        agent_number: Optional[str] = None
        reason: Optional[str] = None
        hangup_cause: Optional[str] = None
        reason_key: Optional[str] = None
        hangup_by: str
        created_at: Optional[int] = None
        action_performed_by: Optional[str] = None
        lead_call_status: Optional[str] = None
        agent_call_status: Optional[str] = None
        call_connected: Optional[Union[int, str]] = None
        lead_name: Optional[str] = None
        call_type: Optional[str] = None
        do_recording_url: Optional[str] = None
        number_type: Optional[str] = None
        lead_secret: Optional[str] = None
        call_id: Optional[str] = None
        call_uuid: Optional[str] = None
        vendor_id: Optional[str] = None
        vendor_config_id: Optional[str] = None
        display_name: Optional[str] = None
        custom_fields: Optional[Dict[str, Any]] = None

        @field_validator("total_call_duration", "talk_time", mode="before")
        def handle_int_fields(cls, v):
            """
            Ensures that duration/talk_time fields are always int.
            If None, empty string, or invalid → return 0.
            """
            if v in (None, "", "null", "None"):
                return 0
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0

    class AgentCallRecordHistoryResponse(BaseModel):
        call_record: List["Contract.CallRecordHistoryResponse"] = []
        total_count: int

        @field_validator("call_record", mode="before")
        def ensure_call_histories(cls, v):
            """Ensure call_histories is always a list."""
            if not isinstance(v, list):
                return []
            return v

    class AgentCallLogResponse(BaseModel):
        call_histories: List["Contract.CallLogResponse"] = []
        total_count: int

        @field_validator("call_histories", mode="before")
        def ensure_call_histories(cls, v):
            """Ensure call_histories is always a list."""
            if not isinstance(v, list):
                return []
            return v

    class CallRecordHistoryPayload(BaseModel):
        lead_id: Optional[int] = None
        entity_type: Optional[str] = None
        entity_id: Optional[int] = None
        service_board_id: Optional[int] = None
        time_range: Optional[str] = None
        call_status: Optional[List[str]] = None
        agents: Optional[List[int]] = None
        phone_number: Optional[str] = None
        talk_time_range: Optional[List[str]] = None
        call_type: Optional[str] = None
        did_number: Optional[str] = None
        is_masking_enabled: Optional[bool] = True
        custom_fields: Optional[Dict[str, Any]] = None

        @field_validator("call_status")
        def validate_call_status(cls, v):
            if v is not None:
                valid_statuses = [
                    "answered",
                    "missed",
                    "lead_connected",
                    "lead_not_connected",
                    "agent_connected",
                    "agent_not_connected",
                ]
                invalid_statuses = [s for s in v if s not in valid_statuses]
                if invalid_statuses:
                    raise ValueError(
                        f"Invalid call_status values: {invalid_statuses}. Allowed values: {valid_statuses}"
                    )
            return v

        @field_validator("call_type")
        def validate_call_type(cls, v):
            if v is not None:
                valid_call_types = ["incoming", "outgoing"]
                if v not in valid_call_types:
                    raise ValueError(
                        f"Invalid call_type: {v}. Allowed values: {valid_call_types}"
                    )
            return v

        @field_validator("time_range")
        def validate_time_range(cls, v):
            if v is not None:
                try:
                    start, end = v.split("-")
                    start = int(start)
                    end = int(end)
                    if start > end:
                        raise ValueError(
                            "start_time must be less than or equal to end_time"
                        )
                except (ValueError, AttributeError):
                    raise ValueError(
                        "time_range must be in format 'start_time-end_time' with valid integers"
                    )
            return v

    class SetCDRCustomFieldsRequest(BaseModel):
        custom_fields: Dict[str, Any]

    class SetCDRCustomFieldsResponse(BaseModel):
        call_id: str
        custom_fields: Dict[str, Any]
        message: str
