from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.components.analytics.date_range_helper import TalkoDateRangeHelper
from src.components.analytics.enums import TalkoDateRangePeriod


class TestDateRangeHelper:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.logger = MagicMock()
        self.helper = TalkoDateRangeHelper(self.logger)

    def test_get_default_date_range(self):
        start_ms, end_ms, period = self.helper.get_default_date_range()
        assert period == TalkoDateRangePeriod.THREE_MONTHS.value
        assert start_ms < end_ms
        self.logger.debug.assert_called_once()

    def test_adjust_date_range_none(self):
        start_ms, end_ms, period = self.helper.adjust_date_range(None, None)
        assert period == TalkoDateRangePeriod.THREE_MONTHS.value
        self.logger.debug.assert_called()

    def test_adjust_date_range_only_one(self):
        with pytest.raises(ValueError):
            self.helper.adjust_date_range(1000, None)
        with pytest.raises(ValueError):
            self.helper.adjust_date_range(None, 1000)

    def test_adjust_date_range_end_before_start(self):
        start = int(datetime.now().timestamp())
        end = start - 100
        with pytest.raises(ValueError):
            self.helper.adjust_date_range(start, end)

    def test_adjust_date_range_today(self):
        now = int(datetime.now().timestamp())
        start_ms, end_ms, period = self.helper.adjust_date_range(now - 86400, now)
        assert period == TalkoDateRangePeriod.TODAY.value
        assert start_ms < end_ms

    def test_adjust_date_range_last_week(self):
        now = int(datetime.now().timestamp())
        start = now - 604800
        start_ms, end_ms, period = self.helper.adjust_date_range(start, now)
        assert period == TalkoDateRangePeriod.LAST_WEEK.value
        assert start_ms < end_ms

    def test_adjust_date_range_three_months(self):
        now = int(datetime.now().timestamp())
        start = now - 90 * 24 * 3600
        start_ms, end_ms, period = self.helper.adjust_date_range(start, now)
        assert period == TalkoDateRangePeriod.THREE_MONTHS.value

    def test_adjust_date_range_custom(self):
        now = int(datetime.now().timestamp())
        start = now - 2 * 24 * 3600  # 2 days
        start_ms, end_ms, period = self.helper.adjust_date_range(start, now)
        assert period == TalkoDateRangePeriod.CUSTOM.value
