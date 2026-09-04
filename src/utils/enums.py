from enum import Enum
from typing import Optional

from src.utils.auto_format import normalize_auto_format


class VendorType(str, Enum):
    AIRTEL = "airtel"
    TATA_TELE = "tata_tele"
    KNOWLARITY = "knowlarity"
    ACEFHONE = "acefhone"


class NumberType(str, Enum):
    PRIMARY_NUMBER = "primary"
    WHATSAPP_NUMBER = "whatsapp"
    ADDITIONAL_NUMBER = "alternate"


class TimeFilter(str, Enum):
    TODAY = "Today"
    LAST_WEEK = "Last week"
    LAST_MONTH = "Last month"


class CallStatus(str, Enum):
    UNKNOWN = "Unknown Status"
    CANCELED = "Cancelled"
    NOANSWER = "No Answer"
    DISCONNECTED_BY_CALLEE = "Disconnected by Callee"
    DISCONNECTED_BY_CALLER = "Disconnected by Caller"
    BUSY = "Busy"


class HangupCause(str, Enum):
    UNKNOWN = "Unknown Status"
    CANCELED = CallStatus.CANCELED.value
    CHANUNAVAIL = "Channel Unavailable"
    DISCONNECTED_BY_CALLEE = CallStatus.DISCONNECTED_BY_CALLEE.value
    DISCONNECTED_BY_CALLER = CallStatus.DISCONNECTED_BY_CALLER.value
    NOANSWER = CallStatus.NOANSWER.value
    BUSY = CallStatus.BUSY.value
    CONGESTION = "Congestion"
    FAILED = "Failed"
    FACILITY_REJECTED = "Facility rejected"
    NORMAL_CLEARING = "Normal clearing"

    @classmethod
    def from_raw(cls, value: Optional[str]) -> "HangupCause":
        mapping = {
            None: cls.UNKNOWN,
            "cancel": cls.CANCELED,
            "chanunavail": cls.CHANUNAVAIL,
            "disconnected_by_callee": cls.DISCONNECTED_BY_CALLEE,
            "disconnected_by_caller": cls.DISCONNECTED_BY_CALLER,
            "noanswer": cls.NOANSWER,
            "no answer": cls.NOANSWER,  # Handle case variations
            "NO ANSWER": cls.NOANSWER,  # Explicitly handle uppercase from logs
            "busy": cls.BUSY,
            "BUSY": cls.BUSY,
            "CONGESTION": cls.CONGESTION,
            "FAILED": cls.FAILED,
            "Facility rejected": cls.FACILITY_REJECTED,
            "NormalClearing": cls.NORMAL_CLEARING,
            "congestion": cls.CONGESTION
        }
        if value in mapping:
            return mapping[value]

        # Normalize the value and try to match it to an enum
        normalized = normalize_auto_format(value) if value else "Unknown Status"
        for cause in cls:
            if normalized.lower() == cause.value.lower():
                return cause
        return cls.UNKNOWN  # Fallback to UNKNOWN if no match


class ReasonKey(str, Enum):
    UNKNOWN = CallStatus.UNKNOWN.value
    DISCONNECTED_BY_CALLEE = "Call Disconnected By Callee"
    DISCONNECTED_BY_CALLER = "Call Disconnected By Caller"
    DROPPED = "Calls Dropped"
    CANCELED = CallStatus.CANCELED.value
    INITIATED = "Initiated"
    NOANSWER = CallStatus.NOANSWER.value
    CONGESTION_IN_NETWORK = "Congestion in network"
    BUSY = CallStatus.BUSY.value
    HANDLE_NONE = ""

    @classmethod
    def from_raw(cls, value: Optional[str]) -> "ReasonKey":
        mapping = {
            None: cls.HANDLE_NONE,
            "": cls.HANDLE_NONE,  # Handle empty string
            "Call Disconnected By Callee": cls.DISCONNECTED_BY_CALLEE,
            "Call Disconnected By Caller": cls.DISCONNECTED_BY_CALLER,
            "Calls dropped": cls.DROPPED,
            "cancel": cls.CANCELED,
            "initiated": cls.INITIATED,
            "noanswer": cls.NOANSWER,
            "no answer": cls.NOANSWER,  # Handle case variations
            "NO ANSWER": cls.NOANSWER,  # Handle potential case variations
            "Congestion in network": cls.CONGESTION_IN_NETWORK,
            "busy": cls.BUSY
        }
        if value in mapping:
            return mapping[value]

        # Normalize the value and try to match it to an enum
        normalized = normalize_auto_format(value) if value else "Unknown Status"
        for key in cls:
            if normalized.lower() == key.value.lower():
                return key
        return cls.UNKNOWN  # Fallback to UNKNOWN if no match


class RingType(str, Enum):
    ORDER_BY = "order_by"
    SIMULTANEOUS = "simultaneous"


class UserRoleHierarchy(int, Enum):
    ADMIN = 1
    MAINTAINER = 3
    MANAGER = 4
    TEAM_LEADER = 6
    AGENT = 8


class ConnectionStatus(Enum):
    NOT_CONNECTED = "not connected"
    CONNECTED = "connected"
