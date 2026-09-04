import bisect
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import pytz
from dateutil.relativedelta import relativedelta

from src.components.analytics import constants as analytics_constants
from src.components.analytics.builder import TalkoQueryBuilder
from src.components.analytics.date_range_helper import TalkoDateRangeHelper
from src.components.analytics.enums import TalkoMetric, TalkoTimeInterval
from src.components.cdr.models import TalkoCDR
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.auto_format import safe_to_int
from src.utils.enums import TalkoUserRoleHierarchy


class TalkoCallTrendsHelper:
    """Helper class to handle logic for dashboard call trends processing and formatting."""

    def __init__(
        self,
        logger: TalkoServiceLogger,
        date_range_helper: TalkoDateRangeHelper,
        query_builder: TalkoQueryBuilder,
    ) -> None:
        self.__logger = logger
        self.__date_range_helper = date_range_helper
        self.__query_builder = query_builder

    async def get_projection_and_sort_for_trends(  # NOSONAR
        self,
    ) -> Tuple[Dict[str, Any], List[Tuple[str, int]]]:
        """Fetch call records (CDRs) with optimized projection and sorting."""
        projection = {
            "_id": 0,
            "lead_id": 1,
            "entity_id": 1,
            "entity_type": 1,
            analytics_constants.DATA_TALK_TIME: 1,
            analytics_constants.TOTAL_CALL_DURATION: 1,
            analytics_constants.STATUS_CALL: 1,
            analytics_constants.MODE_CALLING: 1,
            analytics_constants.DATE_TIME: 1,
        }
        sort_order = [(analytics_constants.DATE_TIME, 1)]
        return projection, sort_order

    async def prepare_query_params(  # NOSONAR
        self,
        partner_id: int,
        start_date: Optional[int],
        end_date: Optional[int],
        agents: List[int],
        service_board_id: Optional[List[int]],
        entity_type: Optional[str],
        user_role: int,
    ) -> Tuple[Dict[str, Any], int, int, str]:
        """Prepare query and compute date range."""
        start_date_ms, end_date_ms, period = self.__date_range_helper.adjust_date_range(
            start_date, end_date
        )
        if start_date is None and end_date is None:
            start_date_ms, end_date_ms = (
                self.__date_range_helper.get_default_time_range_trends()
            )

        query = self.__query_builder.build_trend_query(
            partner_id=partner_id,
            start_date_ms=start_date_ms,
            end_date_ms=end_date_ms,
            agents=agents,
            service_board_id=service_board_id,
            entity_type=entity_type,
            user_role=user_role,
        )

        self.__logger.debug(
            f"Adjusted date range: {start_date_ms} - {end_date_ms}, period: {period}"
        )
        return query, start_date_ms, end_date_ms, period

    async def filter_and_format_data(
        self,
        cdrs: List[Dict[str, Any]],
        metric: str,
        trend_basis: str,
        start_dt: int,
        end_dt: int,
        limit: int,
        offset: int,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, Optional[str]]:
        """Filter data by metric and format trends."""
        metric_cond = self._get_cond_for_metric(metric)
        filtered_docs = self._filter_by_metric(cdrs, metric_cond, metric)
        self.__logger.debug(f"Filtered documents: {len(filtered_docs)}")

        formatted_data, total_periods_count, current_month = (
            await self._format_trends_data(
                raw_data=filtered_docs,
                view_type=trend_basis,
                start_dt=start_dt,
                end_dt=end_dt,
                metric=metric,
                limit=limit,
                offset=offset,
            )
        )
        return filtered_docs, formatted_data, total_periods_count, current_month

    async def _format_trends_data(  # NOSONAR
        self,
        raw_data: List[Dict[str, Any]],
        view_type: str,
        start_dt: int,
        end_dt: int,
        metric: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """Format trends data for call metrics."""
        ist = pytz.timezone("Asia/Kolkata")
        start_ist = datetime.fromtimestamp(start_dt / 1000, tz=pytz.UTC).astimezone(ist)
        end_ist = datetime.fromtimestamp(end_dt / 1000, tz=pytz.UTC).astimezone(ist)

        periods = self._generate_periods(view_type, start_ist, end_ist)
        total_periods_count = len(periods)
        periods, current_month = self._paginate_periods(
            periods, view_type, limit, offset
        )
        period_aggregation = self._aggregate_metric_data(raw_data, periods, metric)

        formatted_result = [
            {
                "period": self._format_period_label(period, view_type),
                "total_count": period_aggregation[period],
            }
            for period in periods
        ]
        return formatted_result, total_periods_count, current_month

    def _get_cond_for_metric(self, metric: str) -> Any:
        """Retrieve condition for a given metric."""
        conditions: Dict[TalkoMetric, Union[bool, Dict[str, Any]]] = {
            TalkoMetric.TOTAL_CALLS: True,
            TalkoMetric.TOTAL_CONNECTED_CALLS: {
                analytics_constants.EQ: [
                    analytics_constants.CALL_STATUS,
                    analytics_constants.ANSWERED,
                ]
            },
            TalkoMetric.TOTAL_MISSED_CALLS: {
                analytics_constants.EQ: [
                    analytics_constants.CALL_STATUS,
                    analytics_constants.MISSED,
                ]
            },
            TalkoMetric.LEAD_CONNECTED_CALLS: {
                analytics_constants.QUERY_AND: [
                    {
                        analytics_constants.EQ: [
                            analytics_constants.CALL_STATUS,
                            analytics_constants.ANSWERED,
                        ]
                    },
                    {
                        analytics_constants.EQ: [
                            analytics_constants.CALLING_MODE,
                            analytics_constants.CLICK_TO_CALL,
                        ]
                    },
                ]
            },
            TalkoMetric.AGENT_CONNECTED_CALLS: {
                analytics_constants.QUERY_AND: [
                    {
                        analytics_constants.EQ: [
                            analytics_constants.CALL_STATUS,
                            analytics_constants.ANSWERED,
                        ]
                    },
                    {
                        analytics_constants.EQ: [
                            analytics_constants.CALLING_MODE,
                            analytics_constants.INBOUND,
                        ]
                    },
                ]
            },
            TalkoMetric.LEAD_MISSED_CALLS: {
                analytics_constants.QUERY_AND: [
                    {
                        analytics_constants.EQ: [
                            analytics_constants.CALL_STATUS,
                            analytics_constants.MISSED,
                        ]
                    },
                    {
                        analytics_constants.EQ: [
                            analytics_constants.CALLING_MODE,
                            analytics_constants.CLICK_TO_CALL,
                        ]
                    },
                ]
            },
            TalkoMetric.AGENT_MISSED_CALLS: {
                analytics_constants.QUERY_AND: [
                    {
                        analytics_constants.EQ: [
                            analytics_constants.CALL_STATUS,
                            analytics_constants.MISSED,
                        ]
                    },
                    {
                        analytics_constants.EQ: [
                            analytics_constants.CALLING_MODE,
                            analytics_constants.INBOUND,
                        ]
                    },
                ]
            },
            TalkoMetric.TOTAL_TALK_TIME: True,
            TalkoMetric.TOTAL_CALL_DURATION: True,
            TalkoMetric.TOTAL_UNIQUE_CALLS: True,
        }

        try:
            return conditions[TalkoMetric(metric)]
        except ValueError:
            raise ValueError(
                f"Invalid metric_filter: {metric}. Must be one of {[m.value for m in TalkoMetric]}"
            )

    def _filter_by_metric(
        self, documents: List[Dict], metric_cond: Any, metric: str
    ) -> List[Dict]:
        """Filter documents based on metric condition."""
        if metric_cond is True:
            return documents

        filtered = []
        for doc in documents:
            if metric in [
                TalkoMetric.TOTAL_CONNECTED_CALLS.value,
                TalkoMetric.TOTAL_MISSED_CALLS.value,
            ]:
                if (
                    doc.get(analytics_constants.STATUS_CALL)
                    == metric_cond[analytics_constants.EQ][1]
                ):
                    filtered.append(doc)
            elif metric in [
                TalkoMetric.LEAD_CONNECTED_CALLS.value,
                TalkoMetric.AGENT_CONNECTED_CALLS.value,
                TalkoMetric.LEAD_MISSED_CALLS.value,
                TalkoMetric.AGENT_MISSED_CALLS.value,
            ]:
                cond1 = (
                    doc.get(analytics_constants.STATUS_CALL)
                    == metric_cond[analytics_constants.QUERY_AND][0][
                        analytics_constants.EQ
                    ][1]
                )
                cond2 = (
                    doc.get(analytics_constants.MODE_CALLING)
                    == metric_cond[analytics_constants.QUERY_AND][1][
                        analytics_constants.EQ
                    ][1]
                )
                if cond1 and cond2:
                    filtered.append(doc)
        return filtered

    def _calculate_total_count(
        self, filtered_docs: List[Dict[str, Any]], metric: str
    ) -> int:
        """Compute total count or duration based on metric type."""
        if metric == TalkoMetric.TOTAL_UNIQUE_CALLS.value:
            unique_entities = {
                doc.get("entity_id") or doc.get("lead_id")
                for doc in filtered_docs
                if doc.get("entity_id") or doc.get("lead_id")
            }
            return len(unique_entities)
        elif metric == TalkoMetric.TOTAL_TALK_TIME.value:
            return sum(
                safe_to_int(doc.get(analytics_constants.DATA_TALK_TIME, 0))
                for doc in filtered_docs
            )
        elif metric == TalkoMetric.TOTAL_CALL_DURATION.value:
            return sum(
                safe_to_int(doc.get(analytics_constants.TOTAL_CALL_DURATION, 0))
                for doc in filtered_docs
            )
        return len(filtered_docs)

    def _generate_periods(
        self, view_type: str, start_ist: datetime, end_ist: datetime
    ) -> List[Union[datetime, Tuple[datetime, datetime]]]:
        """Generate date periods for trend aggregation."""
        periods = []
        if view_type == TalkoTimeInterval.DAYS.value:
            current = start_ist.replace(hour=0, minute=0, second=0, microsecond=0)
            while current <= end_ist:
                periods.append(current)
                current += timedelta(days=1)
        elif view_type == TalkoTimeInterval.WEEKS.value:
            current = start_ist
            while current <= end_ist:
                period_end = min(current + timedelta(days=6), end_ist)
                periods.append((current, period_end))
                current = period_end + timedelta(seconds=1)
        elif view_type == TalkoTimeInterval.MONTHS.value:
            current = start_ist.replace(day=1)
            while current <= end_ist:
                next_month = (current.replace(day=28) + timedelta(days=4)).replace(
                    day=1
                )
                periods.append(
                    (current, min(next_month - timedelta(seconds=1), end_ist))
                )
                current = next_month
        else:
            raise ValueError(f"Invalid trend_basis: {view_type}")
        return periods

    def _paginate_periods(
        self,
        periods: List[Union[datetime, Tuple[datetime, datetime]]],
        view_type: str,
        limit: Optional[int],
        offset: Optional[int],
    ) -> Tuple[List[Union[datetime, Tuple[datetime, datetime]]], Optional[str]]:
        """Paginate results by month for daily view."""
        if view_type != TalkoTimeInterval.DAYS.value:
            return periods, None

        periods_by_month = defaultdict(list)
        for p in periods:
            dt = p if isinstance(p, datetime) else p[0]
            key = dt.strftime("%Y-%m")
            periods_by_month[key].append(p)

        sorted_months = sorted(periods_by_month.keys(), reverse=True)
        page_index = (offset - 1) if offset else 0
        current_month = None

        if page_index < len(sorted_months):
            month_key = sorted_months[page_index]
            current_month = datetime.strptime(month_key, "%Y-%m").strftime("%B")
            selected = periods_by_month[month_key]
            return selected, current_month

        return [], None

    def _aggregate_metric_data(
        self,
        raw_data: List[Dict[str, Any]],
        periods: List[Union[datetime, Tuple[datetime, datetime]]],
        metric: str,
    ) -> Dict[Union[datetime, Tuple[datetime, datetime]], int]:
        """Aggregate raw metric data by time period."""
        ist = pytz.timezone("Asia/Kolkata")
        period_aggregation = {p: 0 for p in periods}
        unique_entities = {p: set() for p in periods}

        def find_period(
            dt: datetime,
        ) -> Optional[Union[datetime, Tuple[datetime, datetime]]]:
            for p in periods:
                if isinstance(p, datetime) and dt.date() == p.date():
                    return p
                elif isinstance(p, tuple) and p[0] <= dt <= p[1]:
                    return p
            return None

        for doc in raw_data:
            dt = datetime.fromtimestamp(
                doc[analytics_constants.DATE_TIME] / 1000, tz=pytz.UTC
            ).astimezone(ist)
            period = find_period(dt)
            if not period:
                continue

            if metric == TalkoMetric.TOTAL_UNIQUE_CALLS.value:
                unique_key = doc.get("entity_id") or doc.get("lead_id")
                if unique_key:
                    unique_entities[period].add(unique_key)
            elif metric == TalkoMetric.TOTAL_TALK_TIME.value:
                period_aggregation[period] += safe_to_int(
                    doc.get(analytics_constants.DATA_TALK_TIME, 0)
                )
            elif metric == TalkoMetric.TOTAL_CALL_DURATION.value:
                period_aggregation[period] += safe_to_int(
                    doc.get(analytics_constants.TOTAL_CALL_DURATION, 0)
                )
            else:
                period_aggregation[period] += 1

        if metric == TalkoMetric.TOTAL_UNIQUE_CALLS.value:
            for p in unique_entities:
                period_aggregation[p] = len(unique_entities[p])

        return period_aggregation

    def _format_period_label(self, period, view_type: str) -> str:
        """Return a formatted label for the time period."""
        if view_type == TalkoTimeInterval.DAYS.value:
            return period.strftime("%d/%m/%Y")
        elif view_type == TalkoTimeInterval.WEEKS.value:
            return f"{period[0].strftime('%d/%m/%Y')}-{period[1].strftime('%d/%m/%Y')}"
        elif view_type == TalkoTimeInterval.MONTHS.value:
            return period[0].strftime("%b %Y")
        return ""
