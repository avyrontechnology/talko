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
from src.components.analytics.helper import TalkoCallTrendsHelper
from src.components.cdr.models import TalkoCDR
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.auto_format import safe_to_int
from src.utils.enums import TalkoUserRoleHierarchy


class TalkoAnalyticsRepository:
    def __init__(
        self,
        db_manager: TalkoDocDatabaseSessionManager,
        logger: TalkoServiceLogger,
        analytics_query_builder: TalkoQueryBuilder,
    ):
        self.__db_manager: TalkoDocDatabaseSessionManager = db_manager
        self.__logger: TalkoServiceLogger = logger
        self.__date_range_helper = TalkoDateRangeHelper(logger)
        self.__query_builder: TalkoQueryBuilder = analytics_query_builder
        self.__bucket_ranges = [
            {"range": "0-1 minutes", "min": 0, "max": 60},
            {"range": "1-5 minutes", "min": 60, "max": 300},
            {"range": "5-10 minutes", "min": 300, "max": 600},
            {"range": ">=10 minutes", "min": 600, "max": float("inf")},
        ]
        self.__call_trends_helper = TalkoCallTrendsHelper(
            self.__logger, self.__date_range_helper, self.__query_builder
        )

    def _format_agent_response(
        self, result: List[Dict], fields: List[str]
    ) -> List[Dict]:
        """Format agent-based aggregation results into response structure."""
        return [{field: doc[field] for field in fields} for doc in result]

    def _validate_pagination(self, offset: int, limit: int) -> None:
        """Validate pagination parameters."""
        if offset < 0:
            raise ValueError("Offset must be non-negative")
        if limit <= 0:
            raise ValueError("Limit must be positive")

    async def get_agent_call_analytics(
        self,
        partner_id: int,
        start_date: Optional[int],
        end_date: Optional[int],
        agents: Optional[List[int]],
        service_board_id: Optional[List[int]] = None,
        entity_type: Optional[str] = None,
        limit: int = 10,
        offset: int = 1,
        user_role: int = TalkoUserRoleHierarchy.MAINTAINER.value,
    ) -> Dict:
        try:
            if not agents and user_role != TalkoUserRoleHierarchy.MAINTAINER.value:
                self.__logger.info(
                    f"No agents provided for partner_id: {partner_id}, returning empty result"
                )
                return {analytics_constants.AGENTS: [], "total_count": 0}
            self._validate_pagination(offset, limit)
            async with self.__db_manager.collection(
                TalkoCDR.CollectionName.TalkoCDR
            ) as collection:
                start_date_ms, end_date_ms, period = (
                    self.__date_range_helper.adjust_date_range(start_date, end_date)
                )
                self.__logger.debug(
                    f"Retrieving agent call analytics for partner_id: {partner_id}, "
                    f"start_date: {start_date_ms}, end_date: {end_date_ms}, period: {period}, "
                    f"limit: {limit}, offset: {offset}"
                )
                query = self.__query_builder.build_query(
                    partner_id,
                    start_date_ms,
                    end_date_ms,
                    agents=agents,
                    service_board_id=service_board_id,
                    entity_type=entity_type,
                    user_role=user_role,
                )

                count_pipeline = [
                    {analytics_constants.MATCH: query},
                    {
                        analytics_constants.GROUP: {
                            analytics_constants.UNDERSCORE_ID: analytics_constants.AGENT
                        }
                    },
                    {analytics_constants.COUNT: "total_count"},
                ]
                count_result = await collection.aggregate(count_pipeline).to_list()
                total_count = count_result[0]["total_count"] if count_result else 0
                self.__logger.debug(f"Total agent count: {total_count}")

                skip_count = (offset - 1) * limit
                pipeline = [
                    {analytics_constants.MATCH: query},
                    {
                        analytics_constants.GROUP: {
                            analytics_constants.UNDERSCORE_ID: analytics_constants.AGENT,
                            analytics_constants.TOTAL_CALLS: {
                                analytics_constants.SUM: 1
                            },
                            analytics_constants.UNIQUE_CALLS: {
                                analytics_constants.ADDTOSET: analytics_constants.LEAD_ID
                            },
                            analytics_constants.CONNECTED_CALLS: {
                                analytics_constants.SUM: {
                                    analytics_constants.CONDITION: [
                                        {
                                            analytics_constants.EQ: [
                                                analytics_constants.CALL_STATUS,
                                                analytics_constants.ANSWERED,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            analytics_constants.MISSED_CALLS: {
                                analytics_constants.SUM: {
                                    analytics_constants.CONDITION: [
                                        {
                                            analytics_constants.EQ: [
                                                analytics_constants.CALL_STATUS,
                                                analytics_constants.MISSED,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            analytics_constants.AGENT_MISSED_CALLS: {
                                analytics_constants.SUM: {
                                    analytics_constants.CONDITION: [
                                        {
                                            analytics_constants.QUERY_OR: [
                                                {
                                                    analytics_constants.QUERY_AND: [
                                                        {
                                                            analytics_constants.EQ: [
                                                                analytics_constants.CALLING_MODE,
                                                                analytics_constants.CLICK_TO_CALL,
                                                            ]
                                                        },
                                                        {
                                                            analytics_constants.EQ: [
                                                                analytics_constants.QUERY_TOTAL_CALL_DURATION,
                                                                0,
                                                            ]
                                                        },
                                                    ]
                                                },
                                                {
                                                    analytics_constants.QUERY_AND: [
                                                        {
                                                            analytics_constants.NE_CONDITION: [
                                                                analytics_constants.CALLING_MODE,
                                                                analytics_constants.INBOUND,
                                                            ]
                                                        },
                                                        {
                                                            analytics_constants.NE_CONDITION: [
                                                                analytics_constants.QUERY_CALL_CONNECTED,
                                                                "1",
                                                            ]
                                                        },
                                                        {
                                                            analytics_constants.EQ: [
                                                                analytics_constants.TALK_TIME,
                                                                0,
                                                            ]
                                                        },
                                                    ]
                                                },
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            analytics_constants.LEAD_MISSED_CALLS: {
                                analytics_constants.SUM: {
                                    analytics_constants.CONDITION: [
                                        {
                                            analytics_constants.QUERY_OR: [
                                                {
                                                    analytics_constants.QUERY_AND: [
                                                        {
                                                            analytics_constants.EQ: [
                                                                analytics_constants.CALLING_MODE,
                                                                analytics_constants.CLICK_TO_CALL,
                                                            ]
                                                        },
                                                        {
                                                            analytics_constants.EQ: [
                                                                analytics_constants.TALK_TIME,
                                                                0,
                                                            ]
                                                        },
                                                    ]
                                                },
                                                {
                                                    analytics_constants.QUERY_AND: [
                                                        {
                                                            analytics_constants.NE_CONDITION: [
                                                                analytics_constants.CALLING_MODE,
                                                                analytics_constants.INBOUND,
                                                            ]
                                                        },
                                                        {
                                                            analytics_constants.EQ: [
                                                                analytics_constants.QUERY_TOTAL_CALL_DURATION,
                                                                0,
                                                            ]
                                                        },
                                                    ]
                                                },
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "connected_unique_calls": {
                                analytics_constants.ADDTOSET: {
                                    analytics_constants.CONDITION: [
                                        {
                                            analytics_constants.EQ: [
                                                analytics_constants.CALL_STATUS,
                                                analytics_constants.ANSWERED,
                                            ]
                                        },
                                        analytics_constants.LEAD_ID,
                                        None,
                                    ]
                                }
                            },
                        }
                    },
                    {
                        analytics_constants.LOOKUP: {
                            "from": analytics_constants.AGENTS,
                            "localField": analytics_constants.UNDERSCORE_ID,
                            "foreignField": analytics_constants.AGENT_ID,
                            "as": analytics_constants.AGENT_INFO,
                        }
                    },
                    {
                        analytics_constants.UNWIND: {
                            "path": analytics_constants.QUERY_AGENT_INFO,
                            "preserveNullAndEmptyArrays": True,
                        }
                    },
                    {
                        analytics_constants.PROJECT: {
                            analytics_constants.AGENT_ID: analytics_constants.ID,
                            analytics_constants.AGENT_NAME: {
                                analytics_constants.QUERY_IF_NULL: [
                                    analytics_constants.QUERY_AGENT_INFO_NAME,
                                    "Unknown",
                                ]
                            },
                            analytics_constants.TOTAL_CALLS: 1,
                            analytics_constants.UNIQUE_CALLS: {
                                analytics_constants.SIZE: {
                                    analytics_constants.FILTER: {
                                        "input": analytics_constants.QUERY_UNIQUE_CALLS,
                                        "cond": {
                                            analytics_constants.NE_CONDITION: [
                                                analytics_constants.THIS_CONDITION,
                                                None,
                                            ]
                                        },
                                    }
                                }
                            },
                            analytics_constants.CONNECTED_CALLS: 1,
                            analytics_constants.MISSED_CALLS: 1,
                            analytics_constants.AGENT_MISSED_CALLS: 1,
                            analytics_constants.LEAD_MISSED_CALLS: 1,
                            analytics_constants.TOTAL_PLACED_CALLS: analytics_constants.QUERY_CONNECTED_CALLS,
                            analytics_constants.TOTAL_CONNECTED_UNIQUE_CALLS: {
                                analytics_constants.SIZE: {
                                    analytics_constants.FILTER: {
                                        "input": analytics_constants.QUERY_CONNECTED_UNIQUE_CALLS,
                                        "cond": {
                                            analytics_constants.NE_CONDITION: [
                                                analytics_constants.THIS_CONDITION,
                                                None,
                                            ]
                                        },
                                    }
                                }
                            },
                        }
                    },
                    {analytics_constants.SORT: {analytics_constants.AGENT_ID: 1}},
                    {analytics_constants.SKIP: skip_count},
                    {analytics_constants.LIMIT: limit},
                ]

                self.__logger.debug(f"Agent call analytics pipeline: {pipeline}")
                result = await collection.aggregate(pipeline).to_list()
                self.__logger.debug(f"Aggregation result: {result}")
                self.__logger.info(
                    f"Successfully retrieved agent call analytics for partner_id: {partner_id}"
                )
                return {
                    analytics_constants.AGENTS: self._format_agent_response(
                        result,
                        [
                            analytics_constants.AGENT_ID,
                            analytics_constants.AGENT_NAME,
                            analytics_constants.TOTAL_CALLS,
                            analytics_constants.UNIQUE_CALLS,
                            analytics_constants.CONNECTED_CALLS,
                            analytics_constants.MISSED_CALLS,
                            analytics_constants.AGENT_MISSED_CALLS,
                            analytics_constants.LEAD_MISSED_CALLS,
                            analytics_constants.TOTAL_PLACED_CALLS,
                            analytics_constants.TOTAL_CONNECTED_UNIQUE_CALLS,
                        ],
                    ),
                    "total_count": total_count,
                }
        except Exception as e:
            self.__logger.error(f"Failed to retrieve agent call analytics: {str(e)}")
            raise

    async def get_total_agent_talk_time(
        self,
        partner_id: int,
        start_date: Optional[int],
        end_date: Optional[int],
        agents: Optional[List[int]],
        service_board_id: Optional[List[int]] = None,
        entity_type: Optional[str] = None,
        limit: int = 10,
        offset: int = 1,
        user_role: int = TalkoUserRoleHierarchy.MAINTAINER.value,
    ) -> Dict:
        try:
            if not agents and user_role != TalkoUserRoleHierarchy.MAINTAINER.value:
                self.__logger.info(
                    f"No agents provided for partner_id: {partner_id}, returning empty result"
                )
                return {analytics_constants.AGENTS: [], "total_count": 0}
            self._validate_pagination(offset, limit)
            async with self.__db_manager.collection(
                TalkoCDR.CollectionName.TalkoCDR
            ) as collection:
                start_date_ms, end_date_ms, period = (
                    self.__date_range_helper.adjust_date_range(start_date, end_date)
                )
                self.__logger.debug(
                    f"Retrieving total agent talk time for partner_id: {partner_id}, "
                    f"start_date: {start_date_ms}, end_date: {end_date_ms}, period: {period}, "
                    f"limit: {limit}, offset: {offset}"
                )
                query = self.__query_builder.build_query(
                    partner_id,
                    start_date_ms,
                    end_date_ms,
                    agents=agents,
                    service_board_id=service_board_id,
                    entity_type=entity_type,
                    user_role=user_role,
                )

                count_pipeline = [
                    {analytics_constants.MATCH: query},
                    {
                        analytics_constants.GROUP: {
                            analytics_constants.UNDERSCORE_ID: analytics_constants.AGENT
                        }
                    },
                    {analytics_constants.COUNT: "total_count"},
                ]
                count_result = await collection.aggregate(count_pipeline).to_list()
                total_count = count_result[0]["total_count"] if count_result else 0
                self.__logger.debug(f"Total agent count: {total_count}")

                skip_count = (offset - 1) * limit
                pipeline = [
                    {analytics_constants.MATCH: query},
                    {
                        analytics_constants.GROUP: {
                            analytics_constants.UNDERSCORE_ID: analytics_constants.AGENT,
                            analytics_constants.TOTAL_TALK_TIME: {
                                analytics_constants.SUM: analytics_constants.TALK_TIME
                            },
                            analytics_constants.TOTAL_CALL_DURATION: {
                                analytics_constants.SUM: analytics_constants.QUERY_TOTAL_CALL_DURATION
                            },
                        }
                    },
                    {
                        analytics_constants.LOOKUP: {
                            "from": analytics_constants.AGENTS,
                            "localField": analytics_constants.UNDERSCORE_ID,
                            "foreignField": analytics_constants.AGENT_ID,
                            "as": analytics_constants.AGENT_INFO,
                        }
                    },
                    {
                        analytics_constants.UNWIND: {
                            "path": analytics_constants.QUERY_AGENT_INFO,
                            "preserveNullAndEmptyArrays": True,
                        }
                    },
                    {
                        analytics_constants.PROJECT: {
                            analytics_constants.AGENT_ID: analytics_constants.ID,
                            analytics_constants.AGENT_NAME: {
                                analytics_constants.QUERY_IF_NULL: [
                                    analytics_constants.QUERY_AGENT_INFO_NAME,
                                    "Unknown",
                                ]
                            },
                            analytics_constants.TOTAL_TALK_TIME: 1,
                            analytics_constants.TOTAL_CALL_DURATION: 1,
                        }
                    },
                    {analytics_constants.SORT: {analytics_constants.AGENT_ID: 1}},
                    {analytics_constants.SKIP: skip_count},
                    {analytics_constants.LIMIT: limit},
                ]

                self.__logger.debug(f"Total agent talk time pipeline: {pipeline}")
                result = await collection.aggregate(pipeline).to_list()
                self.__logger.debug(f"Aggregation result: {result}")
                self.__logger.info(
                    f"Successfully retrieved total agent talk time for partner_id: {partner_id}"
                )
                return {
                    analytics_constants.AGENTS: self._format_agent_response(
                        result,
                        [
                            analytics_constants.AGENT_ID,
                            analytics_constants.AGENT_NAME,
                            analytics_constants.TOTAL_TALK_TIME,
                            analytics_constants.TOTAL_CALL_DURATION,
                        ],
                    ),
                    "total_count": total_count,
                }
        except Exception as e:
            self.__logger.error(f"Failed to retrieve total agent talk time: {str(e)}")
            raise

    async def get_agent_talk_time_distribution(
        self,
        partner_id: int,
        start_date: Optional[int],
        end_date: Optional[int],
        agents: Optional[List[int]],
        service_board_id: Optional[List[int]] = None,
        entity_type: Optional[str] = None,
        limit: int = 10,
        offset: int = 1,
        user_role: int = TalkoUserRoleHierarchy.MAINTAINER.value,
    ) -> Dict:
        try:
            if not agents and user_role != TalkoUserRoleHierarchy.MAINTAINER.value:
                self.__logger.info(
                    f"No agents provided for partner_id: {partner_id}, returning empty result"
                )
                return {analytics_constants.AGENTS: [], "total_count": 0}
            self._validate_pagination(offset, limit)
            async with self.__db_manager.collection(
                TalkoCDR.CollectionName.TalkoCDR
            ) as collection:
                start_date_ms, end_date_ms, period = (
                    self.__date_range_helper.adjust_date_range(start_date, end_date)
                )
                self.__logger.debug(
                    f"Retrieving agent talk time distribution for partner_id: {partner_id}, "
                    f"start_date: {start_date_ms}, end_date: {end_date_ms}, period: {period}, "
                    f"limit: {limit}, offset: {offset}"
                )
                query = self.__query_builder.build_query(
                    partner_id,
                    start_date_ms,
                    end_date_ms,
                    agents=agents,
                    service_board_id=service_board_id,
                    entity_type=entity_type,
                    user_role=user_role,
                )

                count_pipeline = [
                    {analytics_constants.MATCH: query},
                    {
                        analytics_constants.GROUP: {
                            analytics_constants.UNDERSCORE_ID: analytics_constants.AGENT
                        }
                    },
                    {analytics_constants.COUNT: "total_count"},
                ]
                count_result = await collection.aggregate(count_pipeline).to_list()
                total_count = count_result[0]["total_count"] if count_result else 0
                self.__logger.debug(f"Total agent count: {total_count}")

                skip_count = (offset - 1) * limit
                pipeline = [
                    {analytics_constants.MATCH: query},
                    {
                        analytics_constants.GROUP: {
                            analytics_constants.UNDERSCORE_ID: analytics_constants.AGENT,
                            "calls": {
                                "$push": {"duration": analytics_constants.TALK_TIME}
                            },
                        }
                    },
                    {
                        analytics_constants.LOOKUP: {
                            "from": analytics_constants.AGENTS,
                            "localField": analytics_constants.UNDERSCORE_ID,
                            "foreignField": analytics_constants.AGENT_ID,
                            "as": analytics_constants.AGENT_INFO,
                        }
                    },
                    {
                        analytics_constants.UNWIND: {
                            "path": analytics_constants.QUERY_AGENT_INFO,
                            "preserveNullAndEmptyArrays": True,
                        }
                    },
                    {
                        analytics_constants.PROJECT: {
                            analytics_constants.AGENT_ID: analytics_constants.ID,
                            analytics_constants.AGENT_NAME: {
                                analytics_constants.QUERY_IF_NULL: [
                                    analytics_constants.QUERY_AGENT_INFO_NAME,
                                    "Unknown",
                                ]
                            },
                            "buckets": {
                                "$arrayToObject": {
                                    "$map": {
                                        "input": self.__bucket_ranges,
                                        "as": "bucket",
                                        "in": {
                                            "k": "$$bucket.range",
                                            "v": {
                                                analytics_constants.SIZE: {
                                                    analytics_constants.FILTER: {
                                                        "input": "$calls",
                                                        "as": "call",
                                                        "cond": {
                                                            analytics_constants.QUERY_AND: [
                                                                {
                                                                    "$gt": [
                                                                        "$$call.duration",
                                                                        "$$bucket.min",
                                                                    ]
                                                                },
                                                                {
                                                                    analytics_constants.LTE_CONDITION: [
                                                                        "$$call.duration",
                                                                        "$$bucket.max",
                                                                    ]
                                                                },
                                                            ]
                                                        },
                                                    }
                                                }
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    },
                    {analytics_constants.SORT: {analytics_constants.AGENT_ID: 1}},
                    {analytics_constants.SKIP: skip_count},
                    {analytics_constants.LIMIT: limit},
                ]

                self.__logger.debug(
                    f"Agent talk time distribution pipeline: {pipeline}"
                )
                result = await collection.aggregate(pipeline).to_list()
                self.__logger.debug(f"Aggregation result: {result}")
                self.__logger.info(
                    f"Successfully retrieved agent talk time distribution for partner_id: {partner_id}"
                )
                return {
                    analytics_constants.AGENTS: self._format_agent_response(
                        result,
                        [
                            analytics_constants.AGENT_ID,
                            analytics_constants.AGENT_NAME,
                            "buckets",
                        ],
                    ),
                    "total_count": total_count,
                }
        except Exception as e:
            self.__logger.error(
                f"Failed to retrieve agent talk time distribution: {str(e)}"
            )
            raise

    async def get_partner_service_board(
        self,
        partner_id: int,
        start_date: Optional[int],
        end_date: Optional[int],
        service_board_id: Optional[List[int]] = None,
        entity_type: Optional[str] = None,
        limit: int = 10,
        offset: int = 1,
        agents: Optional[List[int]] = None,
        user_role: int = TalkoUserRoleHierarchy.MAINTAINER.value,
    ) -> Dict:
        try:
            if not agents and user_role != TalkoUserRoleHierarchy.MAINTAINER.value:
                self.__logger.info(
                    f"No agents provided for partner_id: {partner_id}, returning empty result"
                )
                return {analytics_constants.AGENTS: [], "total_count": 0}
            self._validate_pagination(offset, limit)
            async with self.__db_manager.collection(
                TalkoCDR.CollectionName.TalkoCDR
            ) as collection:
                start_date_ms, end_date_ms, period = (
                    self.__date_range_helper.adjust_date_range(start_date, end_date)
                )
                self.__logger.debug(
                    f"Retrieving partner service board analytics for partner_id: {partner_id}, "
                    f"start_date: {start_date_ms}, end_date: {end_date_ms}, period: {period}, "
                    f"service_board_id: {'all' if service_board_id is None or len(service_board_id) == 0 else service_board_id}"
                )
                query = self.__query_builder.build_query(
                    partner_id,
                    start_date_ms,
                    end_date_ms,
                    agents=agents,
                    service_board_id=service_board_id,
                    entity_type=entity_type,
                    user_role=user_role,
                )

                pipeline = [
                    {analytics_constants.MATCH: query},
                    {
                        analytics_constants.GROUP: {
                            analytics_constants.UNDERSCORE_ID: analytics_constants.PARTNER_ID,
                            analytics_constants.TOTAL_CALLS: {
                                analytics_constants.SUM: 1
                            },
                            analytics_constants.TOTAL_UNIQUE_CALLS: {
                                analytics_constants.ADDTOSET: analytics_constants.LEAD_ID
                            },
                            analytics_constants.TOTAL_CONNECTED: {
                                analytics_constants.SUM: {
                                    analytics_constants.CONDITION: [
                                        {
                                            analytics_constants.EQ: [
                                                analytics_constants.CALL_STATUS,
                                                analytics_constants.ANSWERED,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            analytics_constants.TOTAL_MISSED: {
                                analytics_constants.SUM: {
                                    analytics_constants.CONDITION: [
                                        {
                                            analytics_constants.EQ: [
                                                analytics_constants.CALL_STATUS,
                                                analytics_constants.MISSED,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            analytics_constants.TOTAL_TALK_TIME: {
                                analytics_constants.SUM: analytics_constants.TALK_TIME
                            },
                            analytics_constants.TOTAL_CALL_DURATION: {
                                analytics_constants.SUM: analytics_constants.QUERY_TOTAL_CALL_DURATION
                            },
                        }
                    },
                    {
                        analytics_constants.PROJECT: {
                            analytics_constants.PARTNER_ID: analytics_constants.ID,
                            analytics_constants.TOTAL_CALLS: 1,
                            analytics_constants.TOTAL_UNIQUE_CALLS: {
                                analytics_constants.SIZE: "$total_unique_calls"
                            },
                            analytics_constants.TOTAL_CONNECTED: 1,
                            analytics_constants.TOTAL_MISSED: 1,
                            analytics_constants.TOTAL_TALK_TIME: 1,
                            analytics_constants.TOTAL_CALL_DURATION: 1,
                        }
                    },
                ]

                self.__logger.debug(f"Partner service board pipeline: {pipeline}")
                result = await collection.aggregate(pipeline).to_list()
                self.__logger.debug(f"Aggregation result: {result}")
                self.__logger.info(
                    f"Successfully retrieved partner service board analytics for partner_id: {partner_id}"
                )
                metrics = {
                    analytics_constants.TOTAL_CALLS: 0,
                    analytics_constants.TOTAL_UNIQUE_CALLS: 0,
                    analytics_constants.TOTAL_CONNECTED: 0,
                    analytics_constants.TOTAL_MISSED: 0,
                    analytics_constants.TOTAL_TALK_TIME: 0,
                    analytics_constants.TOTAL_CALL_DURATION: 0,
                }

                if result:
                    for field in metrics.keys():
                        metrics[field] = result[0].get(field, 0)

                # Now format into your required response
                response = {
                    "data": {
                        "current_date": int(datetime.now().timestamp() * 1000),
                        "data": [
                            {
                                "title": "Total Calls",
                                "count": metrics[analytics_constants.TOTAL_CALLS],
                            },
                            {
                                "title": "Unique Calls",
                                "count": metrics[
                                    analytics_constants.TOTAL_UNIQUE_CALLS
                                ],
                            },
                            {
                                "title": "Connected Calls",
                                "count": metrics[analytics_constants.TOTAL_CONNECTED],
                            },
                            {
                                "title": "Missed Calls",
                                "count": metrics[analytics_constants.TOTAL_MISSED],
                            },
                            {
                                "title": "Total Talk Time",
                                "count": metrics[analytics_constants.TOTAL_TALK_TIME],
                            },
                            {
                                "title": "Total Call Duration",
                                "count": metrics[
                                    analytics_constants.TOTAL_CALL_DURATION
                                ],
                            },
                        ],
                    },
                }
                self.__logger.debug(f"Get partner service board final data: {response}")
                return response
        except Exception as e:
            self.__logger.error(
                f"Failed to retrieve partner service board analytics: {str(e)}"
            )
            raise

    async def get_dashboard_call_trends(
        self,
        partner_id: int,
        start_date: Optional[int],
        end_date: Optional[int],
        agents: List[int],
        service_board_id: Optional[List[int]],
        entity_type: Optional[str],
        metric: str,
        trend_basis: str,
        limit: int,
        offset: int,
        user_role: int,
    ) -> Dict[str, Any]:
        """Retrieve dashboard followup trends for a partner with specified metric and trend basis."""
        try:
            self.__logger.info(
                "Retrieving call trends for partner {} — metric={}, trend={}".format(
                    partner_id, metric, trend_basis
                )
            )
            self.__logger.debug(
                "Parameters — start_date: {}, end_date: {}, agents: {}, service_board_id: {}, limit: {}, offset: {}, user_role: {}".format(
                    start_date,
                    end_date,
                    agents,
                    service_board_id,
                    limit,
                    offset,
                    user_role,
                )
            )

            self._validate_pagination(offset, limit)

            # Step 1: Prepare query parameters
            query, start_date_ms, end_date_ms, _ = (
                await self.__call_trends_helper.prepare_query_params(
                    partner_id,
                    start_date,
                    end_date,
                    agents,
                    service_board_id,
                    entity_type,
                    user_role,
                )
            )

            # Step 2: Projection and sorting
            projection, sort_order = (
                await self.__call_trends_helper.get_projection_and_sort_for_trends()
            )

            async with self.__db_manager.collection(
                TalkoCDR.CollectionName.TalkoCDR
            ) as collection:
                cdrs = await collection.find(
                    query, projection=projection, sort=sort_order
                ).to_list(None)

                # Step 3: Filter and format data
                filtered_docs, formatted_data, total_periods_count, current_month = (
                    await self.__call_trends_helper.filter_and_format_data(
                        cdrs,
                        metric,
                        trend_basis,
                        start_date_ms,
                        end_date_ms,
                        limit,
                        offset,
                    )
                )

                # Step 4: Total
                total_count = self.__call_trends_helper._calculate_total_count(
                    filtered_docs, metric
                )

                response = {
                    "trend_basis": trend_basis,
                    "selected_metric": metric,
                    "total_count": total_count,
                    "data": formatted_data,
                }
                if current_month and trend_basis == TalkoTimeInterval.DAYS.value:
                    response["current_month"] = current_month

                return response

        except Exception as e:
            self.__logger.error(f"Error retrieving dashboard call trends: {e}")
            raise
