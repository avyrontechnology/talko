import re
from typing import Any, Dict, List, Optional, Tuple, Union

from src.components.cdr.constants import AGENT_STATUS_EXPR, LEAD_STATUS_EXPR
from src.components.cdr.models import CDR
from src.core.doc_db import DocDatabaseSessionManager
from src.loggers.holler_service_logger import HollerServiceLogger


class CDRRepository:
    def __init__(
        self, db_manager: DocDatabaseSessionManager, logger: HollerServiceLogger
    ):
        self.__db_manager = db_manager
        self.__logger = logger

    async def insert_cdr(self, cdr_dict: dict) -> str:
        try:
            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                result: Any = await collection.insert_one(cdr_dict)
                self.__logger.info(
                    "Inserted CDR with ID: {}".format(result.inserted_id)
                )
                return str(result.inserted_id)
        except Exception as e:
            self.__logger.error("Failed to insert CDR: {}".format(str(e)))
            raise

    async def get_cdrs_by_criteria(
        self, query: Dict, limit: Union[int, None] = None, skip: Union[int, None] = None
    ) -> List[Dict]:
        """
        Fetch CDRs matching the provided query criteria.

        Args:
            query: MongoDB query dictionary.

        Returns:
            List[Dict]: List of CDR documents.
        """
        try:
            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                cursor = collection.find(query)

                # Optional pagination — used by batch processes only
                if skip:
                    cursor = cursor.skip(skip)
                if limit:
                    cursor = cursor.limit(limit)

                to_list_limit = limit if limit else None
                cdrs: List[Dict[str, Any]] = await cursor.to_list(to_list_limit)
                self.__logger.info(
                    "Fetched {} CDRs for query: {}".format(len(cdrs), query)
                )
                return cdrs
        except Exception as e:
            self.__logger.error(
                "Failed to fetch CDRs for query {}: {}".format(query, str(e))
            )
            raise

    async def find_all_cdrs_on_the_basis_of_partner_id(
        self, partner_id: int, offset: int, limit: int, created_at: Optional[int] = None
    ) -> list[dict]:
        try:
            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                skip_count: int = (offset - 1) * limit

                # Base filter
                query: dict = {"partner_id": partner_id}

                # Add created_at filter if provided
                if created_at is not None:
                    query["created_at"] = {"$gt": created_at}

                cursor: Optional[dict] = (
                    collection.find(query)
                    .skip(skip_count)
                    .limit(limit)
                    .max_time_ms(250000)
                )
                results: list = []
                async for cdr in cursor:
                    results.append(cdr)
                return list(results)
        except Exception as e:
            self.__logger.error("Failed to retrieve partner CDRs: {}".format(str(e)))
            raise

    async def find_all_call_logs_on_the_basis_of_user_id(
        self,
        user_id,
        limit,
        offset,
        query,
        projection=None,
        status_match: Optional[dict] = None,
    ):
        try:
            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                self.__logger.debug(
                    "Retrieving call logs for user_id: {}, query: {}, status_match: {}, limit: {}, offset: {}".format(
                        user_id, query, status_match, limit, offset
                    )
                )
                skip_count = (offset - 1) * limit

                base_stages: list = [{"$match": query}]

                if status_match:
                    base_stages.append(
                        {
                            "$addFields": {
                                "agent_call_status": AGENT_STATUS_EXPR,
                                "lead_call_status": LEAD_STATUS_EXPR,
                            }
                        }
                    )
                    base_stages.append({"$match": status_match})

                # --- page + total in a single pass over the matched documents ---
                # Previously this ran two separate aggregate calls (count, then
                # data), each redoing the $match (and any status_match
                # $addFields) from scratch. At CDR's scale (tens of millions of
                # rows) that's a full extra index/collection pass for every
                # request. $facet shares the upstream matched-document stream
                # between both branches in one round trip instead.
                data_stage_pipeline: list = [
                    {"$sort": {"created_at": -1}},
                    {"$skip": skip_count},
                    {"$limit": limit},
                ]
                if projection:
                    data_stage_pipeline.append({"$project": projection})

                facet_pipeline = base_stages + [
                    {
                        "$facet": {
                            "data": data_stage_pipeline,
                            "count": [{"$count": "total"}],
                        }
                    }
                ]

                facet_result = await collection.aggregate(
                    facet_pipeline, allowDiskUse=True, maxTimeMS=250000
                ).to_list(1)

                if not facet_result:
                    return [], 0

                total_count = (
                    facet_result[0]["count"][0]["total"]
                    if facet_result[0]["count"]
                    else 0
                )
                results = facet_result[0]["data"]

                self.__logger.debug(
                    "Total count for query: {}, skip: {}, limit: {}".format(
                        total_count, skip_count, limit
                    )
                )

                if total_count > 0 and skip_count >= total_count:
                    self.__logger.warning(
                        "Offset {} exceeds total_count {}".format(offset, total_count)
                    )

                return results, total_count
        except Exception as e:
            self.__logger.error(
                "Failed to retrieve agent CDRs: {}. Query: {}".format(str(e), query)
            )
            raise

    async def find_one_cdr_by_identifier(
        self,
        call_id: Optional[str] = None,
        call_uuid: Optional[str] = None,
        vendor_config_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single CDR using call_id or call_uuid and return only
        fields required for CallRecordHistoryResponse.
        """
        try:
            if call_id is None and call_uuid is None:
                self.__logger.error(
                    "find_call_record_history_by_identifier requires call_id or call_uuid"
                )
                return None

            query: Dict[str, Any] = {}
            identifier_filters: List[Dict[str, Any]] = []

            if call_id is not None:
                identifier_filters.append(
                    {"call_id": {"$regex": f"^{re.escape(call_id)}$", "$options": "i"}}
                )

            if call_uuid is not None:
                identifier_filters.append(
                    {
                        "call_uuid": {
                            "$regex": f"^{re.escape(call_uuid)}$",
                            "$options": "i",
                        }
                    }
                )

            if len(identifier_filters) == 1:
                query.update(identifier_filters[0])
            else:
                query["$or"] = identifier_filters

            if vendor_config_id is not None:
                query["vendor_config_id"] = vendor_config_id

            projection: Dict[str, int] = {
                "_id": 0,
                "partner_id": 1,
                "agent": 1,
                "lead_id": 1,
                "service_board_id": 1,
                "calling_mode": 1,
                "call_status": 1,
                "call_recording": 1,
                "lead_number": 1,
                "total_call_duration": 1,
                "talk_time": 1,
                "did_number": 1,
                "agent_number": 1,
                "reason": 1,
                "hangup_cause": 1,
                "reason_key": 1,
                "hangup_by": 1,
                "created_at": 1,
                "action_performed_by": 1,
                "lead_call_status": 1,
                "agent_call_status": 1,
                "call_connected": 1,
                "lead_name": 1,
                "call_type": 1,
                "do_recording_url": 1,
                "number_type": 1,
                "lead_secret": 1,
                "call_id": 1,
                "call_uuid": 1,
                "vendor_id": 1,
                "vendor_config_id": 1,
                "custom_fields": 1,
            }

            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                cdr: Optional[Dict[str, Any]] = await collection.find_one(
                    query, projection
                )

            self.__logger.info(
                "Fetched call record history by identifier. query: {}".format(query)
            )
            return cdr

        except Exception as e:
            self.__logger.error(
                "Failed to fetch call record history by identifier: {}".format(str(e))
            )
            raise

    async def update_one(self, filter_query: Dict, update_data: Dict) -> bool:
        try:
            async with self.__db_manager.collection(CDR.CollectionName.CDR) as collection:
                result = await collection.update_one(filter_query, update_data)
                self.__logger.info(
                    "Updated CDR — matched: {}, modified: {}".format(
                        result.matched_count, result.modified_count
                    )
                )
                return result.modified_count > 0
        except Exception as e:
            self.__logger.error("Failed to update CDR: {}".format(str(e)))
            raise

    async def find_cdr_by_call_id(self, call_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single CDR by call_id for the purpose of setting custom
        field values (needs partner_id for tenant checks and the existing
        custom_fields map to merge into).
        """
        try:
            projection: Dict[str, int] = {
                "_id": 1,
                "call_id": 1,
                "call_uuid": 1,
                "partner_id": 1,
                "custom_fields": 1,
            }
            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                cdr: Optional[Dict[str, Any]] = await collection.find_one(
                    {"call_id": call_id}, projection
                )
            self.__logger.info("Fetched CDR by call_id: {}".format(call_id))
            return cdr
        except Exception as e:
            self.__logger.error(
                "Failed to fetch CDR by call_id {}: {}".format(call_id, str(e))
            )
            raise

    async def set_custom_field_values(
        self, call_id: str, values: Dict[str, Any], updated_at: int
    ) -> Optional[Dict[str, Any]]:
        """
        Merge the given slug -> value pairs into the CDR's custom_fields map
        using dot-notation $set, and return the updated document.
        """
        try:
            update_ops: Dict[str, Any] = {
                "custom_fields.{}".format(slug): value for slug, value in values.items()
            }
            update_ops["updated_at"] = updated_at

            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                result: Optional[Dict[str, Any]] = await collection.find_one_and_update(
                    {"call_id": call_id},
                    {"$set": update_ops},
                    projection={"_id": 1, "call_id": 1, "custom_fields": 1},
                    return_document=True,
                )
            self.__logger.info(
                "Set custom field values for call_id {}: {}".format(call_id, values)
            )
            return result
        except Exception as e:
            self.__logger.error(
                "Failed to set custom field values for call_id {}: {}".format(
                    call_id, str(e)
                )
            )
            raise
