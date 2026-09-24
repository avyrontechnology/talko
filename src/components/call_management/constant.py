# LEGACY FALLBACK ONLY: used when a partner has enable_ai_bridge=True but no
# ai_vendor_config_id on its partner_config (see
# TalkoCallService._resolve_vendor_config_id, which warns loudly in that case).
# Backfill ai_vendor_config_id per partner; do not reference this directly.
AI_BRIDGE_VENDOR_CONFIG_ID = "6a902efa7157c16288fc8087"

TATA_WEBHOOK_FIELD_MAPPINGS = {
    "start_stamp": "start_stamp",
    "billing_circle": "billing_circle",
    "caller_id_number": "caller_id_number",
    "ivr_id": "ivr_id",
    "ivr_name": "ivr_name",
    "agent_number": "agent_number",
    "answer_agent_number": "answer_agent_number",
    "call_status": "call_status",
    "direction": "calling_mode",
    "uuid": "call_uuid",
    "answer_stamp": "answer_stamp",
    "end_stamp": "end_stamp",
    "hangup_cause": "hangup_cause",
    "billsec": "billsec",
    "digits_dialed": "digits_dialed",
    "duration": "total_call_duration",
    "answered_agent_number": "answered_agent_number",
    "missed_agent": "missed_agent",
    "call_flow": "call_flow",
    "broadcast_lead_fields": "broadcast_lead_fields",
    "recording_url": "call_recording",
    "agent_ring_time": "agent_ring_time",
    "call_connected": "call_connected",
    "aws_call_recording_identifier": "aws_call_recording_identifier",
    "campaign_name": "campaign_name",
    "campaign_id": "campaign_id",
    "customer_ring_time": "customer_ring_time",
    "reason_key": "reason_key",
    "customer_status": "customer_status",
    "status": "status",
    "outbound_sec": "talk_time",
}

TATA_CDR_FIELD_MAPPING = {
    # Basic identifiers
    "uuid": "call_uuid",
    "direction": "calling_mode",
    "status": "call_status",
    "did_number": "did_number",
    "caller_id_num": "caller_id_number",
    "agent_number": "agent_number",
    "agent_number_with_prefix": "agent_number_with_prefix",
    "agent_name": "agent_name",
    "client_number": "client_number",
    "accountid": "accountid",
    # Call durations
    "call_duration": "total_call_duration",  # From payload's 'call_duration'
    "answered_seconds": "talk_time",  # From payload's 'answered_seconds'
    # Timestamps
    "start_stamp": "start_stamp",
    "end_stamp": "end_stamp",
    "answer_stamp": "answer_stamp",
    # Call status / reason
    "hangup_cause": "hangup_cause",
    "reason": "reason",
    "reason_key": "reason_key",
    # Recordings
    "recording_url": "call_recording",
    "aws_call_recording_identifier": "aws_call_recWording_identifier",
    # Metadata / agent info
    "ivr_id": "ivr_id",
    "ivr_name": "ivr_name",
    "answer_agent_number": "answer_agent_number",
    "agent_ring_time": "agent_ring_time",
    # Campaign / broadcast
    "campaign_name": "campaign_name",
    "campaign_id": "campaign_id",
    "broadcast_lead_fields": "broadcast_lead_fields",
    # Call flow & participants
    "call_flow": "call_flow",
    "missed_agents": "missed_agents",
    "contact_details": "contact_details",
    # Customer & agent statuses
    "customer_status": "customer_status",
    "agent_status": "agent_status",
    # Additional / optional fields
    "billsec": "billsec",
    "digits_dialed": "digits_dialed",
    "call_connected": "call_connected",
    "customer_ring_time": "customer_ring_time",
    "custom_status": "custom_status",
    "voice_email": "voice_email",
    "dtmf_input": "dtmf_extension",
}

WEBHOOK = "webhook"
SIMULTANEOUS = "simultaneous"
ORDERBY = "order_by"
API = "api"


# OTOBA CDR API field mapping (OTOBA key -> TalkoCDR field).
# Covers OTOBA's documented snake_case keys plus the camelCase variants
# seen in the wild; unknown keys are ignored downstream. Mirrors the
# shape of TATA_CDR_FIELD_MAPPING so the same _process_payload logic applies
# after normalization in TalkoOtobaWebhookHandler.
OTOBA_CDR_FIELD_MAPPING = {
    "call_id": "call_id",
    "callId": "call_id",
    "uuid": "call_uuid",
    "call_uuid": "call_uuid",
    "callUuid": "call_uuid",
    "direction": "calling_mode",
    "call_direction": "calling_mode",
    "status": "call_status",
    "call_status": "call_status",
    "callStatus": "call_status",
    "did_number": "did_number",
    "didNumber": "did_number",
    "caller_id_number": "caller_id_number",
    "callerIdNumber": "caller_id_number",
    "agent_number": "agent_number",
    "agentNumber": "agent_number",
    "agent_name": "agent_name",
    "agentName": "agent_name",
    "customer_number": "customer",
    "customerNumber": "customer",
    "client_number": "client_number",
    "duration": "total_call_duration",
    "call_duration": "total_call_duration",
    "callDuration": "total_call_duration",
    "billsec": "billsec",
    "billSec": "billsec",
    "answered_seconds": "talk_time",
    "answeredSeconds": "talk_time",
    "talk_time": "talk_time",
    "start_stamp": "start_stamp",
    "startTime": "start_stamp",
    "end_stamp": "end_stamp",
    "endTime": "end_stamp",
    "answer_stamp": "answer_stamp",
    "answerTime": "answer_stamp",
    "hangup_cause": "hangup_cause",
    "hangupCause": "hangup_cause",
    "reason_key": "reason_key",
    "reasonKey": "reason_key",
    "recording_url": "call_recording",
    "recordingUrl": "call_recording",
    "customer_status": "customer_status",
    "agent_status": "agent_status",
}


DIALER_FIELD_MAPPING = {
    # Core identifiers
    "call_id": "call_id",
    "uuid": "call_uuid",
    "call_to_number": "customer",
    "caller_id_number": "did_number",
    "customer_no_with_prefix": "customer_no_with_prefix",
    # Timestamps (will be converted later)
    "start_stamp": "start_stamp",
    "answer_stamp": "answer_stamp",
    "end_stamp": "end_stamp",
    # Durations
    "billsec": "billsec",
    "outbound_sec": "talk_time",
    "duration": "total_call_duration",
    "agent_ring_time": "agent_ring_time",
    "customer_ring_time": "customer_ring_time",
    # Status & cause
    "call_status": "call_status",
    "reason_key": "reason_key",
    "hangup_cause_key": "hangup_cause_key",
    "hangup_cause_description": "hangup_cause_description",
    "hangup_cause_code": "hangup_cause",
    "hangup_cause": "hangup_cause",
    # Agent info
    "answered_agent": "answered_agent",
    "answered_agent_name": "answered_agent_name",
    "answered_agent_number": "answered_agent_number",
    "missed_agent": "missed_agents",
    # Campaign / lead context
    "campaign_id": "campaign_id",
    "campaign_name": "campaign_name",
    "broadcast_lead_fields": "broadcast_lead_fields",
    # Recording
    "recording_url": "call_recording",
    "aws_call_recording_identifier": "aws_call_recording_identifier",
    # PCA
    "stt": "stt",
    "llm_analysis": "llm_analysis",
    "call_hint": "call_hint",
    # Disposition
    "disposition": "disposition",
    "sub_disposition": "sub_disposition",
    "schedule_timestamp": "schedule_timestamp",
    "schedule_assigned_agent_id": "schedule_assigned_agent_id",
    "schedule_note": "schedule_note",
}
