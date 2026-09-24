from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator


class TalkoContract:
    class CDRCreate(BaseModel):
        action: str
        calling_mode: str
        date_time: int
        solution: str
        sr_number: str
        customer: str
        agent: int | None = None
        call_status: str
        customer_status: str
        agent_status: str
        total_call_duration: int
        talk_time: int
        total_call_duration: Any
        talk_time: Any
        call_actions: list[str]
        call_recording: str | None = None
        call_uuid: str
        hangup_by: str
        disposition: str | None = None
        sub_disposition: str | None = None
        notes: str | None = None
        voice_email: str | None = None
        dtmf_extension: str | None = None
        queue: str | None = None
        partner_id: int | None = None
        lead_id: int | None = None
        entity_type: str | None = None
        entity_id: int | None = None

    class CDRResponse(BaseModel):
        id: str
        action: str
        calling_mode: str
        date_time: int | None = None
        solution: str
        sr_number: str
        customer: int | str | None = None
        agent: int | None = None
        call_status: str
        customer_status: str
        agent_status: str
        total_call_duration: int | None = 0
        talk_time: int | None = 0
        call_actions: list[str]
        call_uuid: str
        hangup_by: str
        partner_id: int | None = None
        created_at: int | None = None
        updated_at: int | None = None

        call_id: str | None = None
        call_recording: str | None = None
        disposition: str | None = None
        sub_disposition: str | None = None
        notes: str | None = None
        voice_email: str | None = None
        dtmf_extension: str | None = None
        queue: str | None = None
        agent_number: str | None = None
        agent_number_with_prefix: str | None = None
        agent_name: str | None = None
        client_number: str | None = None
        did_number: str | None = None
        reason: str | None = None
        hangup_cause: str | None = None
        contact_details: dict[str, Any] | None = None
        missed_agents: list[Any] = []
        call_flow: list[Any] = []
        accountid: str | None = None
        agent_ring_time: str | None = None
        billing_circle: str | dict[str, str | None] | None = None
        agent_hangup_data: Any | None = None
        transfer_missed_agent: list[Any] = []
        call_hint: str | None = None
        support_api_call: bool | None = False
        lead_id: int | None = None
        entity_type: str | None = None
        entity_id: int | None = None
        sid: str | None = None
        sname: str | None = None
        is_incoming_from_broadcast: bool | None = False
        caller_id_number: str | None = None
        sip_agent_ids: Any | None = None
        dialer_call_details: Any | None = None
        custom_status: str | None = None
        is_whatsapp: int | None = 0
        lead_data: list[Any] = []
        lead_name: str | None = None
        voicemail_recording: bool | None = False
        call_duration: int | None = 0
        answered_seconds: int | None = 0
        minutes_consumed: int | None = 0
        charges: int | None = 0
        department_name: str | None = None
        detailed_description: str | None = None
        start_stamp: int | str | None = None
        end_stamp: int | str | None = None
        ivr_id: str | None = None
        answer_agent_number: str | None = None
        answer_stamp: int | str | None = None
        billsec: str | None = None
        outbound_sec: str | None = None
        call_connected: str | None = None
        aws_call_recording_identifier: str | None = None
        campaign_name: str | None = None
        campaign_id: int | str | None = None
        customer_ring_time: str | None = None
        reason_key: str | None = None
        vendor_id: str | None = None
        vendor_config_id: str | None = None
        custom_fields: dict[str, Any] | None = None

    class CallLogResponse(BaseModel):
        # Core fields
        id: str
        action: str
        calling_mode: str
        date_time: int | None = None
        solution: str
        sr_number: str
        customer: int | str | None = None
        agent: int | None = None
        call_status: str
        customer_status: str
        agent_status: str
        total_call_duration: int | None = 0
        talk_time: int | None = 0
        call_actions: list[str]
        call_uuid: str
        hangup_by: str
        partner_id: int | None = None
        created_at: int | None = None
        updated_at: int | None = None

        # Additional fields from TalkoCDR
        call_id: str | None = None
        call_recording: str | None = None
        disposition: str | None = None
        sub_disposition: str | None = None
        notes: str | None = None
        voice_email: str | None = None
        dtmf_extension: str | None = None
        queue: str | None = None
        agent_number: str | None = None
        agent_number_with_prefix: str | None = None
        client_number: str | None = None
        did_number: str | None = None
        reason: str | None = None
        hangup_cause: str | None = None
        contact_details: dict[str, Any] | None = None
        missed_agents: list[Any] = []
        accountid: str | None = None
        agent_ring_time: str | None = None
        billing_circle: str | dict[str, str | None] | None = None
        agent_hangup_data: Any | None = None
        transfer_missed_agent: list[Any] = []
        call_hint: str | None = None
        support_api_call: bool | None = False
        lead_id: int | None = None
        entity_type: str | None = None
        entity_id: int | None = None
        sid: str | None = None
        sname: str | None = None
        is_incoming_from_broadcast: bool | None = False
        caller_id_number: str | None = None
        sip_agent_ids: Any | None = None
        dialer_call_details: Any | None = None
        custom_status: str | None = None
        is_whatsapp: int | None = 0
        lead_data: list[Any] = []
        lead_name: str | None = None
        voicemail_recording: bool | None = False
        call_duration: int | None = 0
        answered_seconds: int | None = 0
        minutes_consumed: int | None = 0
        charges: int | None = 0
        department_name: str | None = None
        detailed_description: str | None = None
        start_stamp: int | None = None
        end_stamp: int | None = None
        ivr_id: str | None = None
        answer_agent_number: str | None = None
        answer_stamp: int | None = None
        billsec: str | None = None
        outbound_sec: str | None = None
        call_connected: str | None = None
        aws_call_recording_identifier: str | None = None
        campaign_name: str | None = None
        campaign_id: int | str | None = None
        customer_ring_time: str | None = None
        reason_key: str | None = None
        answered_agent_number: str | None = None
        event_type: str | None = None
        action_performed_by: str | None = None
        do_recording_url: str | None = None
        vendor_id: str | None = None
        vendor_config_id: str | None = None
        display_name: str | None = None
        custom_fields: dict[str, Any] | None = None

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

        partner_id: int | None = None
        agent: int | None = None
        lead_id: int | None = None
        entity_type: str | None = None
        entity_id: int | None = None
        workspace_id: int | None = None
        calling_mode: str
        call_status: str
        call_recording: str | None = None
        lead_number: int | str | None = None
        total_call_duration: int | None = 0
        talk_time: int | None = 0
        did_number: str | None = None
        agent_number: str | None = None
        reason: str | None = None
        hangup_cause: str | None = None
        reason_key: str | None = None
        hangup_by: str
        created_at: int | None = None
        action_performed_by: str | None = None
        lead_call_status: str | None = None
        agent_call_status: str | None = None
        call_connected: int | str | None = None
        lead_name: str | None = None
        call_type: str | None = None
        do_recording_url: str | None = None
        number_type: str | None = None
        lead_secret: str | None = None
        call_id: str | None = None
        call_uuid: str | None = None
        vendor_id: str | None = None
        vendor_config_id: str | None = None
        display_name: str | None = None
        custom_fields: dict[str, Any] | None = None

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
        call_record: list[TalkoContract.CallRecordHistoryResponse] = []
        total_count: int

        @field_validator("call_record", mode="before")
        def ensure_call_histories(cls, v):
            """Ensure call_histories is always a list."""
            if not isinstance(v, list):
                return []
            return v

    class AgentCallLogResponse(BaseModel):
        call_histories: list[TalkoContract.CallLogResponse] = []
        total_count: int

        @field_validator("call_histories", mode="before")
        def ensure_call_histories(cls, v):
            """Ensure call_histories is always a list."""
            if not isinstance(v, list):
                return []
            return v

    class CallRecordHistoryPayload(BaseModel):
        lead_id: int | None = None
        entity_type: str | None = None
        entity_id: int | None = None
        workspace_id: int | None = None
        time_range: str | None = None
        call_status: list[str] | None = None
        agents: list[int] | None = None
        phone_number: str | None = None
        talk_time_range: list[str] | None = None
        call_type: str | None = None
        did_number: str | None = None
        is_masking_enabled: bool | None = True
        custom_fields: dict[str, Any] | None = None

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
                    raise ValueError(f"Invalid call_type: {v}. Allowed values: {valid_call_types}")
            return v

        @field_validator("time_range")
        def validate_time_range(cls, v):
            if v is not None:
                try:
                    start, end = v.split("-")
                    start = int(start)
                    end = int(end)
                    if start > end:
                        raise ValueError("start_time must be less than or equal to end_time")
                except (ValueError, AttributeError):
                    raise ValueError("time_range must be in format 'start_time-end_time' with valid integers")
            return v

    class SetCDRCustomFieldsRequest(BaseModel):
        custom_fields: dict[str, Any]

    class SetCDRCustomFieldsResponse(BaseModel):
        call_id: str
        custom_fields: dict[str, Any]
        message: str
