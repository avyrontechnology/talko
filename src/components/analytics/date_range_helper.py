from datetime import datetime, time, timezone
from typing import Optional, Tuple

from dateutil.relativedelta import relativedelta

from src.components.analytics.enums import TalkoDateRangePeriod
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoDateRangeHelper:
    """
    Helper class to calculate and adjust date ranges for analytics requests.

    Attributes:
        logger (TalkoServiceLogger): Logger instance for debug and error messages.
    """

    def __init__(self, logger: TalkoServiceLogger):
        """
        Initialize TalkoDateRangeHelper with a logger.

        Args:
            logger (TalkoServiceLogger): Logger instance for debug and error messages.
        """
        self.logger = logger

    def get_default_time_range_trends(self) -> Tuple[int, int, str]:
        now = datetime.now(timezone.utc)
        start_date = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ) - relativedelta(months=2)
        end_date = now

        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)
        return start_ms, end_ms

    def get_default_date_range(self) -> Tuple[int, int, str]:
        """
        Return the default date range of the last 3 months.

        Returns:
            Tuple[int, int, str]:
                - start_date_ms: Start date as Unix timestamp in milliseconds.
                - end_date_ms: End date as Unix timestamp in milliseconds.
                - period: Period type (THREE_MONTHS).
        """
        current_date = datetime.now()
        start_date_dt = current_date - relativedelta(months=3)
        start_date_ms = int(start_date_dt.timestamp() * 1000)
        end_date_ms = int(current_date.timestamp() * 1000)
        self.logger.debug(
            "Using default 3-month range: {} to {}, in int {} t0 {}".format(
                start_date_dt, current_date, start_date_ms, end_date_ms
            )
        )
        return start_date_ms, end_date_ms, TalkoDateRangePeriod.THREE_MONTHS.value

    def adjust_date_range(
        self, start_date: Optional[int], end_date: Optional[int]
    ) -> Tuple[int, int, str]:
        """
        Adjust the provided date range to predefined periods (Today, Last Week, Three Months)
        or custom. Returns Unix timestamps in milliseconds and period type.

        Args:
            start_date (Optional[int]): Start date in Unix timestamp (seconds).
            end_date (Optional[int]): End date in Unix timestamp (seconds).

        Returns:
            Tuple[int, int, str]:
                - start_date_ms: Adjusted start date in milliseconds.
                - end_date_ms: Adjusted end date in milliseconds.
                - period: Period type (TODAY, LAST_WEEK, THREE_MONTHS, or CUSTOM).

        Raises:
            ValueError: If only one of start_date or end_date is provided.
            ValueError: If end_date is earlier than start_date.
        """
        if start_date is None and end_date is None:
            return self.get_default_date_range()

        if start_date is None or end_date is None:
            self.logger.error("Both start_date and end_date must be provided together")
            raise ValueError("Both start_date and end_date must be provided together")

        start_date_ms = start_date * 1000
        end_date_ms = end_date * 1000

        if end_date_ms < start_date_ms:
            self.logger.error(
                "Invalid date range: end_date ({}) is before start_date ({})".format(
                    end_date, start_date
                )
            )
            raise ValueError("end_date must be greater than or equal to start_date")

        duration_seconds = (end_date_ms - start_date_ms) // 1000
        current_date = datetime.now()
        today_start = datetime.combine(current_date.date(), time(0, 0))
        today_end = datetime.combine(current_date.date(), time(23, 59, 59, 999999))

        if 86400 <= duration_seconds <= 86400 * 1.1:
            start_date_ms = int(today_start.timestamp() * 1000)
            end_date_ms = int(today_end.timestamp() * 1000)
            period = TalkoDateRangePeriod.TODAY.value
            self.logger.debug(
                "Detected 'Today' range: {} to {}".format(today_start, today_end)
            )
        elif 604800 <= duration_seconds <= 604800 * 1.1:
            last_week_start = current_date - relativedelta(days=7)
            last_week_start = datetime.combine(last_week_start.date(), time(0, 0))
            last_week_end = last_week_start + relativedelta(
                days=6, hours=23, minutes=59, seconds=59, microseconds=999999
            )
            start_date_ms = int(last_week_start.timestamp() * 1000)
            end_date_ms = int(last_week_end.timestamp() * 1000)
            period = TalkoDateRangePeriod.LAST_WEEK.value
            self.logger.debug(
                "Detected 'Last Week' range: {} to {}".format(
                    last_week_start, last_week_end
                )
            )
        elif 7776000 <= duration_seconds <= 7776000 * 1.1:
            start_date_ms, end_date_ms, _ = self.get_default_date_range()
            period = TalkoDateRangePeriod.THREE_MONTHS.value
            self.logger.debug(
                "Detected '3 Months' range: {} to {}".format(start_date_ms, end_date_ms)
            )
        else:
            period = TalkoDateRangePeriod.CUSTOM.value
            self.logger.debug(
                "Using custom date range: {} to {}".format(start_date_ms, end_date_ms)
            )

        return start_date_ms, end_date_ms, period
