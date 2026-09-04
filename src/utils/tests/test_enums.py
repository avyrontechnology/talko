import pytest
from src.utils.enums import (
    TalkoVendorType,
    TalkoNumberType,
    TalkoTimeFilter,
    TalkoCallStatus,
    TalkoHangupCause,
    TalkoReasonKey,
    TalkoRingType,
    TalkoUserRoleHierarchy,
    TalkoConnectionStatus,
)


class TestVendorType:
    def test_enum_values(self):
        assert TalkoVendorType.AIRTEL.value == "airtel"
        assert TalkoVendorType.TATA_TELE.value == "tata_tele"
        assert TalkoVendorType.KNOWLARITY.value == "knowlarity"
        assert TalkoVendorType.ACEFHONE.value == "acefhone"


class TestNumberType:
    def test_enum_values(self):
        assert TalkoNumberType.PRIMARY_NUMBER.value == "primary"
        assert TalkoNumberType.WHATSAPP_NUMBER.value == "whatsapp"
        assert TalkoNumberType.ADDITIONAL_NUMBER.value == "alternate"


class TestTimeFilter:
    def test_enum_values(self):
        assert TalkoTimeFilter.TODAY.value == "Today"
        assert TalkoTimeFilter.LAST_WEEK.value == "Last week"
        assert TalkoTimeFilter.LAST_MONTH.value == "Last month"


class TestCallStatus:
    def test_enum_values(self):
        assert TalkoCallStatus.UNKNOWN.value == "Unknown Status"
        assert TalkoCallStatus.NOANSWER.value == "No Answer"
        assert TalkoCallStatus.BUSY.value == "Busy"


class TestHangupCause:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (None, TalkoHangupCause.UNKNOWN),
            ("cancel", TalkoHangupCause.CANCELED),
            ("chanunavail", TalkoHangupCause.CHANUNAVAIL),
            ("disconnected_by_callee", TalkoHangupCause.DISCONNECTED_BY_CALLEE),
            ("disconnected_by_caller", TalkoHangupCause.DISCONNECTED_BY_CALLER),
            ("noanswer", TalkoHangupCause.NOANSWER),
            ("no answer", TalkoHangupCause.NOANSWER),
            ("NO ANSWER", TalkoHangupCause.NOANSWER),
            ("busy", TalkoHangupCause.BUSY),
            ("BUSY", TalkoHangupCause.BUSY),
            ("CONGESTION", TalkoHangupCause.CONGESTION),
            ("FAILED", TalkoHangupCause.FAILED),
            ("Facility rejected", TalkoHangupCause.FACILITY_REJECTED),
            ("NormalClearing", TalkoHangupCause.NORMAL_CLEARING),
            ("congestion", TalkoHangupCause.CONGESTION),
        ],
    )
    def test_from_raw_known_values(self, raw, expected):
        assert TalkoHangupCause.from_raw(raw) == expected

    def test_from_raw_normalized_match(self, monkeypatch):
        """Covers normalize_auto_format + for loop match"""
        monkeypatch.setattr(
            "src.utils.enums.normalize_auto_format", lambda v: "Normal clearing"
        )
        assert TalkoHangupCause.from_raw("random value") == TalkoHangupCause.NORMAL_CLEARING

    def test_from_raw_fallback_unknown(self, monkeypatch):
        monkeypatch.setattr(
            "src.utils.enums.normalize_auto_format", lambda v: "Unmatched value"
        )
        assert TalkoHangupCause.from_raw("random") == TalkoHangupCause.UNKNOWN


class TestReasonKey:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (None, TalkoReasonKey.HANDLE_NONE),
            ("", TalkoReasonKey.HANDLE_NONE),
            ("Call Disconnected By Callee", TalkoReasonKey.DISCONNECTED_BY_CALLEE),
            ("Call Disconnected By Caller", TalkoReasonKey.DISCONNECTED_BY_CALLER),
            ("Calls dropped", TalkoReasonKey.DROPPED),
            ("cancel", TalkoReasonKey.CANCELED),
            ("initiated", TalkoReasonKey.INITIATED),
            ("noanswer", TalkoReasonKey.NOANSWER),
            ("no answer", TalkoReasonKey.NOANSWER),
            ("NO ANSWER", TalkoReasonKey.NOANSWER),
            ("Congestion in network", TalkoReasonKey.CONGESTION_IN_NETWORK),
            ("busy", TalkoReasonKey.BUSY),
        ],
    )
    def test_from_raw_known_values(self, raw, expected):
        assert TalkoReasonKey.from_raw(raw) == expected

    def test_from_raw_normalized_match(self, monkeypatch):
        monkeypatch.setattr(
            "src.utils.enums.normalize_auto_format", lambda v: "Calls Dropped"
        )
        assert TalkoReasonKey.from_raw("something") == TalkoReasonKey.DROPPED

    def test_from_raw_fallback_unknown(self, monkeypatch):
        monkeypatch.setattr(
            "src.utils.enums.normalize_auto_format", lambda v: "Unknown something"
        )
        assert TalkoReasonKey.from_raw("other") == TalkoReasonKey.UNKNOWN


class TestRingType:
    def test_enum_values(self):
        assert TalkoRingType.ORDER_BY.value == "order_by"
        assert TalkoRingType.SIMULTANEOUS.value == "simultaneous"


class TestUserRoleHierarchy:
    def test_enum_values(self):
        assert TalkoUserRoleHierarchy.ADMIN == 1
        assert TalkoUserRoleHierarchy.AGENT == 8
        assert isinstance(TalkoUserRoleHierarchy.MANAGER.value, int)


class TestConnectionStatus:
    def test_enum_values(self):
        assert TalkoConnectionStatus.CONNECTED.value == "connected"
        assert TalkoConnectionStatus.NOT_CONNECTED.value == "not connected"
