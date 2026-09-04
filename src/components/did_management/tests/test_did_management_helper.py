from unittest.mock import Mock

import pytest

from src.components.did_management.constants import COOLDOWN_MS, TalkoDIDStatus
from src.components.did_management.dto import TalkoContract
from src.components.did_management.helpers import TalkoDidStatusUpdateHelper


class TestDidStatusUpdateHelper:

    @pytest.fixture
    def mock_payload(self):
        """Creates a mock AdminDIDAction payload."""
        payload = Mock(spec=TalkoContract.AdminDIDAction)
        payload.agent_id = "agent_123"
        payload.service_board_id = None
        return payload

    @pytest.fixture
    def now_ts(self):
        return 1710000000000

    @pytest.mark.parametrize(
        "status",
        [
            TalkoDIDStatus.AVAILABLE.value,
            TalkoDIDStatus.MAPPED.value,
            TalkoDIDStatus.COOLDOWN_COMPLETED.value,
        ],
    )
    def test_handle_set_available_success(self, status, mock_payload, now_ts):
        result = TalkoDidStatusUpdateHelper.handle_set_available(
            status, mock_payload, now_ts
        )
        assert result == {"status": TalkoDIDStatus.AVAILABLE.value}

    def test_handle_set_available_invalid_status(self, mock_payload, now_ts):
        with pytest.raises(ValueError, match="INVALID_TRANSITION"):
            TalkoDidStatusUpdateHelper.handle_set_available(
                TalkoDIDStatus.COOLING_PERIOD.value, mock_payload, now_ts
            )

    def test_handle_set_mapped_success_with_agent(self, mock_payload, now_ts):
        result = TalkoDidStatusUpdateHelper.handle_set_mapped(
            TalkoDIDStatus.AVAILABLE.value, mock_payload, now_ts
        )
        assert result["status"] == TalkoDIDStatus.MAPPED.value
        assert result["agent_id"] == "agent_123"
        assert result["mapped_date"] == now_ts

    def test_handle_set_mapped_without_agent_id(self, mock_payload, now_ts):
        mock_payload.agent_id = None
        result = TalkoDidStatusUpdateHelper.handle_set_mapped(
            TalkoDIDStatus.COOLDOWN_COMPLETED.value, mock_payload, now_ts
        )
        assert result == {"status": TalkoDIDStatus.MAPPED.value}
        assert "agent_id" not in result

    def test_handle_set_mapped_invalid_status(self, mock_payload, now_ts):
        with pytest.raises(ValueError, match="INVALID_TRANSITION"):
            TalkoDidStatusUpdateHelper.handle_set_mapped(
                TalkoDIDStatus.COOLING_PERIOD.value, mock_payload, now_ts
            )

    def test_handle_mark_spammed_success(self, mock_payload, now_ts):
        result = TalkoDidStatusUpdateHelper.handle_mark_spammed(
            TalkoDIDStatus.MAPPED.value, mock_payload, now_ts
        )
        assert result["status"] == TalkoDIDStatus.COOLING_PERIOD.value
        assert result["cooldown_until"] == now_ts + COOLDOWN_MS
        assert result["last_spam_detected_at"] == now_ts

    def test_handle_mark_spammed_raises_when_already_available(
        self, mock_payload, now_ts
    ):
        """Covers line 61 — AVAILABLE status raises INVALID_STATUS ValueError."""
        with pytest.raises(ValueError, match="INVALID_STATUS"):
            TalkoDidStatusUpdateHelper.handle_mark_spammed(
                TalkoDIDStatus.AVAILABLE.value, mock_payload, now_ts
            )

    def test_error_result_default_code(self):
        result = TalkoDidStatusUpdateHelper.error_result("919999999999", "DID not found")
        assert result == {
            "did_number": "919999999999",
            "success": False,
            "status": "skipped",
            "error": {"code": "UNKNOWN_ERROR", "message": "DID not found"},
        }

    def test_error_result_custom_code(self):
        result = TalkoDidStatusUpdateHelper.error_result(
            "919999999999", "DID not found", "DID_NOT_FOUND"
        )
        assert result["error"]["code"] == "DID_NOT_FOUND"
        assert result["error"]["message"] == "DID not found"

    def test_validate_did_returns_none_when_valid(self):
        doc = {"did_number": "12345", "status": TalkoDIDStatus.AVAILABLE.value}
        result = TalkoDidStatusUpdateHelper.validate_did(
            doc, "12345", TalkoDIDStatus.AVAILABLE.value, "set_available"
        )
        assert result is None

    def test_validate_did_not_found(self):
        result = TalkoDidStatusUpdateHelper.validate_did(
            None, "12345", TalkoDIDStatus.AVAILABLE.value, "set_available"
        )
        assert result["error"]["code"] == "DID_NOT_FOUND"
        assert result["success"] is False

    def test_validate_did_cooling_period(self):
        doc = {"did_number": "12345"}
        result = TalkoDidStatusUpdateHelper.validate_did(
            doc, "12345", TalkoDIDStatus.COOLING_PERIOD.value, "set_mapped"
        )
        assert result["error"]["code"] == "COOLING_PERIOD_ACTIVE"

    def test_validate_did_invalid_action(self):
        doc = {"did_number": "12345"}
        result = TalkoDidStatusUpdateHelper.validate_did(
            doc, "12345", TalkoDIDStatus.AVAILABLE.value, "invalid_action"
        )
        assert result["error"]["code"] == "INVALID_ACTION"

    def test_prepare_update_data_without_service_board(self, mock_payload, now_ts):
        mock_payload.service_board_id = None
        handler = TalkoDidStatusUpdateHelper.handle_set_available
        result = TalkoDidStatusUpdateHelper.prepare_update_data(
            handler, TalkoDIDStatus.AVAILABLE.value, mock_payload, now_ts
        )
        assert result["status"] == TalkoDIDStatus.AVAILABLE.value
        assert result["status_changed_at"] == now_ts
        assert "service_board_id" not in result

    def test_prepare_update_data_with_service_board(self, mock_payload, now_ts):
        mock_payload.service_board_id = 42
        handler = TalkoDidStatusUpdateHelper.handle_set_available
        result = TalkoDidStatusUpdateHelper.prepare_update_data(
            handler, TalkoDIDStatus.AVAILABLE.value, mock_payload, now_ts
        )
        assert result["service_board_id"] == 42
        assert result["status_changed_at"] == now_ts

    def test_parse_value_error_with_pipe(self):
        result = TalkoDidStatusUpdateHelper.parse_value_error(
            "12345", ValueError("INVALID_TRANSITION|Transition not allowed")
        )
        assert result["error"]["code"] == "INVALID_TRANSITION"
        assert result["error"]["message"] == "Transition not allowed"

    def test_parse_value_error_without_pipe(self):
        result = TalkoDidStatusUpdateHelper.parse_value_error(
            "12345", ValueError("plain error message")
        )
        assert result["error"]["code"] == "VALIDATION_ERROR"
        assert result["error"]["message"] == "plain error message"

    def test_build_summary_all_success(self):
        results = [{"success": True}, {"success": True}]
        summary = TalkoDidStatusUpdateHelper.build_summary(["1", "2"], results)
        assert summary["summary"]["total"] == 2
        assert summary["summary"]["succeeded"] == 2
        assert summary["summary"]["failed"] == 0

    def test_build_summary_mixed(self):
        results = [{"success": True}, {"success": False}]
        summary = TalkoDidStatusUpdateHelper.build_summary(["1", "2"], results)
        assert summary["summary"]["succeeded"] == 1
        assert summary["summary"]["failed"] == 1

    def test_build_summary_all_failed(self):
        results = [{"success": False}, {"success": False}]
        summary = TalkoDidStatusUpdateHelper.build_summary(["1", "2"], results)
        assert summary["summary"]["succeeded"] == 0
        assert summary["summary"]["failed"] == 2
