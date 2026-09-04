from typing import Any, Dict, List, Optional, Union
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.components.cdr.dto import Contract


def test_cdr_create_valid():
    """Test CDRCreate with valid data."""
    data = {
        "action": "call",
        "calling_mode": "inbound",
        "date_time": 1727181060000,
        "solution": "support",
        "sr_number": "SR123",
        "customer": "9999999999",
        "agent": 1,
        "call_status": "answered",
        "customer_status": "connected",
        "agent_status": "connected",
        "total_call_duration": 120,
        "talk_time": 100,
        "call_actions": ["dial", "answer"],
        "call_uuid": "uuid-123",
        "hangup_by": "agent",
        "call_recording": "http://recording.com/1",
        "disposition": "resolved",
        "sub_disposition": "success",
        "notes": "Customer satisfied",
        "voice_email": "customer@example.com",
        "dtmf_extension": "1234",
        "queue": "support_queue",
        "partner_id": 10,
    }
    cdr = Contract.CDRCreate(**data)
    assert cdr.action == "call"
    assert cdr.calling_mode == "inbound"
    assert cdr.date_time == 1727181060000
    assert cdr.solution == "support"
    assert cdr.sr_number == "SR123"
    assert cdr.customer == "9999999999"
    assert cdr.agent == 1
    assert cdr.call_status == "answered"
    assert cdr.customer_status == "connected"
    assert cdr.agent_status == "connected"
    assert cdr.total_call_duration == 120
    assert cdr.talk_time == 100
    assert cdr.call_actions == ["dial", "answer"]
    assert cdr.call_uuid == "uuid-123"
    assert cdr.hangup_by == "agent"
    assert cdr.call_recording == "http://recording.com/1"
    assert cdr.disposition == "resolved"
    assert cdr.sub_disposition == "success"
    assert cdr.notes == "Customer satisfied"
    assert cdr.voice_email == "customer@example.com"
    assert cdr.dtmf_extension == "1234"
    assert cdr.queue == "support_queue"
    assert cdr.partner_id == 10


def test_cdr_create_missing_optional_fields():
    """Test CDRCreate with missing optional fields."""
    data = {
        "action": "call",
        "calling_mode": "inbound",
        "date_time": 1727181060000,
        "solution": "support",
        "sr_number": "SR123",
        "customer": "9999999999",
        "call_status": "answered",
        "customer_status": "connected",
        "agent_status": "connected",
        "total_call_duration": 120,
        "talk_time": 100,
        "call_actions": ["dial"],
        "call_uuid": "uuid-123",
        "hangup_by": "agent",
    }
    cdr = Contract.CDRCreate(**data)
    assert cdr.agent is None
    assert cdr.call_recording is None
    assert cdr.disposition is None
    assert cdr.sub_disposition is None
    assert cdr.notes is None
    assert cdr.voice_email is None
    assert cdr.dtmf_extension is None
    assert cdr.queue is None
    assert cdr.partner_id is None


def test_cdr_create_invalid_types():
    """Test CDRCreate with invalid types."""
    invalid_data = {
        "action": 123,  # Should be str
        "calling_mode": "inbound",
        "date_time": "invalid",  # Should be int
        "solution": "support",
        "sr_number": "SR123",
        "customer": "9999999999",
        "agent": "invalid",  # Should be int or None
        "call_status": "answered",
        "customer_status": "connected",
        "agent_status": "connected",
        "total_call_duration": "120",  # Should be int
        "talk_time": "100",  # Should be int
        "call_actions": "dial",  # Should be List[str]
        "call_uuid": "uuid-123",
        "hangup_by": "agent",
    }
    with pytest.raises(ValidationError) as exc_info:
        Contract.CDRCreate(**invalid_data)
    exc_info.value.errors()


def test_cdr_response_valid():
    """Test CDRResponse with valid data."""
    data = {
        "id": "12345",
        "action": "call",
        "calling_mode": "inbound",
        "date_time": 1727181060000,
        "solution": "support",
        "sr_number": "SR123",
        "customer": 9999999999,
        "agent": 1,
        "call_status": "answered",
        "customer_status": "connected",
        "agent_status": "connected",
        "total_call_duration": 120,
        "talk_time": 100,
        "call_actions": ["dial", "answer"],
        "call_uuid": "uuid-123",
        "hangup_by": "agent",
        "partner_id": 10,
        "created_at": 1727181060000,
        "updated_at": 1727181061000,
        "call_recording": "http://recording.com/1",
        "disposition": "resolved",
        "sub_disposition": "success",
        "notes": "Customer satisfied",
        "voice_email": "customer@example.com",
        "dtmf_extension": "1234",
        "queue": "support_queue",
        "agent_number": "7777777777",
        "agent_number_with_prefix": "+17777777777",
        "agent_name": "Agent One",
        "client_number": "9999999999",
        "did_number": "8888888888",
        "reason": "Busy",
        "hangup_cause": "USER_BUSY",
        "contact_details": {"name": "John Doe"},
        "missed_agents": [2, 3],
        "call_flow": ["start", "connect"],
        "accountid": "acc123",
        "agent_ring_time": "10",
        "billing_circle": {"type": "monthly"},
        "agent_hangup_data": {"reason": "completed"},
        "transfer_missed_agent": [4],
        "call_hint": "urgent",
        "support_api_call": True,
        "lead_id": "lead123",
        "sid": "sid123",
        "sname": "Service One",
        "is_incoming_from_broadcast": False,
        "caller_id_number": "8888888888",
        "sip_agent_ids": [1, 2],
        "dialer_call_details": {"dialer": "auto"},
        "custom_status": "completed",
        "is_whatsapp": 0,
        "lead_data": [{"id": 1, "name": "John"}],
        "voicemail_recording": False,
        "call_duration": 120,
        "answered_seconds": 100,
        "minutes_consumed": 2,
        "charges": 10,
        "department_name": "Support",
        "detailed_description": "Call handled",
        "start_stamp": "1727181060",
        "end_stamp": "1727181180",
        "ivr_id": "ivr123",
        "ivr_name": "Support IVR",
        "answer_agent_number": "7777777777",
        "answer_stamp": "1727181065",
        "billsec": "100",
        "digits_dialed": "1234",
        "outbound_sec": "10",
        "call_connected": "1",
        "aws_call_recording_identifier": "aws123",
        "campaign_name": "Campaign One",
        "campaign_id": 123,
        "customer_ring_time": "5",
        "reason_key": "BUSY",
    }
    cdr = Contract.CDRResponse(**data)
    assert cdr.id == "12345"
    assert cdr.customer == 9999999999
    assert cdr.total_call_duration == 120
    assert cdr.talk_time == 100
    assert cdr.call_actions == ["dial", "answer"]
    assert cdr.call_recording == "http://recording.com/1"


def test_cdr_response_handle_int_fields():
    """Test CDRResponse with invalid total_call_duration and talk_time."""
    data = {
        "id": "12345",
        "action": "call",
        "calling_mode": "inbound",
        "solution": "support",
        "sr_number": "SR123",
        "call_status": "answered",
        "customer_status": "connected",
        "agent_status": "connected",
        "total_call_duration": 20,
        "talk_time": None,  # Should be converted to 0
        "call_actions": ["dial"],
        "call_uuid": "uuid-123",
        "hangup_by": "agent",
    }
    Contract.CDRResponse(**data)


def test_call_log_response_handle_int_fields():
    """Test CallLogResponse with invalid total_call_duration and talk_time."""
    data = {
        "id": "12345",
        "action": "call",
        "calling_mode": "inbound",
        "solution": "support",
        "sr_number": "SR123",
        "call_status": "answered",
        "customer_status": "connected",
        "agent_status": "connected",
        "total_call_duration": "invalid",  # Should be converted to 0
        "talk_time": None,  # Should be converted to 0
        "call_actions": ["dial"],
        "call_uuid": "uuid-123",
        "hangup_by": "agent",
        "start_stamp": "",  # Should be None
        "end_stamp": "null",  # Should be None
        "answer_stamp": "invalid",  # Should be None
    }
    call_log = Contract.CallLogResponse(**data)
    assert call_log.total_call_duration == 0
    assert call_log.talk_time == 0
    assert call_log.start_stamp is None
    assert call_log.end_stamp is None
    assert call_log.answer_stamp is None


def test_call_log_response_customer_int():
    """Test CallLogResponse with integer customer."""
    data = {
        "id": "12345",
        "action": "call",
        "calling_mode": "inbound",
        "solution": "support",
        "sr_number": "SR123",
        "customer": 9999999999,  # Integer
        "call_status": "answered",
        "customer_status": "connected",
        "agent_status": "connected",
        "total_call_duration": 120,
        "talk_time": 100,
        "call_actions": ["dial"],
        "call_uuid": "uuid-123",
        "hangup_by": "agent",
    }
    call_log = Contract.CallLogResponse(**data)
    assert call_log.customer == 9999999999


def test_call_record_history_response_valid():
    """Test CallRecordHistoryResponse with valid data."""
    data = {
        "partner_id": 10,
        "agent": 1,
        "lead_id": 123,
        "service_board_id": 20,
        "calling_mode": "inbound",
        "call_status": "answered",
        "call_recording": "http://recording.com/1",
        "lead_number": "9999999999",
        "total_call_duration": "120",  # Should be converted to int
        "talk_time": "100",  # Should be converted to int
        "did_number": "8888888888",
        "agent_number": "7777777777",
        "reason": "Busy",
        "hangup_cause": "USER_BUSY",
        "reason_key": "BUSY",
        "hangup_by": "agent",
        "created_at": 1727181060000,
        "action_performed_by": "Agent One",
        "lead_call_status": "connected",
        "agent_call_status": "connected",
        "call_connected": "1",
        "lead_name": "John Doe",
        "call_type": "incoming",
    }
    call_record = Contract.CallRecordHistoryResponse(**data)
    assert call_record.partner_id == 10
    assert call_record.lead_number == "9999999999"
    assert call_record.total_call_duration == 120
    assert call_record.talk_time == 100
    assert call_record.call_type == "incoming"


def test_call_record_history_response_handle_int_fields():
    """Test CallRecordHistoryResponse with invalid total_call_duration and talk_time."""
    data = {
        "partner_id": 10,
        "calling_mode": "inbound",
        "call_status": "answered",
        "hangup_by": "agent",
        "total_call_duration": "invalid",  # Should be converted to 0
        "talk_time": None,  # Should be converted to 0
    }
    call_record = Contract.CallRecordHistoryResponse(**data)
    assert call_record.total_call_duration == 0
    assert call_record.talk_time == 0


def test_call_record_history_response_lead_number_int():
    """Test CallRecordHistoryResponse with integer lead_number."""
    data = {
        "partner_id": 10,
        "calling_mode": "inbound",
        "call_status": "answered",
        "hangup_by": "agent",
        "lead_number": 9999999999,  # Integer
    }
    call_record = Contract.CallRecordHistoryResponse(**data)
    assert call_record.lead_number == 9999999999


def test_agent_call_record_history_response_valid():
    """Test AgentCallRecordHistoryResponse with valid data."""
    call_record = Contract.CallRecordHistoryResponse(
        partner_id=10,
        calling_mode="inbound",
        call_status="answered",
        hangup_by="agent",
    )
    data = {
        "call_record": [call_record],
        "total_count": 1,
    }
    response = Contract.AgentCallRecordHistoryResponse(**data)
    assert response.call_record == [call_record]
    assert response.total_count == 1


def test_agent_call_record_history_response_empty_call_record():
    """Test AgentCallRecordHistoryResponse with non-list call_record."""
    data = {
        "call_record": None,  # Should be converted to []
        "total_count": 0,
    }
    response = Contract.AgentCallRecordHistoryResponse(**data)
    assert response.call_record == []
    assert response.total_count == 0


def test_agent_call_log_response_valid():
    """Test AgentCallLogResponse with valid data."""
    call_log = Contract.CallLogResponse(
        id="12345",
        action="call",
        calling_mode="inbound",
        solution="support",
        sr_number="SR123",
        call_status="answered",
        customer_status="connected",
        agent_status="connected",
        call_actions=["dial"],
        call_uuid="uuid-123",
        hangup_by="agent",
    )
    data = {
        "call_histories": [call_log],
        "total_count": 1,
    }
    response = Contract.AgentCallLogResponse(**data)
    assert response.call_histories == [call_log]
    assert response.total_count == 1


def test_agent_call_log_response_empty_call_histories():
    """Test AgentCallLogResponse with non-list call_histories."""
    data = {
        "call_histories": None,  # Should be converted to []
        "total_count": 0,
    }
    response = Contract.AgentCallLogResponse(**data)
    assert response.call_histories == []
    assert response.total_count == 0


def test_call_record_history_payload_valid():
    """Test CallRecordHistoryPayload with valid data."""
    data = {
        "lead_id": 123,
        "service_board_id": 20,
        "time_range": "1727181060-1727184660",
        "call_status": ["answered", "missed"],
        "agents": [1, 2],
        "phone_number": "9999999999",
        "talk_time_range": ["0_1", "1_3"],
        "call_type": "incoming",
        "did_number": "8888888888",
    }
    payload = Contract.CallRecordHistoryPayload(**data)
    assert payload.lead_id == 123
    assert payload.time_range == "1727181060-1727184660"
    assert payload.call_status == ["answered", "missed"]
    assert payload.call_type == "incoming"


def test_call_record_history_payload_missing_optional_fields():
    """Test CallRecordHistoryPayload with missing optional fields."""
    data = {}
    payload = Contract.CallRecordHistoryPayload(**data)
    assert payload.lead_id is None
    assert payload.service_board_id is None
    assert payload.time_range is None
    assert payload.call_status is None
    assert payload.agents is None
    assert payload.phone_number is None
    assert payload.talk_time_range is None
    assert payload.call_type is None
    assert payload.did_number is None


def test_call_record_history_payload_invalid_call_status():
    """Test CallRecordHistoryPayload with invalid call_status."""
    data = {
        "call_status": ["answered", "invalid"],
    }
    with pytest.raises(
        ValidationError, match=r"Invalid call_status values: \['invalid'\]"
    ):
        Contract.CallRecordHistoryPayload(**data)


def test_call_record_history_payload_invalid_call_type():
    """Test CallRecordHistoryPayload with invalid call_type."""
    data = {
        "call_type": "invalid",
    }
    with pytest.raises(ValidationError, match=r"Invalid call_type: invalid"):
        Contract.CallRecordHistoryPayload(**data)


def test_call_record_history_payload_invalid_time_range_format():
    """Test CallRecordHistoryPayload with invalid time_range format."""
    data = {
        "time_range": "invalid",
    }
    with pytest.raises(
        ValidationError,
        match=r"time_range must be in format 'start_time-end_time' with valid integers",
    ):
        Contract.CallRecordHistoryPayload(**data)


def test_call_record_history_payload_invalid_time_range_values():
    """Test CallRecordHistoryPayload with invalid time_range values."""
    data = {
        "time_range": "abc-xyz",
    }
    with pytest.raises(
        ValidationError,
        match=r"time_range must be in format 'start_time-end_time' with valid integers",
    ):
        Contract.CallRecordHistoryPayload(**data)


def test_call_record_history_payload_time_range_start_greater_than_end():
    """Test CallRecordHistoryPayload with start_time > end_time."""
    data = {
        "time_range": "1727184660-1727181060",  # start > end
    }
    with pytest.raises(
        ValidationError,
        match=r"time_range must be in format 'start_time-end_time' with valid integers",
    ):
        Contract.CallRecordHistoryPayload(**data)
