from enum import Enum


# Enums for analytics types
class TalkoAnalyticsType(str, Enum):
    AGENT_CALL_ANALYTICS = "agent_call_analytics"
    TOTAL_AGENT_TALK_TIME = "total_agent_talk_time"
    AGENT_TALK_TIME_DISTRIBUTION = "agent_talk_time_distribution"
    PARTNER_SERVICE_BOARD = "partner_service_board"
    DASHBOARD_CALL_TRENDS = "dashboard_call_trends"


class TalkoDateRangePeriod(str, Enum):
    TODAY = "today"
    LAST_WEEK = "last_week"
    THREE_MONTHS = "three_months"
    CUSTOM = "custom"


class TalkoRoleType(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    TEAM_LEAD = "team_lead"
    AGENT = "agent"


class TalkoMetric(str, Enum):
    """Enum for valid metric names."""

    TOTAL_CALLS = "total_calls"
    TOTAL_CONNECTED_CALLS = "total_connected_calls"
    TOTAL_MISSED_CALLS = "total_missed_calls"
    LEAD_CONNECTED_CALLS = "lead_connected_calls"
    AGENT_CONNECTED_CALLS = "agent_connected_calls"
    LEAD_MISSED_CALLS = "lead_missed_calls"
    AGENT_MISSED_CALLS = "agent_missed_calls"
    TOTAL_TALK_TIME = "total_talk_time"
    TOTAL_CALL_DURATION = "total_call_duration"
    TOTAL_UNIQUE_CALLS = "total_unique_calls"


class TalkoTimeInterval(str, Enum):
    DAYS = "DAYS"
    WEEKS = "WEEKS"
    MONTHS = "MONTHS"
    YEARS = "YEARS"
