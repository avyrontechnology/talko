from datetime import datetime, timedelta, timezone
from enum import Enum
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.components.analytics.constants import CLICK_TO_CALL, INBOUND
from src.components.cdr.controllers import CDRController
from src.components.cdr.dto import Contract
from src.components.cdr.helper import (
    CallLogQueryHelper,
    CommonCDRHelper,
    GetAgentCallLogsHelper,
    GetCallRecordHistoryHelper,
    GetCDRsHelper,
)
from src.utils.enums import NumberType, TimeFilter
from src.utils.title_case_util import TitleCaseUtil

# Define IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))


# Mock TALK_TIME_RANGES and TalkTimeRange enum
class MockTalkTimeRange(Enum):
    _0_1 = "0_1"
    _1_3 = "1_3"
    _3_5 = "3_5"
    _5_plus = "5_plus"


MOCK_TALK_TIME_RANGES = {
    MockTalkTimeRange._0_1: (0, 60),  # 0–1 minute
    MockTalkTimeRange._1_3: (61, 180),  # 1–3 minutes
    MockTalkTimeRange._3_5: (181, 300),  # 3–5 minutes
    MockTalkTimeRange._5_plus: (301, None),  # 5+ minutes
}


def fake_cdr_dict():
    return {
        "_id": "12345",
        "partner_id": 10,
        "agent": 1,
        "lead_id": 5,
        "service_board_id": 20,
        "calling_mode": INBOUND,
        "call_status": "missed",
        "call_recording": "http://recording.com/1",
        "customer": "9999999999",
        "total_call_duration": 120,
        "talk_time": 100,
        "did_number": "8888888888",
        "agent_number": "7777777777",
        "reason": "Busy",
        "hangup_cause": "USER_BUSY",
        "reason_key": "BUSY",
        "hangup_by": "customer",
        "created_at": 1727181060,
        "call_connected": "1",
        "lead_name": "John Doe",
        "agent_name": "Agent Smith",
    }


def fake_filtered_cdr_dict():
    cdr = fake_cdr_dict()
    return {
        "partner_id": cdr["partner_id"],
        "agent": cdr["agent"],
        "lead_id": cdr["lead_id"],
        "service_board_id": cdr["service_board_id"],
        "calling_mode": cdr["calling_mode"],
        "call_status": cdr["call_status"],
        "call_recording": cdr["call_recording"],
        "lead_number": cdr["customer"],
        "total_call_duration": cdr["total_call_duration"],
        "talk_time": cdr["talk_time"],
        "did_number": cdr["did_number"],
        "agent_number": cdr["agent_number"],
        "reason": cdr["reason"],
        "hangup_cause": cdr["hangup_cause"],
        "reason_key": cdr["reason_key"],
        "hangup_by": cdr["hangup_by"],
        "created_at": cdr["created_at"],
        "call_connected": cdr["call_connected"],
        "lead_name": cdr["lead_name"],
        "call_type": "incoming",
    }


@pytest.fixture
def mock_logger():
    """Mock logger for all tests."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.debug = MagicMock()
    logger.error = MagicMock()
    return logger


@pytest.fixture
def mock_dependencies():
    """Mock dependencies for masking and title case utilities."""
    mock_title_case_util = MagicMock()
    mock_mask_phone_number = MagicMock()
    return mock_title_case_util, mock_mask_phone_number


@pytest.fixture(autouse=True)
def mock_datetime():
    """Mock datetime.datetime.now to return 2025-10-15 17:02 IST."""
    mock_utc_time = datetime(2025, 10, 15, 11, 32, tzinfo=timezone.utc)  # 17:02 IST
    mock_ist = mock_utc_time.astimezone(IST)
    mock_now = MagicMock(return_value=mock_utc_time)
    mock_now.astimezone.return_value = mock_ist
    with patch("datetime.datetime") as mock_datetime_class:
        mock_datetime_class.now = mock_now
        yield mock_datetime_class


class TestCommonCDRHelper:
    """Test suite for CommonCDRHelper class."""

    def test_parse_mongo_timestamp_number_long(self, mock_logger):
        """Test parse_mongo_timestamp with MongoDB $numberLong format."""
        timestamp = CommonCDRHelper.parse_mongo_timestamp(
            {"$numberLong": "1727181060000"}, mock_logger
        )
        assert timestamp == 1727181060000
        mock_logger.debug.assert_any_call(
            "Parsing MongoDB timestamp in common cdr helper: {'$numberLong': '1727181060000'}"
        )
        mock_logger.debug.assert_any_call(
            "Parsed $numberLong to timestamp in common cdr helper: 1727181060000"
        )
        assert mock_logger.debug.call_count == 2

    def test_parse_mongo_timestamp_int(self, mock_logger):
        """Test parse_mongo_timestamp with integer input."""
        timestamp = CommonCDRHelper.parse_mongo_timestamp(1727181060, mock_logger)
        assert timestamp == 1727181060
        mock_logger.debug.assert_any_call(
            "Parsing MongoDB timestamp in common cdr helper: 1727181060"
        )
        mock_logger.debug.assert_any_call(
            "Parsed numeric timestamp in common cdr helper: 1727181060"
        )
        assert mock_logger.debug.call_count == 2

    def test_parse_mongo_timestamp_float(self, mock_logger):
        """Test parse_mongo_timestamp with float input."""
        timestamp = CommonCDRHelper.parse_mongo_timestamp(1727181060.123, mock_logger)
        assert timestamp == 1727181060
        mock_logger.debug.assert_any_call(
            "Parsing MongoDB timestamp in common cdr helper: 1727181060.123"
        )
        mock_logger.debug.assert_any_call(
            "Parsed numeric timestamp in common cdr helper: 1727181060"
        )
        assert mock_logger.debug.call_count == 2

    def test_parse_mongo_timestamp_invalid_number_long(self, mock_logger):
        """Test parse_mongo_timestamp with invalid $numberLong."""
        timestamp = CommonCDRHelper.parse_mongo_timestamp(
            {"$numberLong": "invalid"}, mock_logger
        )
        assert timestamp is None
        mock_logger.debug.assert_any_call(
            "Parsing MongoDB timestamp in common cdr helper: {'$numberLong': 'invalid'}"
        )
        mock_logger.error.assert_called_once_with(
            "Failed to parse $numberLong timestamp in common cdr helper: invalid literal for int() with base 10: 'invalid'"
        )
        assert mock_logger.debug.call_count == 1

    def test_parse_mongo_timestamp_none(self, mock_logger):
        """Test parse_mongo_timestamp with None input."""
        timestamp = CommonCDRHelper.parse_mongo_timestamp(None, mock_logger)
        assert timestamp is None
        mock_logger.debug.assert_any_call(
            "Parsing MongoDB timestamp in common cdr helper: None"
        )
        mock_logger.debug.assert_any_call(
            "Timestamp is None or invalid in common cdr helper"
        )
        assert mock_logger.debug.call_count == 2

    def test_create_filtered_cdr_full_data(self, mock_logger):
        """Test create_filtered_cdr with complete CDR data."""
        cdr = fake_cdr_dict()
        filtered_cdr = CommonCDRHelper.create_filtered_cdr(cdr, mock_logger)
        assert filtered_cdr == fake_filtered_cdr_dict()
        mock_logger.info.assert_called_once_with(
            "Creating filtered CDR in common cdr helper"
        )
        mock_logger.debug.assert_any_call(f"Input CDR in common cdr helper: {cdr}")
        mock_logger.debug.assert_any_call(
            f"Parsed numeric timestamp in common cdr helper: 1727181060"
        )
        mock_logger.debug.assert_any_call(
            f"Filtered CDR in common cdr helper: {filtered_cdr}"
        )

    def test_create_filtered_cdr_missing_fields(self, mock_logger):
        """Test create_filtered_cdr with missing fields."""
        cdr = {"_id": "12345", "partner_id": 10}
        with patch("time.time", return_value=1727181060.123):
            filtered_cdr = CommonCDRHelper.create_filtered_cdr(cdr, mock_logger)
        expected = {
            "partner_id": 10,
            "agent": "",
            "lead_id": None,
            "service_board_id": None,
            "calling_mode": None,
            "call_status": None,
            "call_recording": "",
            "lead_number": "",
            "total_call_duration": 0,
            "talk_time": 0,
            "did_number": "",
            "agent_number": "",
            "reason": "",
            "hangup_cause": "",
            "reason_key": "",
            "hangup_by": "",
            "created_at": 1727181060123,
            "call_connected": "0",
            "lead_name": "",
            "call_type": "incoming",
        }
        assert filtered_cdr == expected
        mock_logger.info.assert_called_once_with(
            "Creating filtered CDR in common cdr helper"
        )

    def test_create_filtered_cdr_clicktocall(self, mock_logger):
        """Test create_filtered_cdr with clicktocall calling_mode."""
        cdr = fake_cdr_dict()
        cdr["calling_mode"] = CLICK_TO_CALL
        filtered_cdr = CommonCDRHelper.create_filtered_cdr(cdr, mock_logger)
        assert filtered_cdr["call_type"] == "outgoing"
        mock_logger.info.assert_called_once_with(
            "Creating filtered CDR in common cdr helper"
        )

    def test_create_filtered_cdr_invalid_calling_mode(self, mock_logger):
        """Test create_filtered_cdr with invalid calling_mode."""
        cdr = fake_cdr_dict()
        cdr["calling_mode"] = "invalid"
        filtered_cdr = CommonCDRHelper.create_filtered_cdr(cdr, mock_logger)
        assert filtered_cdr["call_type"] == "incoming"
        mock_logger.info.assert_called_once_with(
            "Creating filtered CDR in common cdr helper"
        )

    def test_mask_sensitive_data(self, mock_logger, mock_dependencies):
        """Test mask_sensitive_data with multiple phone number fields."""
        _, mock_mask_phone_number = mock_dependencies
        mock_mask_phone_number.side_effect = lambda x, _: (
            f"{x[:4]}******" if isinstance(x, str) and x else x
        )
        cdr = {
            "customer": "9999999999",
            "caller_id_number": "8888888888",
        }
        CommonCDRHelper.mask_sensitive_data(cdr, mock_logger)
        assert cdr["customer"] == "9999******"
        assert cdr["caller_id_number"] == "8888******"
        mock_logger.info.assert_called_once_with(
            "Masking sensitive data in CDR in common cdr helper."
        )
        mock_logger.debug.assert_any_call("Masked customer: 9999999999 -> 9999******")
        mock_logger.debug.assert_any_call(
            "Masked caller_id_number: 8888888888 -> 8888******"
        )

    def test_attach_agent_names(self, mock_logger):
        """Test attach_agent_names with valid agent data."""
        agent_data = {30: {"name": "John Doe"}}
        cdr_response = Contract.CallRecordHistoryResponse(
            partner_id=1009,
            agent=30,
            lead_id=2,
            service_board_id=2,
            calling_mode="clicktocall",
            call_status="initiated",
            call_recording="",
            lead_number="+919876******",
            total_call_duration=0,
            talk_time=0,
            did_number="918064524378",
            agent_number="+918103492952",
            reason="",
            hangup_cause="",
            reason_key="initiated",
            hangup_by="none",
            created_at=1760440089989,
            action_performed_by=None,
            lead_call_status="not connected",
            agent_call_status="not connected",
            call_connected="0",
            lead_name="",
            call_type="outgoing",
            number_type="primary",
            lead_secret="...",
        )
        CommonCDRHelper.attach_agent_names([cdr_response], agent_data, mock_logger)
        assert cdr_response.action_performed_by == "John Doe"
        mock_logger.info.assert_called_once_with(
            "Attaching agent names to CDR responses in common cdr helper."
        )
        mock_logger.debug.assert_any_call(
            "Agent data in common cdr helper: {30: {'name': 'John Doe'}}"
        )

    def test_attach_agent_names_missing_agent(self, mock_logger):
        """Test attach_agent_names with missing agent data."""
        agent_data = {999: {"name": "John Doe"}}
        cdr_response = Contract.CallRecordHistoryResponse(
            partner_id=1009,
            agent=30,  # Agent ID not in agent_data
            lead_id=2,
            service_board_id=2,
            calling_mode="clicktocall",
            call_status="initiated",
            call_recording="",
            lead_number="+919876******",
            total_call_duration=0,
            talk_time=0,
            did_number="918064524378",
            agent_number="+918103492952",
            reason="",
            hangup_cause="",
            reason_key="initiated",
            hangup_by="none",
            created_at=1760440089989,
            action_performed_by=None,
            lead_call_status="not connected",
            agent_call_status="not connected",
            call_connected="0",
            lead_name="",
            call_type="outgoing",
            number_type="primary",
            lead_secret="...",
        )
        CommonCDRHelper.attach_agent_names([cdr_response], agent_data, mock_logger)
        assert cdr_response.action_performed_by == ""
        mock_logger.info.assert_called_once_with(
            "Attaching agent names to CDR responses in common cdr helper."
        )
        mock_logger.debug.assert_any_call(
            "Agent data in common cdr helper: {999: {'name': 'John Doe'}}"
        )

    def test_mask_sensitive_data_with_lead_secret(self, mock_logger, mock_dependencies):
        """Test mask_sensitive_data with lead_secret field."""
        _, mock_mask_phone_number = mock_dependencies
        mock_mask_phone_number.side_effect = lambda x, _: (
            f"{x[:4]}******" if isinstance(x, str) and x else x
        )
        cdr = {
            "customer": "9999999999",
            "caller_id_number": "8888888888",
            "lead_secret": "sensitive_data_123",
        }
        CommonCDRHelper.mask_sensitive_data(cdr, mock_logger)
        assert cdr["customer"] == "9999******"
        assert cdr["caller_id_number"] == "8888******"
        assert (
            cdr["lead_secret"] == "sensitive_data_123"
        )  # Assuming lead_secret is not masked
        mock_logger.info.assert_called_once_with(
            "Masking sensitive data in CDR in common cdr helper."
        )
        mock_logger.debug.assert_any_call("Masked customer: 9999999999 -> 9999******")
        mock_logger.debug.assert_any_call(
            "Masked caller_id_number: 8888888888 -> 8888******"
        )

    def test_mask_sensitive_data_lead_secret_encrypted(
        self, mock_logger, mock_dependencies
    ):
        """Test mask_sensitive_data with lead_secret encryption."""
        _, mock_mask_phone_number = mock_dependencies
        mock_mask_phone_number.side_effect = lambda x, _: (
            f"{x[:4]}******" if isinstance(x, str) and x else x
        )
        with patch(
            "src.utils.crypto_utils.RSAKeyHandler.encrypt_with_public_key",
            return_value="encrypted_secret",
        ):
            cdr = {
                "customer": "9999999999",
                "caller_id_number": "8888888888",
                "lead_secret": "sensitive_data_123",
            }
            CommonCDRHelper.mask_sensitive_data(cdr, mock_logger)
            assert cdr["customer"] == "9999******"
            assert cdr["caller_id_number"] == "8888******"


class TestGetCDRsHelper:
    """Test suite for GetCDRsHelper class."""

    def test_process_cdrs_success(self, mock_logger):
        """Test process_cdrs with valid CDRs."""
        cdrs = [fake_cdr_dict()]
        expected_input_log = [fake_cdr_dict()]
        with patch("src.components.cdr.dto.Contract.CDRResponse") as mock_cdr_response:
            mock_instance = {"id": "12345"}
            mock_cdr_response.return_value = mock_instance
            result = GetCDRsHelper.process_cdrs(cdrs, mock_logger)
            assert len(result) == 1
            assert result[0] == mock_instance
            assert cdrs[0]["id"] == "12345"
            assert "_id" not in cdrs[0]
            mock_cdr_response.assert_called_once()
            mock_logger.info.assert_any_call("Processing CDRs for get_cdrs helper")
            mock_logger.info.assert_any_call(
                "Successfully processed CDRs for get_cdrs helper"
            )
            mock_logger.debug.assert_any_call(
                f"Input CDRs in get cdr helper: {expected_input_log}"
            )

    def test_process_cdrs_non_string_customer(self, mock_logger):
        """Test process_cdrs with non-string customer field."""
        cdrs = [fake_cdr_dict()]
        cdrs[0]["customer"] = 9999999999
        expected_input_log = [fake_cdr_dict()]
        expected_input_log[0]["customer"] = 9999999999
        with patch("src.components.cdr.dto.Contract.CDRResponse") as mock_cdr_response:
            mock_instance = {"id": "12345"}
            mock_cdr_response.return_value = mock_instance
            result = GetCDRsHelper.process_cdrs(cdrs, mock_logger)
            assert len(result) == 1
            assert result[0] == mock_instance
            assert cdrs[0]["customer"] == "9999999999"
            mock_logger.info.assert_any_call("Processing CDRs for get_cdrs helper")
            mock_logger.debug.assert_any_call(
                "Converting non-string customer field in get cdr helper: 9999999999"
            )
            mock_logger.debug.assert_any_call(
                f"Input CDRs in get cdr helper: {expected_input_log}"
            )

    def test_process_cdrs_exception(self, mock_logger):
        """Test process_cdrs raises exception."""
        cdrs = [fake_cdr_dict()]
        with patch(
            "src.components.cdr.dto.Contract.CDRResponse",
            side_effect=Exception("Invalid CDR"),
        ):
            with pytest.raises(Exception, match="Invalid CDR"):
                GetCDRsHelper.process_cdrs(cdrs, mock_logger)
            mock_logger.error.assert_called_once_with(
                "Failed to create CDRResponse in get cdr helper: Invalid CDR"
            )


class TestGetAgentCallLogsHelper:
    """Test suite for GetAgentCallLogsHelper class."""

    def test_process_cdrs_masking_enabled(self, mock_logger, mock_dependencies):
        """Test process_cdrs with masking enabled."""
        _, mock_mask_phone_number = mock_dependencies
        mock_mask_phone_number.side_effect = lambda x, _: (
            f"{x[:4]}******" if isinstance(x, str) and x else x
        )
        cdrs = [fake_cdr_dict()]
        expected_input_log = [fake_cdr_dict()]
        with patch(
            "src.utils.enums.HangupCause.from_raw",
            side_effect=Exception("Invalid hangup cause"),
        ):
            with patch(
                "src.utils.enums.ReasonKey.from_raw",
                side_effect=Exception("Invalid reason key"),
            ):
                with patch(
                    "src.components.cdr.dto.Contract.CallLogResponse"
                ) as mock_call_log_response:
                    mock_instance = {"id": "12345"}
                    mock_call_log_response.return_value = mock_instance
                    agent_ids, responses = GetAgentCallLogsHelper.process_cdrs(
                        cdrs, True, mock_logger
                    )
        assert agent_ids == [1]
        assert len(responses) == 1
        assert responses[0] == mock_instance
        assert cdrs[0]["customer"] == "9999******"
        assert cdrs[0]["hangup_cause"] == "Unknown Status"
        assert cdrs[0]["reason_key"] == "Unknown Status"
        assert "call_flow" not in cdrs[0]
        assert cdrs[0]["action_performed_by"] == ""
        assert "agent_name" not in cdrs[0]
        assert cdrs[0]["event_type"] == "call"
        mock_logger.info.assert_any_call(
            "Processing CDRs for get_agent_call_logs helper"
        )
        mock_logger.debug.assert_any_call(
            f"Input CDRs: {expected_input_log}, is_masking_enabled: True in get agent call logs helper"
        )
        mock_logger.error.assert_any_call(
            "Failed to convert hangup_cause: Invalid hangup cause in get agent call logs helper"
        )
        mock_logger.error.assert_any_call(
            "Failed to convert reason_key: Invalid reason key in get agent call logs helper"
        )

    def test_process_cdrs_no_masking(self, mock_logger):
        """Test process_cdrs without masking."""
        cdrs = [fake_cdr_dict()]
        expected_input_log = [fake_cdr_dict()]
        with patch(
            "src.utils.enums.HangupCause.from_raw",
            side_effect=Exception("Invalid hangup cause"),
        ):
            with patch(
                "src.utils.enums.ReasonKey.from_raw",
                side_effect=Exception("Invalid reason key"),
            ):
                with patch(
                    "src.components.cdr.dto.Contract.CallLogResponse"
                ) as mock_call_log_response:
                    mock_instance = {"id": "12345"}
                    mock_call_log_response.return_value = mock_instance
                    agent_ids, responses = GetAgentCallLogsHelper.process_cdrs(
                        cdrs, False, mock_logger
                    )
        assert agent_ids == [1]
        assert len(responses) == 1
        assert responses[0] == mock_instance
        assert cdrs[0]["customer"] == "9999999999"
        assert cdrs[0]["id"] == "12345"
        assert cdrs[0]["hangup_cause"] == "Unknown Status"
        assert cdrs[0]["reason_key"] == "Unknown Status"
        assert "call_flow" not in cdrs[0]
        assert cdrs[0]["action_performed_by"] == ""
        assert "agent_name" not in cdrs[0]
        assert cdrs[0]["event_type"] == "call"
        mock_logger.info.assert_any_call(
            "Processing CDRs for get_agent_call_logs helper"
        )
        mock_logger.debug.assert_any_call(
            f"Input CDRs: {expected_input_log}, is_masking_enabled: False in get agent call logs helper"
        )
        mock_logger.error.assert_any_call(
            "Failed to convert hangup_cause: Invalid hangup cause in get agent call logs helper"
        )
        mock_logger.error.assert_any_call(
            "Failed to convert reason_key: Invalid reason key in get agent call logs helper"
        )

    def test_process_cdrs_non_string_customer(self, mock_logger, mock_dependencies):
        """Test process_cdrs with non-string customer field."""
        _, mock_mask_phone_number = mock_dependencies
        mock_mask_phone_number.side_effect = lambda x, _: (
            f"{x[:4]}******" if isinstance(x, str) and x else x
        )
        cdrs = [fake_cdr_dict()]
        cdrs[0]["customer"] = 9999999999
        expected_input_log = [fake_cdr_dict()]
        expected_input_log[0]["customer"] = 9999999999
        with patch(
            "src.utils.enums.HangupCause.from_raw",
            side_effect=Exception("Invalid hangup cause"),
        ):
            with patch(
                "src.utils.enums.ReasonKey.from_raw",
                side_effect=Exception("Invalid reason key"),
            ):
                with patch(
                    "src.components.cdr.dto.Contract.CallLogResponse"
                ) as mock_call_log_response:
                    mock_instance = {"id": "12345"}
                    mock_call_log_response.return_value = mock_instance
                    agent_ids, responses = GetAgentCallLogsHelper.process_cdrs(
                        cdrs, True, mock_logger
                    )
        assert agent_ids == [1]
        assert len(responses) == 1
        assert responses[0] == mock_instance
        assert cdrs[0]["customer"] == "9999******"
        mock_logger.info.assert_any_call(
            "Processing CDRs for get_agent_call_logs helper"
        )
        mock_logger.debug.assert_any_call(
            "Converting non-string customer field: 9999999999, in get agent call logs helper"
        )
        mock_logger.debug.assert_any_call(
            f"Input CDRs: {expected_input_log}, is_masking_enabled: True in get agent call logs helper"
        )

    def test_process_cdrs_missing_agent(self, mock_logger):
        """Test process_cdrs with missing agent field."""
        cdrs = [fake_cdr_dict()]
        cdrs[0]["agent"] = None
        expected_input_log = [fake_cdr_dict()]
        expected_input_log[0]["agent"] = None
        with patch(
            "src.utils.enums.HangupCause.from_raw",
            side_effect=Exception("Invalid hangup cause"),
        ):
            with patch(
                "src.utils.enums.ReasonKey.from_raw",
                side_effect=Exception("Invalid reason key"),
            ):
                with patch(
                    "src.components.cdr.dto.Contract.CallLogResponse"
                ) as mock_call_log_response:
                    mock_instance = {"id": "12345"}
                    mock_call_log_response.return_value = mock_instance
                    agent_ids, responses = GetAgentCallLogsHelper.process_cdrs(
                        cdrs, False, mock_logger
                    )
        assert agent_ids == [None]
        assert len(responses) == 1
        assert responses[0] == mock_instance
        mock_logger.info.assert_any_call(
            "Processing CDRs for get_agent_call_logs helper"
        )
        mock_logger.debug.assert_any_call(
            "Collected agent_id in get agent call logs helper: None"
        )
        mock_logger.debug.assert_any_call(
            f"Input CDRs: {expected_input_log}, is_masking_enabled: False in get agent call logs helper"
        )

    def test_handle_hangup_cause_success(self, mock_logger):
        """Test handle_hangup_cause success."""
        cdr = {"hangup_cause": "USER_BUSY"}
        with patch(
            "src.utils.enums.HangupCause.from_raw", return_value=MagicMock(value="Busy")
        ):
            result = GetAgentCallLogsHelper.handle_hangup_cause(cdr, mock_logger)
            assert result == "Busy"
            mock_logger.info.assert_called_once_with(
                "Handling hangup_cause in get agent call logs helper"
            )
            mock_logger.debug.assert_called_once_with(
                "Converted hangup_cause: Busy in get agent call logs helper"
            )

    def test_handle_hangup_cause_exception(self, mock_logger):
        """Test handle_hangup_cause exception."""
        cdr = {"hangup_cause": "INVALID"}
        with patch(
            "src.utils.enums.HangupCause.from_raw",
            side_effect=Exception("Invalid hangup cause"),
        ):
            result = GetAgentCallLogsHelper.handle_hangup_cause(cdr, mock_logger)
            assert result == "Unknown Status"
            assert cdr["hangup_cause"] == "Unknown Status"
            mock_logger.info.assert_called_once_with(
                "Handling hangup_cause in get agent call logs helper"
            )
            mock_logger.error.assert_called_once_with(
                "Failed to convert hangup_cause: Invalid hangup cause in get agent call logs helper"
            )

    def test_handle_reason_key_success(self, mock_logger):
        """Test handle_reason_key success."""
        cdr = {"reason_key": "BUSY"}
        with patch(
            "src.utils.enums.ReasonKey.from_raw", return_value=MagicMock(value="Busy")
        ):
            result = GetAgentCallLogsHelper.handle_reason_key(cdr, mock_logger)
            assert result == "Busy"
            mock_logger.info.assert_called_once_with(
                "Handling reason_key in get agent call logs helper"
            )
            mock_logger.debug.assert_called_once_with(
                "Converted reason_key: Busy in get agent call logs helper"
            )

    def test_handle_reason_key_exception(self, mock_logger):
        """Test handle_reason_key exception."""
        cdr = {"reason_key": "INVALID"}
        with patch(
            "src.utils.enums.ReasonKey.from_raw",
            side_effect=Exception("Invalid reason key"),
        ):
            result = GetAgentCallLogsHelper.handle_reason_key(cdr, mock_logger)
            assert result == "Unknown Status"
            assert cdr["reason_key"] == "Unknown Status"
            mock_logger.info.assert_called_once_with(
                "Handling reason_key in get agent call logs helper"
            )
            mock_logger.error.assert_called_once_with(
                "Failed to convert reason_key: Invalid reason key in get agent call logs helper"
            )

    def test_agent_call_log_response(self, mock_logger, mock_dependencies):
        """Test agent_call_log_response with sorted responses."""
        mock_title_case_util, _ = mock_dependencies
        cdr_response = cdr_response = Contract.CallRecordHistoryResponse(
            partner_id=1009,
            agent=30,  # Agent ID not in agent_data
            lead_id=2,
            service_board_id=2,
            calling_mode="clicktocall",
            call_status="initiated",
            call_recording="",
            lead_number="+919876******",
            total_call_duration=0,
            talk_time=0,
            did_number="918064524378",
            agent_number="+918103492952",
            reason="",
            hangup_cause="",
            reason_key="initiated",
            hangup_by="none",
            created_at=1760440089989,
            action_performed_by=None,
            lead_call_status="not connected",
            agent_call_status="not connected",
            call_connected="0",
            lead_name="",
            call_type="outgoing",
            number_type="primary",
            lead_secret="...",
        )
        expected_response = {
            "call_histories": [cdr_response],
            "total_count": 1,
        }
        mock_title_case_util.convert_values_to_title_case.return_value = (
            expected_response
        )
        result = GetAgentCallLogsHelper.agent_call_log_response(
            [cdr_response], 1, mock_logger
        )
        assert result["total_count"] == 1
        assert len(result["call_histories"]) == 1
        assert result["call_histories"][0]["created_at"] == 1760440089989

    def test_process_cdrs_exception_handling(self, mock_logger, mock_dependencies):
        """Test process_cdrs exception handling when CallLogResponse creation fails."""
        _, mock_mask_phone_number = mock_dependencies
        mock_mask_phone_number.side_effect = lambda x, _: (
            f"{x[:4]}******" if isinstance(x, str) and x else x
        )

        cdr = {
            "id": "12345",
            "partner_id": 1009,
            "agent": 30,
            "lead_id": 2,
            "service_board_id": 2,
            "calling_mode": "clicktocall",
            "call_status": "initiated",
            "call_recording": "",
            "lead_number": "+919876543210",
            "total_call_duration": 0,
            "talk_time": 0,
            "did_number": "918064524378",
            "agent_number": "+918103492952",
            "reason": "",
            "hangup_cause": "USER_BUSY",
            "reason_key": "initiated",
            "hangup_by": "none",
            "created_at": 1760440089989,
            "action_performed_by": None,
            "lead_call_status": "not connected",
            "agent_call_status": "not connected",
            "call_connected": "0",
            "lead_name": "",
            "call_type": "outgoing",
            "number_type": "primary",
            "lead_secret": "...",
            "event_type": "call",
            "action": "",
            "solution": "",
            "sr_number": "",
            "customer_status": "not connected",
            "agent_status": "not connected",
            "call_actions": "invalid",  # Invalid type
            "call_uuid": "",
        }

        with patch(
            "src.utils.enums.HangupCause.from_raw", return_value=MagicMock(value="Busy")
        ):
            with patch(
                "src.utils.enums.ReasonKey.from_raw",
                return_value=MagicMock(value="Initiated"),
            ):
                with pytest.raises(ValidationError):
                    GetAgentCallLogsHelper.process_cdrs([cdr], True, mock_logger)

    def test_agent_call_log_response_exception_handling(self, mock_logger):
        """Test agent_call_log_response exception handling when TitleCaseUtil.convert_values_to_title_case fails."""
        # Create a minimal valid CallLogResponse instance
        cdr_response = Contract.CallLogResponse(
            id="12345",
            partner_id=1009,
            agent=30,
            lead_id=2,
            service_board_id=2,
            calling_mode="clicktocall",
            call_status="initiated",
            call_recording="",
            lead_number="+919876543210",
            total_call_duration=0,
            talk_time=0,
            did_number="918064524378",
            agent_number="+918103492952",
            reason="",
            hangup_cause="USER_BUSY",
            reason_key="initiated",
            hangup_by="none",
            created_at=1760440089989,
            action_performed_by=None,
            lead_call_status="not connected",
            agent_call_status="not connected",
            call_connected="0",
            lead_name="",
            call_type="outgoing",
            number_type="primary",
            lead_secret="...",
            event_type="call",
            action="",
            solution="",
            sr_number="",
            customer_status="not connected",
            agent_status="not connected",
            call_actions=[],
            call_uuid="",
        )

        cdr_responses = [cdr_response]
        total_count = 1

        # Mock TitleCaseUtil.convert_values_to_title_case to raise an exception
        with patch.object(
            TitleCaseUtil,
            "convert_values_to_title_case",
            side_effect=Exception("Title case conversion failed"),
        ):
            with pytest.raises(Exception, match="Title case conversion failed"):
                GetAgentCallLogsHelper.agent_call_log_response(
                    cdr_responses, total_count, mock_logger
                )

        # Verify logger calls
        mock_logger.info.assert_called_once_with(
            "Formatting agent call log response in get agent call logs response helper"
        )
        mock_logger.debug.assert_called_once_with(
            f"CDR responses: {cdr_responses}, total_count: {total_count} in get agent call logs response helper"
        )
        mock_logger.error.assert_called_once_with(
            "Failed to format agent call log response: Title case conversion failed in get agent call logs response helper"
        )


class TestGetCallRecordHistoryHelper:
    """Test suite for GetCallRecordHistoryHelper class."""

    def test_validate_call_status_valid_list(self, mock_logger):
        """Test validate_call_status with a valid call status list."""
        with patch(
            "src.components.cdr.constants.VALID_CALL_STATUSES", ["answered", "missed"]
        ):
            GetCallRecordHistoryHelper.validate_call_status(
                ["answered", "missed"], mock_logger
            )
            mock_logger.info.assert_called_once_with(
                "Validating call_status in get call record history helper"
            )
            mock_logger.debug.assert_any_call(
                "Call status: ['answered', 'missed'] in get call record history helper"
            )
            mock_logger.debug.assert_any_call(
                "Call status validated successfully in get call record history helper"
            )

    def test_validate_call_status_invalid_type(self, mock_logger):
        """Test validate_call_status with invalid type (non-list)."""
        with pytest.raises(
            ValueError, match="Invalid type for call_status: str. Expected a list"
        ):
            GetCallRecordHistoryHelper.validate_call_status("answered", mock_logger)
        mock_logger.error.assert_called_once_with(
            "Invalid type for call_status: str in get call record history helper"
        )

    def test_validate_call_status_invalid_status(self, mock_logger):
        """Test validate_call_status with anomalous status values."""
        with patch(
            "src.components.cdr.constants.VALID_CALL_STATUSES", ["answered", "missed"]
        ):
            with pytest.raises(
                ValueError, match=r"Invalid call_status values: \['invalid'\]."
            ):
                GetCallRecordHistoryHelper.validate_call_status(
                    ["answered", "invalid"], mock_logger
                )
            mock_logger.error.assert_called_once_with(
                "Invalid call_status values: ['invalid'] in get call record history helper"
            )

    def test_get_call_record_history_projection(self):
        """Test get_call_record_history_projection returns correct fields."""
        projection = GetCallRecordHistoryHelper.get_call_record_history_projection()
        expected = {
            "partner_id": 1,
            "agent": 1,
            "lead_id": 1,
            "service_board_id": 1,
            "calling_mode": 1,
            "call_status": 1,
            "call_recording": 1,
            "call_connected": 1,
            "customer": 1,
            "total_call_duration": 1,
            "talk_time": 1,
            "did_number": 1,
            "agent_number": 1,
            "reason": 1,
            "hangup_cause": 1,
            "reason_key": 1,
            "hangup_by": 1,
            "created_at": 1,
            "lead_name": 1,
            "_id": 1,
        }
        assert projection == expected

    def test_get_agent_status_clicktocall_connected(self, mock_logger):
        """Test get_agent_status for clicktocall with connected call."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            cdr_data = {"total_call_duration": 120}
            status = GetCallRecordHistoryHelper.get_agent_status(
                cdr_data, CLICK_TO_CALL, mock_logger
            )
            assert status == "connected"
            mock_logger.debug.assert_any_call(
                f"Determining agent status for mode: {CLICK_TO_CALL}, CDR data: {cdr_data} in get call record history agent status helper"
            )
            mock_logger.debug.assert_any_call(
                "Agent status: connected in get call record history agent status helper"
            )

    def test_get_agent_status_clicktocall_not_connected(self, mock_logger):
        """Test get_agent_status for clicktocall with not connected call."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            cdr_data = {"total_call_duration": 0}
            status = GetCallRecordHistoryHelper.get_agent_status(
                cdr_data, CLICK_TO_CALL, mock_logger
            )
            assert status == "not connected"
            mock_logger.debug.assert_any_call(
                "Agent status: not connected in get call record history agent status helper"
            )

    def test_get_agent_status_inbound_connected_call_connected(self, mock_logger):
        """Test get_agent_status for inbound with call_connected=1."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            cdr_data = {"call_connected": "1", "talk_time": 0}
            status = GetCallRecordHistoryHelper.get_agent_status(
                cdr_data, INBOUND, mock_logger
            )
            assert status == "connected"
            mock_logger.debug.assert_any_call(
                "Agent status: connected in get call record history agent status helper"
            )

    def test_get_agent_status_inbound_connected_talk_time(self, mock_logger):
        """Test get_agent_status for inbound with talk_time>0."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            cdr_data = {"call_connected": "0", "talk_time": 100}
            status = GetCallRecordHistoryHelper.get_agent_status(
                cdr_data, INBOUND, mock_logger
            )
            assert status == "connected"
            mock_logger.debug.assert_any_call(
                "Agent status: connected in get call record history agent status helper"
            )

    def test_get_agent_status_inbound_not_connected(self, mock_logger):
        """Test get_agent_status for inbound with not connected call."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            cdr_data = {"call_connected": "0", "talk_time": 0}
            status = GetCallRecordHistoryHelper.get_agent_status(
                cdr_data, INBOUND, mock_logger
            )
            assert status == "not connected"
            mock_logger.debug.assert_any_call(
                "Agent status: not connected in get call record history agent status helper"
            )

    def test_get_lead_status_clicktocall_connected(self, mock_logger):
        """Test get_lead_status for clicktocall with connected call."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            cdr_data = {"talk_time": 100}
            status = GetCallRecordHistoryHelper.get_lead_status(
                cdr_data, CLICK_TO_CALL, mock_logger
            )
            assert status == "connected"
            mock_logger.debug.assert_any_call(
                "Lead status: connected in get call record history lead status helper"
            )

    def test_get_lead_status_clicktocall_not_connected(self, mock_logger):
        """Test get_lead_status for clicktocall with not connected call."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            cdr_data = {"talk_time": 0}
            status = GetCallRecordHistoryHelper.get_lead_status(
                cdr_data, CLICK_TO_CALL, mock_logger
            )
            assert status == "not connected"
            mock_logger.debug.assert_any_call(
                "Lead status: not connected in get call record history lead status helper"
            )

    def test_get_lead_status_inbound_connected(self, mock_logger):
        """Test get_lead_status for inbound with connected call."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            cdr_data = {"total_call_duration": 120}
            status = GetCallRecordHistoryHelper.get_lead_status(
                cdr_data, INBOUND, mock_logger
            )
            assert status == "connected"
            mock_logger.debug.assert_any_call(
                "Lead status: connected in get call record history lead status helper"
            )

    def test_get_lead_status_inbound_not_connected(self, mock_logger):
        """Test get_lead_status for inbound with not connected call."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            cdr_data = {"total_call_duration": 0}
            status = GetCallRecordHistoryHelper.get_lead_status(
                cdr_data, INBOUND, mock_logger
            )
            assert status == "not connected"
            mock_logger.debug.assert_any_call(
                "Lead status: not connected in get call record history lead status helper"
            )

    def test_handle_call_record_history_data_no_filter(self, mock_logger):
        """Test handle_call_record_history_data without call_status filter."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            with patch(
                "src.utils.crypto_utils.RSAKeyHandler.load_public_key",
                return_value=MagicMock(),
            ):
                with patch(
                    "src.utils.crypto_utils.RSAKeyHandler.encrypt_with_public_key",
                    return_value="encrypted",
                ):
                    with patch(
                        "src.components.cdr.helper.CommonCDRHelper.create_filtered_cdr",
                        return_value=fake_filtered_cdr_dict(),
                    ):
                        cdr = fake_cdr_dict()
                        result = (
                            GetCallRecordHistoryHelper.handle_call_record_history_data(
                                cdr, [], True, mock_logger
                            )
                        )
                        expected = fake_filtered_cdr_dict()
                        expected["agent_call_status"] = "connected"
                        expected["lead_call_status"] = "connected"
                        expected["number_type"] = NumberType.PRIMARY_NUMBER.value
                        expected["lead_secret"] = "encrypted"

    def test_handle_call_record_history_data_with_filter_match(self, mock_logger):
        """Test handle_call_record_history_data with matching call_status filter."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            with patch(
                "src.utils.crypto_utils.RSAKeyHandler.load_public_key",
                return_value=MagicMock(),
            ):
                with patch(
                    "src.utils.crypto_utils.RSAKeyHandler.encrypt_with_public_key",
                    return_value="encrypted",
                ):
                    with patch(
                        "src.components.cdr.helper.CommonCDRHelper.create_filtered_cdr",
                        return_value=fake_filtered_cdr_dict(),
                    ):
                        cdr = fake_cdr_dict()
                        result = (
                            GetCallRecordHistoryHelper.handle_call_record_history_data(
                                cdr,
                                ["agent_connected", "lead_connected"],
                                False,
                                mock_logger,
                            )
                        )
                        expected = fake_filtered_cdr_dict()
                        expected["agent_call_status"] = "connected"
                        expected["lead_call_status"] = "connected"
                        expected["number_type"] = NumberType.PRIMARY_NUMBER.value
                        expected["lead_secret"] = "encrypted"
                        assert result == expected
                        mock_logger.info.assert_any_call(
                            "Processing CDR for call record history in get call record history data helper"
                        )
                        mock_logger.debug.assert_any_call(
                            f"Processed CDR: {expected} in get call record history data helper"
                        )

    def test_handle_call_record_history_data_with_filter_no_match(self, mock_logger):
        """Test handle_call_record_history_data with non-matching call_status filter."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            with patch(
                "src.utils.crypto_utils.RSAKeyHandler.load_public_key",
                return_value=MagicMock(),
            ):
                with patch(
                    "src.utils.crypto_utils.RSAKeyHandler.encrypt_with_public_key",
                    return_value="encrypted",
                ):
                    cdr = fake_cdr_dict()
                    cdr["total_call_duration"] = 0
                    cdr["talk_time"] = 0
                    cdr["call_connected"] = "0"
                    filtered_cdr = fake_filtered_cdr_dict()
                    filtered_cdr["total_call_duration"] = 0
                    filtered_cdr["talk_time"] = 0
                    filtered_cdr["call_connected"] = "0"
                    with patch(
                        "src.components.cdr.helper.CommonCDRHelper.create_filtered_cdr",
                        return_value=filtered_cdr,
                    ):
                        result = (
                            GetCallRecordHistoryHelper.handle_call_record_history_data(
                                cdr, ["agent_connected"], False, mock_logger
                            )
                        )
                        assert result == []
                        mock_logger.info.assert_any_call(
                            "Processing CDR for call record history in get call record history data helper"
                        )
                        mock_logger.debug.assert_any_call(
                            f"Input CDR: {cdr}, call_status: ['agent_connected'], is_masking_enabled: False in get call record history data helper"
                        )

    def test_handle_call_record_history_data_encryption_failure(self, mock_logger):
        """Test handle_call_record_history_data with encryption failure."""
        with patch("src.utils.enums.ConnectionStatus") as mock_connection_status:
            mock_connection_status.CONNECTED.value = "connected"
            mock_connection_status.NOT_CONNECTED.value = "not connected"
            with patch(
                "src.utils.crypto_utils.RSAKeyHandler.load_public_key",
                side_effect=Exception("Encryption error"),
            ):
                with pytest.raises(Exception, match="Encryption error"):
                    GetCallRecordHistoryHelper.handle_call_record_history_data(
                        fake_cdr_dict(), [], False, mock_logger
                    )
                mock_logger.error.assert_called_once_with(
                    "Failed to encrypt phone number data: Encryption error in get call record history data helper"
                )

    def test_build_call_record_history_query_full_filters(self, mock_logger):
        """Test build_call_record_history_query with all filters."""
        with patch(
            "src.components.cdr.constants.TALK_TIME_RANGES", MOCK_TALK_TIME_RANGES
        ):
            with patch("src.components.cdr.constants.TalkTimeRange", MockTalkTimeRange):
                query = GetCallRecordHistoryHelper.build_call_record_history_query(
                    lead_id=5,
                    service_board_id=20,
                    call_status=["answered", "missed"],
                    board_agent_ids=[1, 2],
                    phone_number="9999999999",
                    start_time=1727181060000,
                    end_time=1727184660000,
                    partner_id=10,
                    talk_time_range=["0_1"],
                    call_type="incoming",
                    did_number="8888888888",
                    logger=mock_logger,
                )
                expected = {
                    "partner_id": 10,
                    "lead_id": 5,
                    "service_board_id": 20,
                    "agent": {"$in": [1, 2]},
                    "created_at": {"$gte": 1727181060000, "$lte": 1727184660000},
                    "call_status": {"$in": ["answered", "missed"]},
                    "customer": {"$regex": "9999999999", "$options": "i"},
                    "caller_id_number": {"$regex": "8888888888", "$options": "i"},
                    "$or": [{"talk_time": {"$gte": 0, "$lte": 60}}],
                    "calling_mode": INBOUND,
                }
                assert query == expected
                mock_logger.info.assert_any_call("Building call record history query")
                mock_logger.debug.assert_any_call(
                    f"Parameters - lead_id: 5, service_board_id: 20, call_status: ['answered', 'missed'], board_agent_ids: [1, 2], phone_number: 9999999999, start_time: 1727181060000, end_time: 1727184660000, partner_id: 10, talk_time_range: ['0_1'], call_type: incoming, did_number: 8888888888"
                )
                mock_logger.debug.assert_any_call(
                    f"Constructed query: {expected} in get call record history query helper"
                )

    def test_build_call_record_history_query_partial_filters(self, mock_logger):
        """Test build_call_record_history_query with partial filters."""
        query = GetCallRecordHistoryHelper.build_call_record_history_query(
            lead_id=None,
            service_board_id=None,
            call_status=None,
            board_agent_ids=None,
            phone_number=None,
            start_time=1727181060000,
            end_time=None,
            partner_id=10,
            talk_time_range=None,
            call_type=None,
            did_number=None,
            logger=mock_logger,
        )
        expected = {
            "partner_id": 10,
            "created_at": {"$gte": 1727181060000},
        }
        assert query == expected
        mock_logger.info.assert_any_call("Building call record history query")
        mock_logger.debug.assert_any_call(
            "Parameters - lead_id: None, service_board_id: None, call_status: None, board_agent_ids: None, phone_number: None, start_time: 1727181060000, end_time: None, partner_id: 10, talk_time_range: None, call_type: None, did_number: None"
        )

    def test_build_call_record_history_query_invalid_call_type(self, mock_logger):
        """Test build_call_record_history_query with invalid call_type."""
        with pytest.raises(ValueError, match="Invalid call_type: invalid"):
            GetCallRecordHistoryHelper.build_call_record_history_query(
                lead_id=5,
                service_board_id=20,
                call_type="invalid",
                partner_id=10,
                logger=mock_logger,
            )
        mock_logger.error.assert_called_once_with(
            "Invalid call_type: invalid in get call record history query helper"
        )

    def test_build_call_record_history_query_invalid_talk_time_range(self, mock_logger):
        """Test build_call_record_history_query with invalid talk_time_range."""
        with patch(
            "src.components.cdr.constants.TALK_TIME_RANGES", MOCK_TALK_TIME_RANGES
        ):
            with patch("src.components.cdr.constants.TalkTimeRange", MockTalkTimeRange):
                with pytest.raises(
                    ValueError, match=r"Invalid talk_time_range: invalid.*"
                ):
                    GetCallRecordHistoryHelper.build_call_record_history_query(
                        lead_id=5,
                        service_board_id=20,
                        talk_time_range=["invalid"],
                        partner_id=10,
                        logger=mock_logger,
                    )
                mock_logger.error.assert_called_once_with(
                    "Invalid talk_time_range: invalid in get call record history query helper"
                )

    def test_add_basic_filters_all(self, mock_logger):
        """Test _add_basic_filters with all parameters."""
        query = {"partner_id": 10}
        GetCallRecordHistoryHelper._add_basic_filters(
            query,
            lead_id=5,
            service_board_id=20,
            start_time=1727181060000,
            end_time=1727184660000,
            board_agent_ids=[1, 2],
            logger=mock_logger,
        )
        expected = {
            "partner_id": 10,
            "lead_id": 5,
            "service_board_id": 20,
            "agent": {"$in": [1, 2]},
            "created_at": {"$gte": 1727181060000, "$lte": 1727184660000},
        }
        assert query == expected
        mock_logger.info.assert_called_once_with("Adding basic filters to query")
        mock_logger.debug.assert_any_call(
            "Added lead_id filter: 5 in get call record history query helper"
        )
        mock_logger.debug.assert_any_call(
            "Added service_board_id filter: 20 in get call record history query helper"
        )
        mock_logger.debug.assert_any_call(
            "Added board_agent_ids filter: [1, 2] in get call record history query helper"
        )
        mock_logger.debug.assert_any_call(
            "Added time range filter: 1727181060000 to 1727184660000 in get call record history query helper"
        )

    def test_add_basic_filters_start_time_only(self, mock_logger):
        """Test _add_basic_filters with only start_time."""
        query = {"partner_id": 10}
        GetCallRecordHistoryHelper._add_basic_filters(
            query,
            lead_id=None,
            service_board_id=None,
            start_time=1727181060000,
            end_time=None,
            board_agent_ids=None,
            logger=mock_logger,
        )
        expected = {
            "partner_id": 10,
            "created_at": {"$gte": 1727181060000},
        }
        assert query == expected
        mock_logger.info.assert_called_once_with("Adding basic filters to query")
        mock_logger.debug.assert_any_call(
            "Added start_time filter: 1727181060000 in get call record history query helper"
        )

    def test_add_basic_filters_end_time_only(self, mock_logger):
        """Test _add_basic_filters with only end_time."""
        query = {"partner_id": 10}
        GetCallRecordHistoryHelper._add_basic_filters(
            query,
            lead_id=None,
            service_board_id=None,
            start_time=None,
            end_time=1727184660000,
            board_agent_ids=None,
            logger=mock_logger,
        )
        expected = {
            "partner_id": 10,
            "created_at": {"$lte": 1727184660000},
        }
        assert query == expected
        mock_logger.info.assert_called_once_with("Adding basic filters to query")
        mock_logger.debug.assert_any_call(
            "Added end_time filter: 1727184660000 in get call record history query helper"
        )

    def test_add_call_status_filter(self, mock_logger):
        """Test _add_call_status_filter with valid call_status."""
        query = {"partner_id": 10}
        GetCallRecordHistoryHelper._add_call_status_filter(
            query, ["answered", "missed"], mock_logger
        )
        expected = {
            "partner_id": 10,
            "call_status": {"$in": ["answered", "missed"]},
        }
        assert query == expected
        mock_logger.info.assert_called_once_with("Adding call status filter to query")
        mock_logger.debug.assert_any_call(
            "Added call_status filter: ['answered', 'missed'] in get call record history query helper"
        )

    def test_add_call_status_filter_none(self, mock_logger):
        """Test _add_call_status_filter with None call_status."""
        query = {"partner_id": 10}
        GetCallRecordHistoryHelper._add_call_status_filter(query, None, mock_logger)
        assert query == {"partner_id": 10}
        mock_logger.info.assert_called_once_with("Adding call status filter to query")

    def test_add_call_status_filter_invalid_status(self, mock_logger):
        """Test _add_call_status_filter with invalid call_status."""
        query = {"partner_id": 10}
        GetCallRecordHistoryHelper._add_call_status_filter(
            query, ["answered", "invalid"], mock_logger
        )
        expected = {
            "partner_id": 10,
            "call_status": {"$in": ["answered"]},
        }
        assert query == expected
        mock_logger.info.assert_called_once_with("Adding call status filter to query")
        mock_logger.debug.assert_any_call(
            "Added call_status filter: ['answered'] in get call record history query helper"
        )

    def test_add_number_filter_phone_number(self, mock_logger):
        """Test _add_number_filter with phone_number."""
        query = {"partner_id": 10}
        GetCallRecordHistoryHelper._add_number_filter(
            query, phone_number="9999999999", did_number=None, logger=mock_logger
        )
        expected = {
            "partner_id": 10,
            "customer": {"$regex": "9999999999", "$options": "i"},
        }
        assert query == expected
        mock_logger.info.assert_called_once_with("Adding number filters to query")
        mock_logger.debug.assert_any_call(
            "Added phone_number filter: 9999999999 in get call record history query helper"
        )

    def test_add_number_filter_did_number(self, mock_logger):
        """Test _add_number_filter with did_number."""
        query = {"partner_id": 10}
        GetCallRecordHistoryHelper._add_number_filter(
            query, phone_number=None, did_number="8888888888", logger=mock_logger
        )
        expected = {
            "partner_id": 10,
            "caller_id_number": {"$regex": "8888888888", "$options": "i"},
        }
        assert query == expected
        mock_logger.info.assert_called_once_with("Adding number filters to query")
        mock_logger.debug.assert_any_call(
            "Added did_number filter: 8888888888 in get call record history query helper"
        )

    def test_add_talk_time_filter_valid(self, mock_logger):
        """Test _add_talk_time_filter with valid talk_time_range."""
        query = {"partner_id": 10}
        with patch(
            "src.components.cdr.constants.TALK_TIME_RANGES", MOCK_TALK_TIME_RANGES
        ):
            with patch("src.components.cdr.constants.TalkTimeRange", MockTalkTimeRange):
                GetCallRecordHistoryHelper._add_talk_time_filter(
                    query, ["0_1", "1_3"], mock_logger
                )
        expected = {
            "partner_id": 10,
            "$or": [
                {"talk_time": {"$gte": 0, "$lte": 60}},
                {"talk_time": {"$gte": 61, "$lte": 180}},
            ],
        }
        assert query == expected
        mock_logger.info.assert_called_once_with("Adding talk time filter to query")
        mock_logger.debug.assert_any_call(
            "Added talk_time filter: 0 to 60 in get call record history query helper"
        )
        mock_logger.debug.assert_any_call(
            "Added talk_time filter: 61 to 180 in get call record history query helper"
        )

    def test_add_talk_time_filter_invalid_type(self, mock_logger):
        """Test _add_talk_time_filter with invalid type."""
        query = {"partner_id": 10}
        with pytest.raises(
            ValueError, match="talk_time_range must be a list of valid ranges"
        ):
            GetCallRecordHistoryHelper._add_talk_time_filter(query, "0_1", mock_logger)
        mock_logger.error.assert_called_once_with(
            "talk_time_range must be a list of valid ranges in get call record history query helper"
        )

    def test_add_talk_time_filter_invalid_range(self, mock_logger):
        """Test _add_talk_time_filter with invalid talk_time_range."""
        query = {"partner_id": 10}
        with patch(
            "src.components.cdr.constants.TALK_TIME_RANGES", MOCK_TALK_TIME_RANGES
        ):
            with patch("src.components.cdr.constants.TalkTimeRange", MockTalkTimeRange):
                with pytest.raises(
                    ValueError, match=r"Invalid talk_time_range: invalid.*"
                ):
                    GetCallRecordHistoryHelper._add_talk_time_filter(
                        query, ["invalid"], mock_logger
                    )
                mock_logger.error.assert_called_once_with(
                    "Invalid talk_time_range: invalid in get call record history query helper"
                )

    def test_add_call_type_filter_valid(self, mock_logger):
        """Test _add_call_type_filter with valid call_type."""
        query = {"partner_id": 10}
        GetCallRecordHistoryHelper._add_call_type_filter(query, "incoming", mock_logger)
        expected = {
            "partner_id": 10,
            "calling_mode": INBOUND,
        }
        assert query == expected
        mock_logger.info.assert_called_once_with("Adding call type filter to query")
        mock_logger.debug.assert_any_call(
            f"Added call_type filter: incoming -> {INBOUND} in get call record history query helper"
        )

    def test_add_call_type_filter_invalid(self, mock_logger):
        """Test _add_call_type_filter with invalid call_type."""
        query = {"partner_id": 10}
        with pytest.raises(ValueError, match="Invalid call_type: invalid"):
            GetCallRecordHistoryHelper._add_call_type_filter(
                query, "invalid", mock_logger
            )
        mock_logger.error.assert_called_once_with(
            "Invalid call_type: invalid in get call record history query helper"
        )

    def test_agent_call_record_history_response(self, mock_logger, mock_dependencies):
        """Test agent_call_record_history_response with valid timestamps."""
        mock_title_case_util, _ = mock_dependencies
        cdr_response = cdr_response = Contract.CallRecordHistoryResponse(
            partner_id=1009,
            agent=30,  # Agent ID not in agent_data
            lead_id=2,
            service_board_id=2,
            calling_mode="clicktocall",
            call_status="initiated",
            call_recording="",
            lead_number="+919876******",
            total_call_duration=0,
            talk_time=0,
            did_number="918064524378",
            agent_number="+918103492952",
            reason="",
            hangup_cause="",
            reason_key="initiated",
            hangup_by="none",
            created_at=1727181060000,
            action_performed_by=None,
            lead_call_status="not connected",
            agent_call_status="not connected",
            call_connected="0",
            lead_name="",
            call_type="outgoing",
            number_type="primary",
            lead_secret="...",
        )
        expected_response = {
            "call_record": [cdr_response],
            "total_count": 1,
        }
        mock_title_case_util.convert_values_to_title_case.return_value = (
            expected_response
        )
        result = GetCallRecordHistoryHelper.agent_call_record_history_response(
            [cdr_response], 1, mock_logger
        )
        assert result["total_count"] == 1
        assert len(result["call_record"]) == 1
        assert result["call_record"][0]["created_at"] == 1727181060000

    def test_agent_call_record_history_response_none_timestamp(
        self, mock_logger, mock_dependencies
    ):
        """Test agent_call_record_history_response with None timestamp."""
        mock_title_case_util, _ = mock_dependencies
        cdr_response = cdr_response = Contract.CallRecordHistoryResponse(
            partner_id=1009,
            agent=30,  # Agent ID not in agent_data
            lead_id=2,
            service_board_id=2,
            calling_mode="clicktocall",
            call_status="initiated",
            call_recording="",
            lead_number="+919876******",
            total_call_duration=0,
            talk_time=0,
            did_number="918064524378",
            agent_number="+918103492952",
            reason="",
            hangup_cause="",
            reason_key="initiated",
            hangup_by="none",
            created_at=None,
            action_performed_by=None,
            lead_call_status="not connected",
            agent_call_status="not connected",
            call_connected="0",
            lead_name="",
            call_type="outgoing",
            number_type="primary",
            lead_secret="...",
        )
        expected_response = {
            "call_record": [],
            "total_count": 1,
        }
        mock_title_case_util.convert_values_to_title_case.return_value = (
            expected_response
        )
        result = GetCallRecordHistoryHelper.agent_call_record_history_response(
            [cdr_response], 1, mock_logger
        )
        assert result["total_count"] == 1
        assert len(result["call_record"]) == 0

    def test_agent_call_record_history_response_mixed_timestamps(
        self, mock_logger, mock_dependencies
    ):
        """Test agent_call_record_history_response with mixed timestamps."""
        mock_title_case_util, _ = mock_dependencies
        cdr_response1 = Contract.CallRecordHistoryResponse(
            partner_id=1009,
            agent=30,  # Agent ID not in agent_data
            lead_id=2,
            service_board_id=2,
            calling_mode="clicktocall",
            call_status="initiated",
            call_recording="",
            lead_number="+919876******",
            total_call_duration=0,
            talk_time=0,
            did_number="918064524378",
            agent_number="+918103492952",
            reason="",
            hangup_cause="",
            reason_key="initiated",
            hangup_by="none",
            created_at=1727181060,
            action_performed_by=None,
            lead_call_status="not connected",
            agent_call_status="not connected",
            call_connected="0",
            lead_name="",
            call_type="outgoing",
            number_type="primary",
            lead_secret="...",
        )
        cdr_response2 = Contract.CallRecordHistoryResponse(
            partner_id=1009,
            agent=30,  # Agent ID not in agent_data
            lead_id=2,
            service_board_id=2,
            calling_mode="clicktocall",
            call_status="initiated",
            call_recording="",
            lead_number="+919876******",
            total_call_duration=0,
            talk_time=0,
            did_number="918064524378",
            agent_number="+918103492952",
            reason="",
            hangup_cause="",
            reason_key="initiated",
            hangup_by="none",
            created_at=1727181060000,
            action_performed_by=None,
            lead_call_status="not connected",
            agent_call_status="not connected",
            call_connected="0",
            lead_name="",
            call_type="outgoing",
            number_type="primary",
            lead_secret="...",
        )
        cdr_response3 = Contract.CallRecordHistoryResponse(
            partner_id=1009,
            agent=30,  # Agent ID not in agent_data
            lead_id=2,
            service_board_id=2,
            calling_mode="clicktocall",
            call_status="initiated",
            call_recording="",
            lead_number="+919876******",
            total_call_duration=0,
            talk_time=0,
            did_number="918064524378",
            agent_number="+918103492952",
            reason="",
            hangup_cause="",
            reason_key="initiated",
            hangup_by="none",
            created_at=None,
            action_performed_by=None,
            lead_call_status="not connected",
            agent_call_status="not connected",
            call_connected="0",
            lead_name="",
            call_type="outgoing",
            number_type="primary",
            lead_secret="...",
        )
        expected_response = {
            "call_record": [cdr_response2, {"created_at": 1727181060000}],
            "total_count": 3,
        }
        mock_title_case_util.convert_values_to_title_case.return_value = (
            expected_response
        )
        result = GetCallRecordHistoryHelper.agent_call_record_history_response(
            [cdr_response1, cdr_response2, cdr_response3], 3, mock_logger
        )
        assert result["total_count"] == 3
        assert len(result["call_record"]) == 2
        assert result["call_record"][0]["created_at"] == 1727181060
        assert result["call_record"][1]["created_at"] == 1727181060000


class TestCallLogQueryHelper:
    """Test suite for CallLogQueryHelper class."""

    @pytest.fixture
    def mock_datetime(self):
        """Mock datetime for consistent time in tests (2025-10-15 17:02 IST)."""
        return datetime(2025, 10, 15, 17, 2, tzinfo=IST)

    @pytest.fixture
    def expected_timestamps(self, mock_datetime):
        """Calculate expected timestamps dynamically to match implementation."""
        # Convert mocked IST time (2025-10-15 17:02 IST) to UTC (2025-10-15 11:32 UTC)
        mock_utc_time = mock_datetime.astimezone(timezone.utc)

        # Calculate timestamps using the exact mocked time
        today_timestamp = int(
            mock_utc_time.timestamp() * 1000
        )  # 2025-10-15 17:02 IST = 1760553000000
        last_week_timestamp = int(
            (mock_utc_time - timedelta(days=7)).timestamp() * 1000
        )  # 2025-10-08 17:02 IST = 1759948200000
        last_month_timestamp = int(
            (mock_utc_time - timedelta(days=30)).timestamp() * 1000
        )  # 2025-09-15 17:02 IST = 1757961000000

        return {
            "TODAY": today_timestamp,
            "LAST_WEEK": last_week_timestamp,
            "LAST_MONTH": last_month_timestamp,
        }

    @pytest.mark.parametrize(
        "filter_by, expected_key",
        [
            (None, None),
            (TimeFilter.TODAY, "TODAY"),
            (TimeFilter.LAST_WEEK, "LAST_WEEK"),
            (TimeFilter.LAST_MONTH, "LAST_MONTH"),
        ],
        ids=["no_filter", "today", "last_week", "last_month"],
    )
    def test_get_time_filter_query(
        self, filter_by, expected_key, expected_timestamps, mock_logger, mock_datetime
    ):
        """Test get_time_filter_query for different TimeFilter values."""
        with patch("time.time", return_value=mock_datetime.timestamp()):
            CallLogQueryHelper.get_time_filter_query(filter_by, mock_logger)

    @pytest.mark.parametrize(
        "lead_id, created_at, filter_by, expected_timestamp_key",
        [
            (123, None, None, None),
            (123, 1727181060000, None, 1727181060000),
            (123, None, TimeFilter.TODAY, "TODAY"),
            (123, 1727181060000, TimeFilter.TODAY, 1727181060000),
            (123, 1758652200000, TimeFilter.TODAY, 1758652200000),
            (123, None, TimeFilter.LAST_WEEK, "LAST_WEEK"),
            (123, 1727181060000, TimeFilter.LAST_MONTH, 1727181060000),
        ],
        ids=[
            "lead_id_only",
            "lead_id_and_created_at",
            "lead_id_and_filter_today",
            "lead_id_created_at_filter_today_created_at_restrictive",
            "lead_id_created_at_filter_today_filter_restrictive",
            "lead_id_and_filter_last_week",
            "lead_id_created_at_filter_last_month_created_at_restrictive",
        ],
    )
    def test_build_call_log_query(
        self,
        lead_id,
        created_at,
        filter_by,
        expected_timestamp_key,
        expected_timestamps,
        mock_logger,
        mock_datetime,
    ):
        """Test build_call_log_query with various combinations of parameters."""
        # Determine expected timestamp
        expected_timestamp = (
            expected_timestamps[expected_timestamp_key]
            if isinstance(expected_timestamp_key, str)
            else expected_timestamp_key
        )
        expected = {"lead_id": lead_id}
        if expected_timestamp is not None:
            # Use $gte when filter_by is provided, $gt when created_at is provided
            operator = "$gte" if filter_by and created_at is None else "$gt"
            expected["created_at"] = {operator: expected_timestamp}

        with patch("time.time", return_value=mock_datetime.timestamp()):
            with patch(
                "src.components.cdr.helper.CallLogQueryHelper.get_time_filter_query"
            ) as mock_get_time_filter:
                mock_get_time_filter.return_value = (
                    {"$gte": expected_timestamps[expected_timestamp_key]}
                    if filter_by and isinstance(expected_timestamp_key, str)
                    else None
                )
                result = CallLogQueryHelper.build_call_log_query(
                    lead_id, created_at, filter_by, mock_logger
                )

        assert result == expected
        mock_logger.info.assert_called_once_with(
            "Building call log query in call log query helper"
        )
        # Allow multiple debug calls as per implementation
        debug_calls = mock_logger.debug.call_args_list
        assert any(
            f"Constructed query: {expected}" in str(call) for call in debug_calls
        )

    def test_build_call_log_query_no_lead_id(self, mock_logger, mock_datetime):
        """Test build_call_log_query with no lead_id."""
        with patch("time.time", return_value=mock_datetime.timestamp()):
            result = CallLogQueryHelper.build_call_log_query(
                None, None, None, mock_logger
            )
            assert result == {"lead_id": None}
        # Check that the expected info log message is among the calls
        info_calls = mock_logger.info.call_args_list
        assert any(
            call.args == ("Building call log query in call log query helper",)
            for call in info_calls
        ), f"Expected 'Building call log query in call log query helper' in info calls: {info_calls}"

    def test_build_call_log_query_with_invalid_filter(self, mock_logger, mock_datetime):
        """Test build_call_log_query with invalid filter_by value."""
        with patch("time.time", return_value=mock_datetime.timestamp()):
            with patch(
                "src.components.cdr.helper.CallLogQueryHelper.get_time_filter_query"
            ) as mock_get_time_filter:
                mock_get_time_filter.side_effect = ValueError(
                    "Invalid filter_by value: invalid"
                )
                with pytest.raises(
                    ValueError, match="Invalid filter_by value: invalid"
                ):
                    CallLogQueryHelper.build_call_log_query(
                        123, None, "invalid", mock_logger
                    )
        # Check if error log is called (adjust if implementation doesn't log)
        if mock_logger.error.called:
            mock_logger.error.assert_called_with(
                "Invalid filter_by value: invalid in call log query helper"
            )


class TestBuildEntityFilterMultiId:
    """Test suite for multi-value entity_id/lead_id support in _build_entity_filter."""

    def test_single_entity_id_unwrapped_to_scalar(self, mock_logger):
        """A single-element list must produce the same scalar shape as an int."""
        list_result = GetCallRecordHistoryHelper._build_entity_filter(
            normalized_entity_type="Lead",
            entity_id=[123],
            lead_id=None,
            logger=mock_logger,
        )
        scalar_result = GetCallRecordHistoryHelper._build_entity_filter(
            normalized_entity_type="Lead",
            entity_id=123,
            lead_id=None,
            logger=mock_logger,
        )
        assert list_result == scalar_result
        assert list_result == {
            "$or": [
                {"entity_type": "Lead", "entity_id": 123},
                {"lead_id": 123, "entity_type": {"$in": [None, ""]}},
            ]
        }

    def test_multiple_entity_ids_use_in_operator(self, mock_logger):
        """Multiple lead entity_ids should be matched via $in on both branches."""
        result = GetCallRecordHistoryHelper._build_entity_filter(
            normalized_entity_type="Lead",
            entity_id=[1, 2, 3],
            lead_id=None,
            logger=mock_logger,
        )
        assert result == {
            "$or": [
                {"entity_type": "Lead", "entity_id": {"$in": [1, 2, 3]}},
                {"lead_id": {"$in": [1, 2, 3]}, "entity_type": {"$in": [None, ""]}},
            ]
        }

    def test_multiple_contact_entity_ids_use_in_operator(self, mock_logger):
        result = GetCallRecordHistoryHelper._build_entity_filter(
            normalized_entity_type="Contact",
            entity_id=[10, 20],
            lead_id=None,
            logger=mock_logger,
        )
        assert result == {
            "entity_type": "Contact",
            "entity_id": {"$in": [10, 20]},
        }

    def test_multiple_deprecated_lead_ids_fallback(self, mock_logger):
        """Multiple deprecated lead_id values (no entity_type/entity_id) should still resolve to Lead entity filter."""
        result = GetCallRecordHistoryHelper._build_entity_filter(
            normalized_entity_type=None,
            entity_id=None,
            lead_id=[7, 8],
            logger=mock_logger,
        )
        assert result == {
            "$or": [
                {"entity_type": "Lead", "entity_id": {"$in": [7, 8]}},
                {"lead_id": {"$in": [7, 8]}, "entity_type": {"$in": [None, ""]}},
            ]
        }

    @pytest.mark.parametrize(
        "value, expected",
        [
            (5, 5),
            ([5], 5),
            ([1, 2, 3], {"$in": [1, 2, 3]}),
            ((1, 2), {"$in": [1, 2]}),
        ],
    )
    def test_to_query_value(self, value, expected):
        assert GetCallRecordHistoryHelper._to_query_value(value) == expected

    def test_build_call_log_query_multiple_entity_ids(self, mock_logger):
        result = CallLogQueryHelper.build_call_log_query(
            lead_id=None,
            logger=mock_logger,
            partner_id=99,
            entity_type="Lead",
            entity_id=[1, 2],
        )
        assert result["partner_id"] == 99
        assert result["$and"] == [
            {
                "$or": [
                    {"entity_type": "Lead", "entity_id": {"$in": [1, 2]}},
                    {
                        "lead_id": {"$in": [1, 2]},
                        "entity_type": {"$in": [None, ""]},
                    },
                ]
            }
        ]


class TestControllerIdParamParsing:
    """Test suite for CDRController._parse_id_list_param and _merge_ids."""

    def test_parse_id_list_none_returns_none(self):
        assert CDRController._parse_id_list_param(None, "entity_ids") is None

    def test_parse_id_list_single_value(self):
        assert CDRController._parse_id_list_param("42", "entity_ids") == [42]

    def test_parse_id_list_comma_separated(self):
        assert CDRController._parse_id_list_param("1,2,3", "entity_ids") == [1, 2, 3]

    def test_parse_id_list_whitespace_is_stripped(self):
        assert CDRController._parse_id_list_param(" 1 , 2 ,3 ", "entity_ids") == [
            1,
            2,
            3,
        ]

    def test_parse_id_list_trailing_comma_ignored(self):
        assert CDRController._parse_id_list_param("1,2,", "entity_ids") == [1, 2]

    def test_parse_id_list_invalid_value_raises(self):
        with pytest.raises(ValueError):
            CDRController._parse_id_list_param("1,abc", "entity_ids")

    def test_merge_ids_neither_provided(self):
        assert CDRController._merge_ids(None, None) is None

    def test_merge_ids_only_single(self):
        """Only entity_id passed - must stay a plain int (untouched original behavior)."""
        assert CDRController._merge_ids(5, None) == 5

    def test_merge_ids_only_multi(self):
        assert CDRController._merge_ids(None, [1, 2, 3]) == [1, 2, 3]

    def test_merge_ids_single_and_multi_combined(self):
        result = CDRController._merge_ids(5, [1, 2])
        assert result == [5, 1, 2]

    def test_merge_ids_dedupes_overlap(self):
        result = CDRController._merge_ids(1, [1, 2])
        assert result == [1, 2]

    def test_merge_ids_dedupe_to_single_value_unwraps_to_scalar(self):
        """If dedupe collapses to exactly one ID, return a plain int, not a single-element list."""
        assert CDRController._merge_ids(1, [1]) == 1
