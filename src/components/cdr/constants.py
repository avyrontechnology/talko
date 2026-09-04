from datetime import timedelta, timezone
from enum import Enum

from src.components.analytics.constants import CLICK_TO_CALL
from src.utils.enums import TalkoConnectionStatus

IST = timezone(timedelta(hours=5, minutes=30))


VALID_DB_STATUSES = {"answered", "missed"}  # stored in DB
VALID_LEAD_STATUSES = {"lead_connected", "lead_not_connected"}
VALID_AGENT_STATUSES = {"agent_connected", "agent_not_connected"}

VALID_CALL_STATUSES = VALID_DB_STATUSES | VALID_LEAD_STATUSES | VALID_AGENT_STATUSES


class TalkoEntityType(str, Enum):
    LEAD = "Lead"
    CONTACT = "Contact"


class TalkoTalkTimeRange(str, Enum):
    ZERO_TO_ONE = "0_1"
    ONE_TO_THREE = "1_3"
    THREE_TO_FIVE = "3_5"
    GREATER_FIVE = "5_plus"


TALK_TIME_RANGES = {
    TalkoTalkTimeRange.ZERO_TO_ONE: (0, 60),  # 0–1 min
    TalkoTalkTimeRange.ONE_TO_THREE: (61, 180),  # 1–3 min
    TalkoTalkTimeRange.THREE_TO_FIVE: (181, 300),  # 3–5 min
    TalkoTalkTimeRange.GREATER_FIVE: (301, None),  # > 5 min
}

AGENT_STATUS_EXPR = {
    "$cond": {
        "if": {"$eq": [{"$ifNull": ["$calling_mode", CLICK_TO_CALL]}, CLICK_TO_CALL]},
        "then": {
            "$cond": {
                "if": {"$gt": [{"$ifNull": ["$total_call_duration", 0]}, 0]},
                "then": TalkoConnectionStatus.CONNECTED.value,
                "else": TalkoConnectionStatus.NOT_CONNECTED.value,
            }
        },
        "else": {
            "$cond": {
                "if": {
                    "$or": [
                        {"$eq": ["$call_connected", 1]},
                        {"$gt": [{"$ifNull": ["$talk_time", 0]}, 0]},
                    ]
                },
                "then": TalkoConnectionStatus.CONNECTED.value,
                "else": TalkoConnectionStatus.NOT_CONNECTED.value,
            }
        },
    }
}

LEAD_STATUS_EXPR = {
    "$cond": {
        "if": {"$eq": [{"$ifNull": ["$calling_mode", CLICK_TO_CALL]}, CLICK_TO_CALL]},
        "then": {
            "$cond": {
                "if": {"$gt": [{"$ifNull": ["$talk_time", 0]}, 0]},
                "then": TalkoConnectionStatus.CONNECTED.value,
                "else": TalkoConnectionStatus.NOT_CONNECTED.value,
            }
        },
        "else": {
            "$cond": {
                "if": {"$gt": [{"$ifNull": ["$total_call_duration", 0]}, 0]},
                "then": TalkoConnectionStatus.CONNECTED.value,
                "else": TalkoConnectionStatus.NOT_CONNECTED.value,
            }
        },
    }
}
