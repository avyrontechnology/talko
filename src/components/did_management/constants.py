from enum import Enum, unique


@unique
class DIDStatus(str, Enum):
    """
    Enum representing all valid statuses for a DID in phone_number collection.
    Using str + Enum so values can be used directly in MongoDB and Pydantic.
    """

    AVAILABLE = "Available"
    MAPPED = "Mapped"
    COOLING_PERIOD = "Cooling Period"
    COOLDOWN_COMPLETED = "Cooldown Completed"


class DIDType(str, Enum):
    """DID types for human vs AI agent routing."""

    NORMAL = "normal"
    AI_AGENT = "ai_agent"


# Useful constant sets (type-safe)
COOLDOWN_BLOCKED_STATUSES = frozenset(
    [DIDStatus.COOLING_PERIOD, DIDStatus.COOLDOWN_COMPLETED]
)

USABLE_STATUSES = frozenset([DIDStatus.AVAILABLE, DIDStatus.MAPPED])

# Cooldown configuration (fixed 30 days as per requirement)
COOLDOWN_DAYS = 30
COOLDOWN_MS = COOLDOWN_DAYS * 24 * 3600 * 1000

# Action handlers for admin actions on DIDs
ADMIN_ACTION_SET_AVAILABLE = "set_available"
ADMIN_ACTION_SET_MAPPED = "set_mapped"
ADMIN_ACTION_MARK_SPAMMED = "mark_cooling_period"
