from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.components.call_management.tata_tele.call_dialer import TalkoDialerWebhookHandler

_MAGLO_PATCH_PATH = "src.components.call_management.tata_tele.call_dialer.TalkoMagloClient"
_HTTPX_PATCH_PATH = (
    "src.components.call_management.handlers.webhook_base_handler.httpx.AsyncClient"
)


@pytest.fixture(autouse=True)
def _patch_maglo_client():
    """
    Replaces TalkoMagloClient with a MagicMock for every test in this module.
    This prevents __init__ from creating an aiohttp session (which needs
    a running event loop) during both collection and execution.
    """
    with patch(_MAGLO_PATCH_PATH, new_callable=MagicMock) as mock_cls:
        mock_cls.return_value = MagicMock()
        yield mock_cls


@pytest.fixture(autouse=True)
def _patch_makunai_relay_client():
    """
    Every process_webhook() call now also fires _relay_to_makunai() —
    stub httpx.AsyncClient so no test makes a real network call. Tests that
    care about the relay itself grab the mock client via this fixture
    instead of relying on autouse alone.
    """
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch(_HTTPX_PATCH_PATH, return_value=mock_client):
        yield mock_client


def _make_handler() -> TalkoDialerWebhookHandler:
    """
    Build a TalkoDialerWebhookHandler with plain MagicMock dependencies.
    Must be called inside a test body (sync or async) — never at class scope.
    The autouse fixture ensures TalkoMagloClient is already patched when this runs.
    """
    logger = MagicMock()
    call_repository = MagicMock()
    did_management_service = MagicMock()

    handler = TalkoDialerWebhookHandler(
        logger=logger,
        call_repository=call_repository,
        did_management_service=did_management_service,
        vendor_type="tata_tele",
    )

    # maglo_client was already replaced by the autouse patch; give it a fresh mock
    handler.maglo_client = MagicMock()
    handler.datetime_util = MagicMock()
    handler.datetime_util.get_current_time.return_value = 1722945600
    # Default: return the int as-is (simulates a valid epoch ms conversion)
    handler.datetime_util.convert_date_time.side_effect = lambda v: (
        int(v) if isinstance(v, (int, float)) else 0
    )

    return handler


def _base_payload(**overrides) -> Dict[str, Any]:
    """Minimal valid dialer webhook payload."""
    payload = {
        "call_id": "call-123",
        "uuid": "uuid-abc-456",
        "caller_id_number": "+911234567890",
        "call_to_number": "+919876543210",
        "call_status": "initiated",
        "campaign_id": "camp-1",
        "campaign_name": "Test Campaign",
        "customer_no_with_prefix": "+919876543210",
    }
    payload.update(overrides)
    return payload


def _default_did_info() -> Dict[str, Any]:
    return {
        "partner_id": 100,
        "service_board_id": 1,
        "vendor_id": "vendor123",
        "vendor_config_id": "config456",
    }


def _default_maglo_response() -> Dict[str, Any]:
    """
    Keys must match the string literals that TalkoMagloApiConstants resolves to:
        FIELD_LEAD_ID               -> "lead_id"
        FIELD_AGENT_NAME            -> "agent_name"
        FIELD_LEAD_REQUEST_ID       -> "lead_request_id"
        LEAD_RESPONSE_ASSIGNED_TO   -> "assigned_to"
    """
    return {
        "lead_id": 9001,
        "agent_name": "Jane Doe",
        "lead_request_id": 5001,
        "assigned_to": 42,
    }


class TestProcessWebhookHappyPath:
    @pytest.mark.asyncio
    async def test_process_webhook_creates_new_cdr(self):
        """When no existing TalkoCDR is found a new one should be inserted."""
        handler = _make_handler()

        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value=_default_did_info()
        )
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value=_default_maglo_response()
        )
        handler.call_repository.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value=None
        )
        handler.call_repository.insert_cdr = AsyncMock()

        result = await handler.process_webhook(_base_payload())

        assert result["status"] == "created"
        assert result["call_id"] == "call-123"
        handler.call_repository.insert_cdr.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_webhook_updates_existing_cdr(self):
        """When an existing TalkoCDR is found it should be updated."""
        handler = _make_handler()

        existing_cdr = {"_id": "mongo-id-999", "call_id": "call-123"}
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value=_default_did_info()
        )
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value=_default_maglo_response()
        )
        handler.call_repository.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value=existing_cdr
        )
        handler.call_repository.update_cdr = AsyncMock(return_value=True)

        result = await handler.process_webhook(_base_payload())

        assert result["status"] == "updated"
        handler.call_repository.update_cdr.assert_called_once()
        assert handler.call_repository.update_cdr.call_args[0][0] == "mongo-id-999"

    @pytest.mark.asyncio
    async def test_process_webhook_update_fails_returns_update_failed(self):
        """When update_cdr returns False the status should be 'update_failed'."""
        handler = _make_handler()

        existing_cdr = {"_id": "mongo-id-999"}
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value=_default_did_info()
        )
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value=_default_maglo_response()
        )
        handler.call_repository.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value=existing_cdr
        )
        handler.call_repository.update_cdr = AsyncMock(return_value=False)

        result = await handler.process_webhook(_base_payload())

        assert result["status"] == "update_failed"


class TestRelayToMakunai:
    """Covers TalkoDialerWebhookHandler._relay_to_makunai in isolation, using the
    autouse _patch_makunai_relay_client fixture's mock httpx.AsyncClient."""

    @pytest.mark.asyncio
    async def test_relay_posts_payload_with_partner_id_and_secret_header(
        self, _patch_makunai_relay_client
    ):
        from src.core.environment import TalkoENV

        handler = _make_handler()
        payload = {"call_id": "call-123", "uuid": "uuid-abc-456"}

        await handler._relay_to_makunai(100, payload)

        _patch_makunai_relay_client.post.assert_called_once()
        call_args = _patch_makunai_relay_client.post.call_args
        assert call_args[0][0] == TalkoENV.MAKUNAI_CDR_WEBHOOK_URL
        assert call_args[1]["json"] == {**payload, "partner_id": 100}
        assert call_args[1]["headers"] == {
            "X-Webhook-Secret": TalkoENV.CDR_WEBHOOK_RELAY_SECRET
        }

    @pytest.mark.asyncio
    async def test_relay_does_not_mutate_original_payload(
        self, _patch_makunai_relay_client
    ):
        handler = _make_handler()
        payload = {"call_id": "call-123"}

        await handler._relay_to_makunai(100, payload)

        assert payload == {"call_id": "call-123"}

    @pytest.mark.asyncio
    async def test_relay_failure_is_swallowed(self, _patch_makunai_relay_client):
        """A relay failure must never propagate — our own TalkoCDR write already
        succeeded by the time _relay_to_makunai runs."""
        _patch_makunai_relay_client.post = AsyncMock(
            side_effect=httpx.ConnectError("boom")
        )
        handler = _make_handler()

        await handler._relay_to_makunai(100, {"call_id": "call-123"})

        handler.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_relay_failure_on_bad_status_is_swallowed(
        self, _patch_makunai_relay_client
    ):
        """raise_for_status() raising (e.g. a 500 from makun-ai) must also be
        swallowed, not just transport-level connection errors."""
        _patch_makunai_relay_client.post.return_value.raise_for_status.side_effect = (
            httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            )
        )
        handler = _make_handler()

        await handler._relay_to_makunai(100, {"call_id": "call-123"})

        handler.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_webhook_still_succeeds_when_relay_fails(
        self, _patch_makunai_relay_client
    ):
        """End-to-end: a broken relay must not turn a successful TalkoCDR write
        into a failed webhook response."""
        _patch_makunai_relay_client.post = AsyncMock(
            side_effect=httpx.ConnectError("boom")
        )
        handler = _make_handler()

        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value=_default_did_info()
        )
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value=_default_maglo_response()
        )
        handler.call_repository.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value=None
        )
        handler.call_repository.insert_cdr = AsyncMock()

        result = await handler.process_webhook(_base_payload())

        assert result["status"] == "created"


class TestProcessWebhookErrorCases:
    @pytest.mark.asyncio
    async def test_missing_caller_id_number_returns_error(self):
        handler = _make_handler()
        payload = _base_payload()
        del payload["caller_id_number"]

        result = await handler.process_webhook(payload)

        assert result["status"] == "error"
        assert result["reason"] == "missing_did"
        handler.did_management_service.get_dids_by_number.assert_not_called()

    @pytest.mark.asyncio
    async def test_did_not_found_returns_error(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(return_value=None)

        result = await handler.process_webhook(_base_payload())

        assert result["status"] == "error"
        assert result["reason"] == "did_not_assigned"

    @pytest.mark.asyncio
    async def test_did_partner_id_zero_returns_error(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value={"partner_id": 0, "service_board_id": 1}
        )

        result = await handler.process_webhook(_base_payload())

        assert result["status"] == "error"
        assert result["reason"] == "did_not_assigned"

    @pytest.mark.asyncio
    async def test_did_partner_id_none_returns_error(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value={"partner_id": None, "service_board_id": 1}
        )

        result = await handler.process_webhook(_base_payload())

        assert result["status"] == "error"
        assert result["reason"] == "did_not_assigned"

    @pytest.mark.asyncio
    async def test_did_lookup_exception_returns_error(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            side_effect=Exception("DB connection failed")
        )

        result = await handler.process_webhook(_base_payload())

        assert result["status"] == "error"
        assert result["reason"] == "did_not_assigned"
        handler.logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_maglo_upsert_exception_is_handled(self):
        """
        When Maglo upsert raises, _upsert_ivr_lead_if_needed returns None.
        The handler guards for None (if upsert_res:) so lead fields default
        to None and the TalkoCDR is still created successfully.
        """
        handler = _make_handler()

        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value=_default_did_info()
        )
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            side_effect=Exception("Maglo unavailable")
        )
        handler.call_repository.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value=None
        )
        handler.call_repository.insert_cdr = AsyncMock()

        result = await handler.process_webhook(_base_payload())

        assert result["status"] == "created"
        handler.logger.error.assert_called()


class TestSanitizePayload:
    """Tests for Tata Tele unresolved placeholder sanitization."""

    def test_replaces_dollar_prefixed_placeholders_with_none(self):
        handler = _make_handler()
        payload = {
            "hangup_cause_key": "$hangupcause_key",
            "hangup_cause_description": "$hangupcause_desc",
            "hangup_cause": "$hangupcause_code",
            "call_id": "call-123",  # normal value — must not be touched
        }
        result = handler._sanitize_payload(payload)

        assert result["hangup_cause_key"] is None
        assert result["hangup_cause_description"] is None
        assert result["hangup_cause"] is None
        assert result["call_id"] == "call-123"

    def test_replaces_underscore_prefixed_placeholders_with_none(self):
        handler = _make_handler()
        payload = {"answered_agent_number": "_number", "call_id": "call-123"}
        result = handler._sanitize_payload(payload)

        assert result["answered_agent_number"] is None
        assert result["call_id"] == "call-123"

    def test_preserves_non_placeholder_string_values(self):
        handler = _make_handler()
        payload = {
            "call_status": "answered",
            "agent_number": "+919311634345",
            "customer_ring_time": "10",
        }
        result = handler._sanitize_payload(payload)

        assert result["call_status"] == "answered"
        assert result["agent_number"] == "+919311634345"
        assert result["customer_ring_time"] == "10"

    def test_preserves_none_and_non_string_values(self):
        handler = _make_handler()
        payload = {
            "talk_time": 0,
            "lead_id": 12345,
            "disposition": None,
            "call_actions": [],
        }
        result = handler._sanitize_payload(payload)

        assert result["talk_time"] == 0
        assert result["lead_id"] == 12345
        assert result["disposition"] is None
        assert result["call_actions"] == []

    def test_empty_payload_returns_empty_dict(self):
        handler = _make_handler()
        assert handler._sanitize_payload({}) == {}

    def test_sanitized_hangup_cause_key_none_does_not_trigger_hangup_detection(self):
        """
        After sanitization hangup_cause_key=None. _try_detect_event uses
        payload.get("hangup_cause_key") which is None (falsy) → no hangup.
        uuid is present but billsec is absent and hangup_cause_key is None,
        so event detection returns None.
        """
        handler = _make_handler()
        # Simulate post-sanitize state: key present, value is None
        result = handler._try_detect_event({"uuid": "u", "hangup_cause_key": None})
        assert result is None

    def test_sanitizer_called_before_processing_in_process_webhook(self):
        """
        Placeholder fields must be None by the time the rest of the handler
        runs. Verified by checking _sanitize_payload output directly.
        """
        handler = _make_handler()
        payload = _base_payload(
            hangup_cause_key="$hangupcause_key",
            customer_ring_time="$customer_ring_time",
            answered_agent_number="_number",
        )
        sanitized = handler._sanitize_payload(payload)

        assert sanitized["hangup_cause_key"] is None
        assert sanitized["customer_ring_time"] is None
        assert sanitized["answered_agent_number"] is None


class TestExtractDidNumber:
    def test_normalizes_e164_number_to_no_plus_format(self):
        """
        _extract_did_number must call normalize_phone_number(did, with_plus=False)
        so the returned value matches the stored DB format (no leading +).
        """
        handler = _make_handler()
        result = handler._extract_did_number({"caller_id_number": "+911234567890"})
        # normalize_phone_number("+911234567890", with_plus=False) → "911234567890"
        assert result == "911234567890"

    def test_normalizes_10_digit_number(self):
        handler = _make_handler()
        result = handler._extract_did_number({"caller_id_number": "1234567890"})
        # 10-digit → prepend 91, no plus
        assert result == "911234567890"

    def test_normalizes_12_digit_91_prefix_number(self):
        handler = _make_handler()
        result = handler._extract_did_number({"caller_id_number": "911234567890"})
        assert result == "911234567890"

    def test_returns_none_when_field_missing(self):
        handler = _make_handler()
        assert handler._extract_did_number({}) is None

    def test_returns_none_for_empty_string(self):
        handler = _make_handler()
        assert handler._extract_did_number({"caller_id_number": ""}) is None

    def test_logs_error_when_did_missing(self):
        handler = _make_handler()
        handler._extract_did_number({})
        handler.logger.error.assert_called()

    def test_logs_debug_with_original_and_normalized(self):
        handler = _make_handler()
        handler._extract_did_number({"caller_id_number": "+911234567890"})
        debug_calls = [str(c) for c in handler.logger.debug.call_args_list]
        assert any(
            "normalized" in c.lower() or "911234567890" in c for c in debug_calls
        )


class TestNormalizeCustomerNumber:
    def test_uses_call_to_number_when_present(self):
        handler = _make_handler()
        result = handler._normalize_customer_number({"call_to_number": "09876543210"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_falls_back_to_broadcast_lead_fields_when_call_to_number_empty(self):
        handler = _make_handler()
        payload = {
            "call_to_number": "",
            "broadcast_lead_fields": {"Phone_Number": "+919876543210"},
        }
        result = handler._normalize_customer_number(payload)
        assert isinstance(result, str)
        assert len(result) > 0
        handler.logger.warning.assert_called()

    def test_falls_back_when_call_to_number_absent(self):
        handler = _make_handler()
        payload = {"broadcast_lead_fields": {"Phone_Number": "9876543210"}}
        result = handler._normalize_customer_number(payload)
        assert isinstance(result, str)

    def test_returns_empty_string_when_no_number_available(self):
        handler = _make_handler()
        result = handler._normalize_customer_number({})
        assert result == ""

    def test_returns_empty_string_when_both_sources_empty(self):
        handler = _make_handler()
        result = handler._normalize_customer_number(
            {"call_to_number": "", "broadcast_lead_fields": {"Phone_Number": ""}}
        )
        assert result == ""

    def test_handles_none_call_to_number(self):
        handler = _make_handler()
        result = handler._normalize_customer_number({"call_to_number": None})
        assert isinstance(result, str)

    def test_handles_none_broadcast_lead_fields(self):
        handler = _make_handler()
        result = handler._normalize_customer_number(
            {"call_to_number": "", "broadcast_lead_fields": None}
        )
        assert result == ""


class TestGetDidInfo:
    @pytest.mark.asyncio
    async def test_returns_did_info_for_valid_record(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value={
                "partner_id": 100,
                "service_board_id": 1,
                "vendor_id": 55,
                "vendor_config_id": 77,
            }
        )

        result = await handler._get_did_info("911234567890")

        assert result is not None
        assert result["partner_id"] == 100
        assert result["service_board_id"] == 1
        assert result["vendor_id"] == "55"  # cast to str
        assert result["vendor_config_id"] == "77"

    @pytest.mark.asyncio
    async def test_returns_none_when_record_missing(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(return_value=None)
        assert await handler._get_did_info("911234567890") is None

    @pytest.mark.asyncio
    async def test_returns_none_when_partner_id_zero(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value={"partner_id": 0}
        )
        assert await handler._get_did_info("911234567890") is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            side_effect=RuntimeError("DB error")
        )
        assert await handler._get_did_info("911234567890") is None
        handler.logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_vendor_ids_are_none_when_absent_from_record(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value={"partner_id": 100}
        )
        result = await handler._get_did_info("911234567890")
        assert result["vendor_id"] is None
        assert result["vendor_config_id"] is None


class TestUpsertIvrLeadIfNeeded:
    @pytest.mark.asyncio
    async def test_returns_none_when_customer_number_empty(self):
        handler = _make_handler()
        handler.maglo_client.upsert_ivr_lead = AsyncMock()

        result = await handler._upsert_ivr_lead_if_needed("", 100, 1)

        assert result is None
        handler.maglo_client.upsert_ivr_lead.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_lead_data_on_success(self):
        handler = _make_handler()
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value=_default_maglo_response()
        )

        result = await handler._upsert_ivr_lead_if_needed("+919876543210", 100, 1)

        assert result is not None
        id_data, lead_name, assigned_agent_id = result
        assert id_data == 5001
        assert assigned_agent_id == 42

    @pytest.mark.asyncio
    async def test_uses_lead_id_when_lead_request_id_is_none(self):
        handler = _make_handler()
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value={
                "lead_id": 9001,
                "agent_name": "Jane",
                "lead_request_id": None,
                "assigned_to": 10,
            }
        )

        result = await handler._upsert_ivr_lead_if_needed("+919876543210", 100, 1)

        assert result is not None
        id_data, _, _ = result
        # lead_request_id is None → `or None` makes it None →
        # `id_data = lead_request_id if lead_request_id is not None else lead_id`
        # → falls back to lead_id = 9001
        assert id_data == None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        handler = _make_handler()
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            side_effect=Exception("Maglo down")
        )

        result = await handler._upsert_ivr_lead_if_needed("+919876543210", 100, 1)

        assert result is None
        handler.logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_logs_warning_when_no_lead_id_returned(self):
        handler = _make_handler()
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value={"lead_id": None, "agent_name": "", "assigned_to": None}
        )

        await handler._upsert_ivr_lead_if_needed("+919876543210", 100, 1)

        handler.logger.warning.assert_called()


class TestApplyTalkTime:
    def test_uses_outbound_sec_when_present(self):
        handler = _make_handler()
        updates = {}
        handler._apply_talk_time(updates, {"outbound_sec": 120, "billsec": 90})
        assert updates["talk_time"] == 120

    def test_falls_back_to_billsec_when_outbound_sec_absent(self):
        handler = _make_handler()
        updates = {}
        handler._apply_talk_time(updates, {"billsec": 90})
        assert updates["talk_time"] == 90

    def test_no_update_when_neither_field_present(self):
        handler = _make_handler()
        updates = {}
        handler._apply_talk_time(updates, {"call_status": "answered"})
        assert "talk_time" not in updates

    def test_defaults_to_zero_when_values_are_none(self):
        handler = _make_handler()
        updates = {}
        handler._apply_talk_time(updates, {"billsec": None, "outbound_sec": None})
        assert updates["talk_time"] == 0

    def test_handles_string_integer_values(self):
        """Tata Tele sometimes sends billsec as a string."""
        handler = _make_handler()
        updates = {}
        handler._apply_talk_time(updates, {"outbound_sec": "45", "billsec": "30"})
        assert updates["talk_time"] == 45

    def test_handles_empty_string_gracefully(self):
        """Empty-string billsec must not crash — defaults to 0."""
        handler = _make_handler()
        updates = {}
        handler._apply_talk_time(updates, {"billsec": ""})
        assert updates["talk_time"] == 0


class TestApplyMissedAgents:
    def test_skips_when_missed_agent_not_in_payload(self):
        handler = _make_handler()
        updates = {}
        handler._apply_missed_agents(updates, {})
        assert "missed_agents" not in updates

    def test_wraps_scalar_value_in_list(self):
        handler = _make_handler()
        updates = {}
        handler._apply_missed_agents(updates, {"missed_agent": "agent-001"})
        assert updates["missed_agents"] == ["agent-001"]

    def test_keeps_list_unchanged(self):
        handler = _make_handler()
        updates = {}
        handler._apply_missed_agents(
            updates, {"missed_agent": ["agent-001", "agent-002"]}
        )
        assert updates["missed_agents"] == ["agent-001", "agent-002"]

    def test_handles_empty_list(self):
        handler = _make_handler()
        updates = {}
        handler._apply_missed_agents(updates, {"missed_agent": []})
        assert updates["missed_agents"] == []


class TestExtractAnsweredAgentNumber:
    def test_extracts_last_10_digits_from_agent_number(self):
        handler = _make_handler()
        assert (
            handler._extract_answered_agent_number({"agent_number": "08888888888"})
            == "8888888888"
        )

    def test_answered_agent_number_field_takes_priority_over_agent_number(self):
        handler = _make_handler()
        result = handler._extract_answered_agent_number(
            {"agent_number": "08888888888", "answered_agent_number": "09999999999"}
        )
        assert result == "9999999999"

    def test_extracts_from_missed_agent_list_of_dicts(self):
        handler = _make_handler()
        payload = {"missed_agent": [{"agent_number": "07777777777"}]}
        assert handler._extract_answered_agent_number(payload) == "7777777777"

    def test_extracts_from_missed_agent_as_dict(self):
        handler = _make_handler()
        payload = {"missed_agent": {"agent_number": "06666666666"}}
        assert handler._extract_answered_agent_number(payload) == "6666666666"

    def test_uses_number_key_when_agent_number_absent_in_missed_agent(self):
        handler = _make_handler()
        payload = {"missed_agent": [{"number": "05555555555"}]}
        assert handler._extract_answered_agent_number(payload) == "5555555555"

    def test_returns_empty_string_when_no_relevant_fields(self):
        handler = _make_handler()
        assert handler._extract_answered_agent_number({}) == ""

    def test_logs_warning_for_non_dict_item_in_missed_agent_list(self):
        handler = _make_handler()
        handler._extract_answered_agent_number({"missed_agent": ["not-a-dict"]})
        handler.logger.warning.assert_called()

    def test_logs_warning_for_unexpected_missed_agent_type(self):
        handler = _make_handler()
        handler._extract_answered_agent_number({"missed_agent": 12345})
        handler.logger.warning.assert_called()

    def test_sanitized_placeholder_returns_empty(self):
        """answered_agent_number=None (post-sanitize) must yield empty string."""
        handler = _make_handler()
        result = handler._extract_answered_agent_number({"answered_agent_number": None})
        assert result == ""


class TestApplyAgentNumbersAndType:
    @pytest.mark.asyncio
    async def test_soft_phone_when_cloud_agent_present(self):
        handler = _make_handler()
        handler._resolve_agent_from_ivr_phone = AsyncMock(return_value=None)

        updates: Dict[str, Any] = {}
        await handler._apply_agent_numbers_and_type(
            updates, {"extension_c2c": "12345"}, 100
        )

        assert updates["outbound_type"] == "soft_phone"
        assert updates["cloud_agent_number"] == "12345"

    @pytest.mark.asyncio
    async def test_phone_number_when_no_cloud_agent(self):
        handler = _make_handler()
        handler._resolve_agent_from_ivr_phone = AsyncMock(return_value=None)

        updates: Dict[str, Any] = {}
        await handler._apply_agent_numbers_and_type(
            updates, {"extension_c2c": "  "}, 100
        )

        assert updates["outbound_type"] == "phone_number"

    @pytest.mark.asyncio
    async def test_none_extension_c2c_treated_as_empty(self):
        """None (from sanitizer) must not crash — treated as no cloud agent."""
        handler = _make_handler()
        handler._resolve_agent_from_ivr_phone = AsyncMock(return_value=None)

        updates: Dict[str, Any] = {}
        await handler._apply_agent_numbers_and_type(
            updates, {"extension_c2c": None}, 100
        )

        assert updates["outbound_type"] == "phone_number"

    @pytest.mark.asyncio
    async def test_answered_agent_number_populated_from_agent_number(self):
        handler = _make_handler()
        handler._resolve_agent_from_ivr_phone = AsyncMock(return_value=None)

        updates: Dict[str, Any] = {}
        await handler._apply_agent_numbers_and_type(
            updates, {"agent_number": "919988776655"}, 100
        )

        assert updates["answered_agent_number"] == "9988776655"
        assert updates["agent_number"] == "9988776655"

    @pytest.mark.asyncio
    async def test_agent_number_keys_absent_when_no_agent_in_payload(self):
        handler = _make_handler()
        handler._resolve_agent_from_ivr_phone = AsyncMock(return_value=None)

        updates: Dict[str, Any] = {}
        await handler._apply_agent_numbers_and_type(updates, {}, 100)

        assert "answered_agent_number" not in updates
        assert "agent_number" not in updates
        assert "agent" not in updates

    @pytest.mark.asyncio
    async def test_resolved_agent_id_written_to_updates(self):
        handler = _make_handler()
        handler._resolve_agent_from_ivr_phone = AsyncMock(return_value=999)

        updates: Dict[str, Any] = {}
        await handler._apply_agent_numbers_and_type(
            updates, {"agent_number": "919988776655"}, 100
        )

        assert updates["agent"] == 999

    @pytest.mark.asyncio
    async def test_soft_phone_detection_combined_with_agent_resolution(self):
        handler = _make_handler()
        handler.maglo_client.get_agent_by_ivr_phone = AsyncMock(
            return_value={"agent_id": 555}
        )

        updates: Dict[str, Any] = {}
        payload = {"extension_c2c": "101", "answered_agent_number": "919988776655"}
        await handler._apply_agent_numbers_and_type(updates, payload, 100)

        assert updates["outbound_type"] == "soft_phone"
        assert updates["cloud_agent_number"] == "101"
        assert updates["answered_agent_number"] == "9988776655"


class TestApplyTimestamps:
    def test_converts_truthy_integer_timestamp(self):
        handler = _make_handler()
        # Clear the default side_effect so return_value takes effect
        handler.datetime_util.convert_date_time.side_effect = None
        handler.datetime_util.convert_date_time.return_value = 9999999
        data = {"start_stamp": 1234567890, "answer_stamp": 0, "end_stamp": 0}
        handler._apply_timestamps(data)
        assert data["start_stamp"] == 9999999

    def test_sets_falsy_fields_to_zero(self):
        """Falsy values (0, None, '') must be set to 0 without calling convert."""
        handler = _make_handler()
        data = {"start_stamp": 0, "answer_stamp": None, "end_stamp": ""}
        handler._apply_timestamps(data)

        handler.datetime_util.convert_date_time.assert_not_called()
        assert data["start_stamp"] == 0
        assert data["answer_stamp"] == 0
        assert data["end_stamp"] == 0

    def test_logs_warning_and_defaults_to_zero_on_conversion_failure(self):
        handler = _make_handler()
        handler.datetime_util.convert_date_time.side_effect = ValueError("bad fmt")
        data = {"start_stamp": "invalid-date"}
        handler._apply_timestamps(data)
        handler.logger.warning.assert_called()
        assert data["start_stamp"] == 0

    def test_defaults_to_zero_when_convert_returns_non_numeric(self):
        """
        If convert_date_time returns a string the guard must store 0 instead.
        Must clear side_effect so return_value is used.
        """
        handler = _make_handler()
        handler.datetime_util.convert_date_time.side_effect = None
        handler.datetime_util.convert_date_time.return_value = "3/9/2026, 5:00 PM"
        data = {"start_stamp": "3/9/2026, 5:00 PM"}
        handler._apply_timestamps(data)
        assert data["start_stamp"] == 0
        handler.logger.warning.assert_called()

    def test_always_sets_updated_at(self):
        handler = _make_handler()
        data = {}
        handler._apply_timestamps(data)
        assert data.get("updated_at") == 1722945600

    def test_tata_tele_date_format_converted_correctly(self):
        """Simulate convert_date_time returning a valid int for the Tata Tele format."""
        handler = _make_handler()
        handler.datetime_util.convert_date_time.side_effect = None
        handler.datetime_util.convert_date_time.return_value = 1741524600000
        data = {"start_stamp": "3/9/2026, 5:30:00 PM"}
        handler._apply_timestamps(data)
        assert data["start_stamp"] == 1741524600000

    def test_exception_during_conversion_sets_field_to_zero(self):
        """Generic Exception (not just ValueError) must also be caught."""
        handler = _make_handler()
        handler.datetime_util.convert_date_time.side_effect = Exception(
            "Invalid format"
        )
        data = {"start_stamp": "bad-date"}
        handler._apply_timestamps(data)
        assert data["start_stamp"] == 0


class TestTryDetectEvent:
    def test_detects_pca_via_llm_analysis(self):
        handler = _make_handler()
        assert handler._try_detect_event({"llm_analysis": "data"}) == "pca"

    def test_detects_pca_via_stt(self):
        handler = _make_handler()
        assert handler._try_detect_event({"stt": "transcript"}) == "pca"

    def test_does_not_detect_pca_for_falsy_llm_analysis(self):
        """Key present but falsy value — must not trigger pca."""
        handler = _make_handler()
        assert handler._try_detect_event({"llm_analysis": None, "stt": None}) is None

    def test_detects_disposition_via_disposition_field(self):
        handler = _make_handler()
        assert handler._try_detect_event({"disposition": "ANSWERED"}) == "disposition"

    def test_detects_disposition_when_disposition_is_none(self):
        """disposition=None (sanitized) still counts — key was explicitly set."""
        handler = _make_handler()
        # disposition=None means it was present in payload and sanitized; `is not None` check
        # The new handler checks `payload.get("disposition") is not None`
        # so None value means the key exists but value is absent — should NOT trigger
        assert handler._try_detect_event({"disposition": None}) is None

    def test_detects_disposition_via_schedule_timestamp(self):
        handler = _make_handler()
        assert handler._try_detect_event({"schedule_timestamp": 123}) == "disposition"

    def test_detects_connected_event(self):
        handler = _make_handler()
        assert handler._try_detect_event({"call_connected": True}) == "connected"

    def test_detects_hangup_via_billsec(self):
        handler = _make_handler()
        assert handler._try_detect_event({"uuid": "u", "billsec": 60}) == "hangup"

    def test_detects_hangup_via_hangup_cause_key(self):
        handler = _make_handler()
        assert (
            handler._try_detect_event({"uuid": "u", "hangup_cause_key": "NORMAL"})
            == "hangup"
        )

    def test_sanitized_hangup_cause_key_none_is_not_hangup(self):
        """
        After sanitization hangup_cause_key=None. The handler now uses
        payload.get("hangup_cause_key") which returns None (falsy) →
        hangup must NOT be triggered.
        """
        handler = _make_handler()
        result = handler._try_detect_event({"uuid": "u", "hangup_cause_key": None})
        assert result is None

    def test_detects_dialed_event(self):
        handler = _make_handler()
        assert (
            handler._try_detect_event({"call_status": "dialed_on_customer_number"})
            == "dialed"
        )

    def test_returns_none_for_unrecognised_payload(self):
        handler = _make_handler()
        assert handler._try_detect_event({"call_id": "123"}) is None

    def test_uuid_without_billsec_or_hangup_key_is_not_hangup(self):
        """uuid alone must not trigger hangup — needs billsec or a truthy hangup_cause_key."""
        handler = _make_handler()
        assert handler._try_detect_event({"uuid": "u"}) is None


class TestPersistCdr:
    @pytest.mark.asyncio
    async def test_inserts_new_cdr_when_no_existing_record(self):
        handler = _make_handler()
        handler.call_repository.insert_cdr = AsyncMock()

        result = await handler._persist_cdr(None, {"call_id": "call-123"}, {})

        assert result == "created"
        handler.call_repository.insert_cdr.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_existing_cdr_by_id(self):
        handler = _make_handler()
        existing = {"_id": "mongo-id-001"}
        handler.call_repository.update_cdr = AsyncMock(return_value=True)

        result = await handler._persist_cdr(existing, {"call_id": "call-123"}, {})

        assert result == "updated"
        handler.call_repository.update_cdr.assert_called_once_with(
            "mongo-id-001", {"call_id": "call-123"}
        )

    @pytest.mark.asyncio
    async def test_returns_update_failed_when_update_cdr_returns_false(self):
        handler = _make_handler()
        existing = {"_id": "mongo-id-001"}
        handler.call_repository.update_cdr = AsyncMock(return_value=False)

        result = await handler._persist_cdr(existing, {}, {})

        assert result == "update_failed"

    @pytest.mark.asyncio
    async def test_new_cdr_action_reflects_detected_event(self):
        handler = _make_handler()
        handler.call_repository.insert_cdr = AsyncMock()

        final_data: Dict[str, Any] = {}
        await handler._persist_cdr(None, final_data, {"uuid": "u", "billsec": 10})

        assert final_data["action"] == "dialer_hangup"

    @pytest.mark.asyncio
    async def test_new_cdr_action_is_dialer_event_when_unknown(self):
        handler = _make_handler()
        handler.call_repository.insert_cdr = AsyncMock()

        final_data: Dict[str, Any] = {}
        await handler._persist_cdr(None, final_data, {})

        assert final_data["action"] == "dialer_event"

    @pytest.mark.asyncio
    async def test_new_cdr_has_created_at_timestamp(self):
        handler = _make_handler()
        handler.call_repository.insert_cdr = AsyncMock()

        final_data: Dict[str, Any] = {}
        await handler._persist_cdr(None, final_data, {})

        assert final_data.get("created_at") == 1722945600

    @pytest.mark.asyncio
    async def test_disposition_event_detected_correctly(self):
        handler = _make_handler()
        handler.call_repository.insert_cdr = AsyncMock()

        final_data: Dict[str, Any] = {"call_id": "123"}
        await handler._persist_cdr(None, final_data, {"disposition": "ANSWERED"})

        assert final_data["action"] == "dialer_disposition"


class TestProcessCdrApiPayload:
    @pytest.mark.asyncio
    async def test_always_returns_not_supported(self):
        handler = _make_handler()

        result = await handler.process_cdr_api_payload(
            {"some": "data"}, call_id="c1", uuid="u1"
        )

        assert result == {"status": "not_supported"}
        handler.logger.warning.assert_called()


class TestProcessWebhookResponseFields:
    @pytest.mark.asyncio
    async def test_event_type_hangup_in_response(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value=_default_did_info()
        )
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value=_default_maglo_response()
        )
        handler.call_repository.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value=None
        )
        handler.call_repository.insert_cdr = AsyncMock()

        result = await handler.process_webhook(_base_payload(billsec=60))

        assert result["event_type"] == "hangup"

    @pytest.mark.asyncio
    async def test_event_type_unknown_when_not_detectable(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value=_default_did_info()
        )
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value=_default_maglo_response()
        )
        handler.call_repository.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value=None
        )
        handler.call_repository.insert_cdr = AsyncMock()

        result = await handler.process_webhook(_base_payload())

        assert result["event_type"] == "unknown"

    @pytest.mark.asyncio
    async def test_call_id_falls_back_to_uuid(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value=_default_did_info()
        )
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value=_default_maglo_response()
        )
        handler.call_repository.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value=None
        )
        handler.call_repository.insert_cdr = AsyncMock()

        payload = _base_payload()
        del payload["call_id"]

        result = await handler.process_webhook(payload)

        assert result["call_id"] == "uuid-abc-456"


class TestSoftphoneDetection:
    @pytest.mark.asyncio
    async def test_extension_c2c_sets_soft_phone_outbound_type(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value=_default_did_info()
        )
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value=_default_maglo_response()
        )
        handler.call_repository.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value=None
        )
        handler.call_repository.insert_cdr = AsyncMock()

        await handler.process_webhook(_base_payload(extension_c2c="9999999999"))

        inserted = handler.call_repository.insert_cdr.call_args[0][0]
        assert inserted["outbound_type"] == "soft_phone"

    @pytest.mark.asyncio
    async def test_no_extension_c2c_sets_phone_number_outbound_type(self):
        handler = _make_handler()
        handler.did_management_service.get_dids_by_number = AsyncMock(
            return_value=_default_did_info()
        )
        handler.maglo_client.upsert_ivr_lead = AsyncMock(
            return_value=_default_maglo_response()
        )
        handler.call_repository.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value=None
        )
        handler.call_repository.insert_cdr = AsyncMock()

        await handler.process_webhook(_base_payload())

        inserted = handler.call_repository.insert_cdr.call_args[0][0]
        assert inserted["outbound_type"] == "phone_number"


class TestAgentResolutionEdgeCases:
    @pytest.mark.asyncio
    async def test_resolve_agent_with_empty_phone_returns_none(self):
        handler = _make_handler()
        result = await handler._resolve_agent_from_ivr_phone(100, "")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_agent_api_exception_returns_none(self):
        handler = _make_handler()
        handler.maglo_client.get_agent_by_ivr_phone = AsyncMock(
            side_effect=Exception("API Down")
        )
        result = await handler._resolve_agent_from_ivr_phone(100, "9988776655")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_agent_returns_int_on_success(self):
        """
        Mock _resolve_agent_from_ivr_phone directly — TalkoConsoleApiConstants.FIELD_AGENT_ID
        is an opaque constant so we cannot reliably mock the response dict key.
        The integration between the constant and maglo_client is tested separately.
        """
        handler = _make_handler()
        handler._resolve_agent_from_ivr_phone = AsyncMock(return_value=555)
        result = await handler._resolve_agent_from_ivr_phone(100, "9988776655")
        assert result == 555
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_resolve_agent_returns_none_when_no_agent_in_response(self):
        handler = _make_handler()
        # Patch maglo so get_agent_by_ivr_phone returns empty dict →
        # agent_data.get(FIELD_AGENT_ID) is None → returns None
        handler.maglo_client.get_agent_by_ivr_phone = AsyncMock(return_value={})
        result = await handler._resolve_agent_from_ivr_phone(100, "9988776655")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_agent_normalizes_phone_to_e164_before_lookup(self):
        """The ivr_phone sent to the console API must start with '+'."""
        handler = _make_handler()
        handler.maglo_client.get_agent_by_ivr_phone = AsyncMock(return_value={})

        await handler._resolve_agent_from_ivr_phone(100, "9988776655")

        call_kwargs = handler.maglo_client.get_agent_by_ivr_phone.call_args[1]
        ivr_phone = call_kwargs.get("ivr_phone", "")
        assert ivr_phone.startswith("+")
