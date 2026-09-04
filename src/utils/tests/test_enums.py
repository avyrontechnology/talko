import pytest
from src.utils.enums import (
    VendorType,
    NumberType,
    TimeFilter,
    CallStatus,
    HangupCause,
    ReasonKey,
    RingType,
    UserRoleHierarchy,
    ConnectionStatus,
)


class TestVendorType:
    def test_enum_values(self):
        assert VendorType.AIRTEL.value == "airtel"
        assert VendorType.TATA_TELE.value == "tata_tele"
        assert VendorType.KNOWLARITY.value == "knowlarity"
        assert VendorType.ACEFHONE.value == "acefhone"


class TestNumberType:
    def test_enum_values(self):
        assert NumberType.PRIMARY_NUMBER.value == "primary"
        assert NumberType.WHATSAPP_NUMBER.value == "whatsapp"
        assert NumberType.ADDITIONAL_NUMBER.value == "alternate"


class TestTimeFilter:
    def test_enum_values(self):
        assert TimeFilter.TODAY.value == "Today"
        assert TimeFilter.LAST_WEEK.value == "Last week"
        assert TimeFilter.LAST_MONTH.value == "Last month"


class TestCallStatus:
    def test_enum_values(self):
        assert CallStatus.UNKNOWN.value == "Unknown Status"
        assert CallStatus.NOANSWER.value == "No Answer"
        assert CallStatus.BUSY.value == "Busy"


class TestHangupCause:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (None, HangupCause.UNKNOWN),
            ("cancel", HangupCause.CANCELED),
            ("chanunavail", HangupCause.CHANUNAVAIL),
            ("disconnected_by_callee", HangupCause.DISCONNECTED_BY_CALLEE),
            ("disconnected_by_caller", HangupCause.DISCONNECTED_BY_CALLER),
            ("noanswer", HangupCause.NOANSWER),
            ("no answer", HangupCause.NOANSWER),
            ("NO ANSWER", HangupCause.NOANSWER),
            ("busy", HangupCause.BUSY),
            ("BUSY", HangupCause.BUSY),
            ("CONGESTION", HangupCause.CONGESTION),
            ("FAILED", HangupCause.FAILED),
            ("Facility rejected", HangupCause.FACILITY_REJECTED),
            ("NormalClearing", HangupCause.NORMAL_CLEARING),
            ("congestion", HangupCause.CONGESTION),
        ],
    )
    def test_from_raw_known_values(self, raw, expected):
        assert HangupCause.from_raw(raw) == expected

    def test_from_raw_normalized_match(self, monkeypatch):
        """Covers normalize_auto_format + for loop match"""
        monkeypatch.setattr(
            "src.utils.enums.normalize_auto_format", lambda v: "Normal clearing"
        )
        assert HangupCause.from_raw("random value") == HangupCause.NORMAL_CLEARING

    def test_from_raw_fallback_unknown(self, monkeypatch):
        monkeypatch.setattr(
            "src.utils.enums.normalize_auto_format", lambda v: "Unmatched value"
        )
        assert HangupCause.from_raw("random") == HangupCause.UNKNOWN


class TestReasonKey:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (None, ReasonKey.HANDLE_NONE),
            ("", ReasonKey.HANDLE_NONE),
            ("Call Disconnected By Callee", ReasonKey.DISCONNECTED_BY_CALLEE),
            ("Call Disconnected By Caller", ReasonKey.DISCONNECTED_BY_CALLER),
            ("Calls dropped", ReasonKey.DROPPED),
            ("cancel", ReasonKey.CANCELED),
            ("initiated", ReasonKey.INITIATED),
            ("noanswer", ReasonKey.NOANSWER),
            ("no answer", ReasonKey.NOANSWER),
            ("NO ANSWER", ReasonKey.NOANSWER),
            ("Congestion in network", ReasonKey.CONGESTION_IN_NETWORK),
            ("busy", ReasonKey.BUSY),
        ],
    )
    def test_from_raw_known_values(self, raw, expected):
        assert ReasonKey.from_raw(raw) == expected

    def test_from_raw_normalized_match(self, monkeypatch):
        monkeypatch.setattr(
            "src.utils.enums.normalize_auto_format", lambda v: "Calls Dropped"
        )
        assert ReasonKey.from_raw("something") == ReasonKey.DROPPED

    def test_from_raw_fallback_unknown(self, monkeypatch):
        monkeypatch.setattr(
            "src.utils.enums.normalize_auto_format", lambda v: "Unknown something"
        )
        assert ReasonKey.from_raw("other") == ReasonKey.UNKNOWN


class TestRingType:
    def test_enum_values(self):
        assert RingType.ORDER_BY.value == "order_by"
        assert RingType.SIMULTANEOUS.value == "simultaneous"


class TestUserRoleHierarchy:
    def test_enum_values(self):
        assert UserRoleHierarchy.ADMIN == 1
        assert UserRoleHierarchy.AGENT == 8
        assert isinstance(UserRoleHierarchy.MANAGER.value, int)


class TestConnectionStatus:
    def test_enum_values(self):
        assert ConnectionStatus.CONNECTED.value == "connected"
        assert ConnectionStatus.NOT_CONNECTED.value == "not connected"
