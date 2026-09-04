from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from src.components.analytics import messages as analytics_messages
from src.components.analytics.enums import TalkoMetric, TalkoTimeInterval
from src.components.cdr.constants import TalkoEntityType


class TalkoAnalyticsRequest(BaseModel):
    analytics_type: str
    data: Dict

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class TalkoAgentCallAnalyticsRequest(BaseModel):
    time_range: Optional[str] = None
    agents: Optional[List[int]] = None
    service_board_id: Optional[List[int]] = None
    entity_type: Optional[str] = TalkoEntityType.LEAD.value

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "time_range": "1749148200000-1756992444404",
                "agents": [1, 2, 3],
                "service_board_id": [1, 2],
                "entity_type": TalkoEntityType.LEAD.value,
            }
        }
    )


class TalkoTotalAgentTalkTimeRequest(BaseModel):
    time_range: Optional[str] = None
    agents: Optional[List[int]] = None
    service_board_id: Optional[List[int]] = None
    entity_type: Optional[str] = TalkoEntityType.LEAD.value

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "time_range": "1749148200000-1756992444404",
                "agents": [1, 2, 3],
                "service_board_id": [1, 2],
                "entity_type": TalkoEntityType.LEAD.value,
            }
        }
    )


class TalkoAgentTalkTimeDistributionRequest(BaseModel):
    time_range: Optional[str] = None
    agents: Optional[List[int]] = None
    service_board_id: Optional[List[int]] = None
    entity_type: Optional[str] = TalkoEntityType.LEAD.value

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "time_range": "1749148200000-1756992444404",
                "agents": [1, 2, 3],
                "service_board_id": [1, 2],
                "entity_type": TalkoEntityType.LEAD.value,
            }
        }
    )


class TalkoPartnerServiceBoardRequest(BaseModel):
    time_range: Optional[str] = None
    service_board_id: Optional[List[int]] = None
    entity_type: Optional[str] = TalkoEntityType.LEAD.value

    @field_validator("time_range")
    def validate_time_range(cls, time_range):
        # Example: ensure time_range format is "start-end"
        if time_range and "-" in time_range:
            start, end = time_range.split("-", 1)
            if int(end) < int(start):
                raise ValueError(analytics_messages.ENDDATE_STARTDATE_GREATER_ERROR)
        return time_range

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "time_range": "1749148200000-1756992444404",
                "service_board_id": [1, 2],
                "entity_type": TalkoEntityType.LEAD.value,
            }
        }
    )


class TalkoDashboardFollowupTrendsRequest(BaseModel):
    time_range: Optional[str] = None
    service_board_id: Optional[List[int]] = None
    entity_type: Optional[str] = TalkoEntityType.LEAD.value
    metric_filter: str
    trend_basis: str

    @field_validator("time_range")
    def validate_time_range(cls, time_range):
        if time_range and "-" in time_range:
            start, end = time_range.split("-", 1)
            if int(end) < int(start):
                raise ValueError(analytics_messages.ENDDATE_STARTDATE_GREATER_ERROR)
        return time_range

    @field_validator("metric_filter")
    def validate_metric_filter(cls, v):
        valid_metrics = [
            TalkoMetric.TOTAL_CALLS.value,
            TalkoMetric.TOTAL_CONNECTED_CALLS.value,
            TalkoMetric.TOTAL_UNIQUE_CALLS.value,
            TalkoMetric.TOTAL_MISSED_CALLS.value,
            TalkoMetric.LEAD_CONNECTED_CALLS.value,
            TalkoMetric.AGENT_CONNECTED_CALLS.value,
            TalkoMetric.LEAD_MISSED_CALLS.value,
            TalkoMetric.AGENT_MISSED_CALLS.value,
            TalkoMetric.TOTAL_TALK_TIME.value,
            TalkoMetric.TOTAL_CALL_DURATION.value,
        ]
        if v not in valid_metrics:
            raise ValueError(f"metric_filter must be one of {valid_metrics}")
        return v

    @field_validator("trend_basis")
    def validate_trend_basis(cls, v):
        valid_bases = [
            TalkoTimeInterval.DAYS.value,
            TalkoTimeInterval.WEEKS.value,
            TalkoTimeInterval.MONTHS.value,
        ]
        if v not in valid_bases:
            raise ValueError(f"trend_basis must be one of {valid_bases}")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "time_range": "1749148200000-1756992444404",
                "service_board_id": [1, 2],
                "entity_type": TalkoEntityType.LEAD.value,
                "metric_filter": "agent_missed_calls",
                "trend_basis": TalkoTimeInterval.WEEKS.value,
            }
        }
    )


class TalkoAnalyticsResponse(BaseModel):
    analytics_type: str
    data: Dict
