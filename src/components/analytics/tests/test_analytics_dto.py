from datetime import datetime

import pytest

from src.components.analytics import messages as analytics_messages
from src.components.analytics.dto import (
    TalkoAgentCallAnalyticsRequest,
    TalkoAgentTalkTimeDistributionRequest,
    TalkoAnalyticsRequest,
    TalkoAnalyticsResponse,
    TalkoDashboardFollowupTrendsRequest,
    TalkoPartnerServiceBoardRequest,
    TalkoTotalAgentTalkTimeRequest,
)
from src.components.analytics.enums import TalkoTimeInterval


def test_analytics_request_serialization():
    req = TalkoAnalyticsRequest(
        analytics_type="agent_calls",
        data={"date": datetime(2023, 1, 1, 12, 0, 0)},
    )
    json_data = req.model_dump_json()
    assert "2023-01-01T12:00:00" in json_data
    assert req.analytics_type == "agent_calls"


@pytest.mark.parametrize(
    "model_class",
    [
        TalkoAgentCallAnalyticsRequest,
        TalkoTotalAgentTalkTimeRequest,
        TalkoAgentTalkTimeDistributionRequest,
    ],
)
def test_agent_related_requests_defaults(model_class):
    req = model_class()
    assert req.time_range is None
    assert req.agents is None
    assert req.service_board_id is None

    req = model_class(time_range="1625097600000-1627689600000", agents=[1, 2, 3])
    assert req.time_range == "1625097600000-1627689600000"
    assert 1 in req.agents
    assert req.service_board_id is None


def test_partner_service_board_request_valid():
    req = TalkoPartnerServiceBoardRequest(
        time_range="1625097600000-1627689600000",  # 2021-07-01 to 2021-07-31
        service_board_id=[1, 2],
    )
    assert req.time_range == "1625097600000-1627689600000"
    assert req.service_board_id == [1, 2]


def test_partner_service_board_request_invalid_date_range():
    with pytest.raises(ValueError) as excinfo:
        TalkoPartnerServiceBoardRequest(
            time_range="1627689600000-1625097600000",  # end < start
            service_board_id=[1],
        )
    assert analytics_messages.ENDDATE_STARTDATE_GREATER_ERROR in str(excinfo.value)


def test_analytics_response():
    resp = TalkoAnalyticsResponse(analytics_type="talk_time", data={"total": 100})
    assert resp.analytics_type == "talk_time"
    assert resp.data["total"] == 100


def test_dashboard_call_trends_request_valid():
    req = TalkoDashboardFollowupTrendsRequest(
        time_range="1722470400000-1726444800000",  # 2025-08-01 to 2025-09-15
        service_board_id=[40, 41],
        metric_filter="agent_missed_calls",
        trend_basis=TalkoTimeInterval.WEEKS.value,
    )
    assert req.time_range == "1722470400000-1726444800000"
    assert req.service_board_id == [40, 41]
    assert req.metric_filter == "agent_missed_calls"


def test_dashboard_call_trends_request_invalid_metric():
    with pytest.raises(ValueError) as excinfo:
        TalkoDashboardFollowupTrendsRequest(
            time_range="1722470400000-1726444800000",
            service_board_id=[40],
            metric_filter="invalid_metric",
            trend_basis="Weekly",
        )
    assert "metric_filter must be one of" in str(excinfo.value)


def test_dashboard_call_trends_request_invalid_trend_basis():
    with pytest.raises(ValueError) as excinfo:
        TalkoDashboardFollowupTrendsRequest(
            time_range="1722470400000-1726444800000",
            service_board_id=[40],
            metric_filter="agent_missed_calls",
            trend_basis="Yearly",
        )
    assert "trend_basis must be one of" in str(excinfo.value)


def test_dashboard_call_trends_request_invalid_time_range():
    with pytest.raises(ValueError) as excinfo:
        TalkoDashboardFollowupTrendsRequest(
            time_range="1726444800000-1722470400000",  # end < start
            service_board_id=[40],
            metric_filter="agent_missed_calls",
            trend_basis="Weekly",
        )
    assert analytics_messages.ENDDATE_STARTDATE_GREATER_ERROR in str(excinfo.value)
