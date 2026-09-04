from datetime import datetime, timedelta

import pytest
import pytz

from src.components.analytics import constants as analytics_constants
from src.components.analytics.builder import QueryBuilder
from src.components.analytics.date_range_helper import DateRangeHelper
from src.components.analytics.enums import Metric, TimeInterval
from src.components.analytics.helper import CallTrendsHelper


class DummyLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def error(self, msg):
        pass


@pytest.fixture
def helper():
    """Return a CallTrendsHelper instance with dummy dependencies."""
    return CallTrendsHelper(
        logger=DummyLogger(),
        date_range_helper=DateRangeHelper(logger=DummyLogger()),
        query_builder=QueryBuilder(logger=DummyLogger()),
    )


@pytest.mark.asyncio
async def test_filter_and_format_data(helper):
    cdrs = [
        {
            "lead_id": "L1",
            analytics_constants.STATUS_CALL: analytics_constants.ANSWERED,
            analytics_constants.MODE_CALLING: analytics_constants.CLICK_TO_CALL,
            analytics_constants.DATE_TIME: int(datetime.now().timestamp() * 1000),
        }
    ]
    filtered_docs, formatted_data, total_periods, current_month = (
        await helper.filter_and_format_data(
            cdrs,
            Metric.TOTAL_CALLS.value,
            TimeInterval.DAYS.value,
            1700000000000,
            1700086400000,
            10,
            1,
        )
    )
    assert isinstance(filtered_docs, list)
    assert isinstance(formatted_data, list)
    assert isinstance(total_periods, int)
    assert current_month is None or isinstance(current_month, str)


def test_filter_by_metric_connected(helper):
    cdrs = [
        {
            analytics_constants.STATUS_CALL: analytics_constants.ANSWERED,
            analytics_constants.MODE_CALLING: analytics_constants.CLICK_TO_CALL,
        }
    ]
    cond = helper._get_cond_for_metric(Metric.LEAD_CONNECTED_CALLS.value)
    result = helper._filter_by_metric(cdrs, cond, Metric.LEAD_CONNECTED_CALLS.value)
    assert len(result) == 1


def test_calculate_total_count_unique(helper):
    docs = [{"lead_id": "1"}, {"lead_id": "1"}, {"lead_id": "2"}]
    total = helper._calculate_total_count(docs, Metric.TOTAL_UNIQUE_CALLS.value)
    assert total == 2


def test_calculate_total_count_talk_time(helper):
    docs = [
        {analytics_constants.DATA_TALK_TIME: 50},
        {analytics_constants.DATA_TALK_TIME: 100},
    ]
    total = helper._calculate_total_count(docs, Metric.TOTAL_TALK_TIME.value)
    assert total == 150


def test_calculate_total_count_call_duration(helper):
    docs = [
        {analytics_constants.TOTAL_CALL_DURATION: 60},
        {analytics_constants.TOTAL_CALL_DURATION: 40},
    ]
    total = helper._calculate_total_count(docs, Metric.TOTAL_CALL_DURATION.value)
    assert total == 100


def test_generate_periods_day(helper):
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    periods = helper._generate_periods(
        TimeInterval.DAYS.value, now, now + timedelta(days=2)
    )
    assert len(periods) == 3


def test_generate_periods_week(helper):
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    periods = helper._generate_periods(
        TimeInterval.WEEKS.value, now, now + timedelta(days=14)
    )
    assert all(isinstance(p, tuple) for p in periods)


def test_generate_periods_month(helper):
    now = datetime(2024, 1, 1, tzinfo=pytz.UTC)
    periods = helper._generate_periods(
        TimeInterval.MONTHS.value, now, now + timedelta(days=60)
    )
    assert all(isinstance(p, tuple) for p in periods)


def test_paginate_periods(helper):
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    periods = [now + timedelta(days=i) for i in range(60)]
    result, current_month = helper._paginate_periods(
        periods, TimeInterval.DAYS.value, 10, 1
    )
    assert isinstance(result, list)
    assert isinstance(current_month, (str, type(None)))


def test_format_period_label(helper):
    now = datetime.now(pytz.UTC)
    assert "/" in helper._format_period_label(now, TimeInterval.DAYS.value)
    week = (now, now + timedelta(days=6))
    assert "-" in helper._format_period_label(week, TimeInterval.WEEKS.value)
    month = (now, now + timedelta(days=30))
    assert " " in helper._format_period_label(month, TimeInterval.MONTHS.value)


def test_aggregate_metric_data(helper):
    now = datetime.now(pytz.UTC)
    ms = int(now.timestamp() * 1000)
    raw = [{"lead_id": "1", analytics_constants.DATE_TIME: ms}]
    periods = [now]
    result = helper._aggregate_metric_data(raw, periods, Metric.TOTAL_CALLS.value)
    assert isinstance(result, dict)
    assert list(result.values())[0] >= 0
