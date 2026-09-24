import re
from typing import Any

from src.components.cdr.constants import AGENT_STATUS_EXPR, LEAD_STATUS_EXPR
from src.components.cdr.models import TalkoCDR
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoCDRRepository:
    def __init__(self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger):
        self.__db_manager = db_manager
        self.__logger = logger

    async def insert_cdr(self, cdr_dict: dict) -> str:
        try:
            async with self.__db_manager.collection(TalkoCDR.CollectionName.TalkoCDR) as collection:
                result: Any = await collection.insert_one(cdr_dict)
                self.__logger.info(f"Inserted TalkoCDR with ID: {result.inserted_id}")
                return str(result.inserted_id)
        except Exception as e:
            self.__logger.error(f"Failed to insert TalkoCDR: {str(e)}")
            raise

    async def get_cdrs_by_criteria(self, query: dict, limit: int | None = None, skip: int | None = None) -> list[dict]:
        """
        Fetch CDRs matching the provided query criteria.

        Args:
            query: MongoDB query dictionary.

        Returns:
            List[Dict]: List of TalkoCDR documents.
        """
        try:
            async with self.__db_manager.collection(TalkoCDR.CollectionName.TalkoCDR) as collection:
                cursor = collection.find(query)

                # Optional pagination — used by batch processes only
                if skip:
                    cursor = cursor.skip(skip)
                if limit:
                    cursor = cursor.limit(limit)

                to_list_limit = limit if limit else None
                cdrs: list[dict[str, Any]] = await cursor.to_list(to_list_limit)
                self.__logger.info(f"Fetched {len(cdrs)} CDRs for query: {query}")
                return cdrs
        except Exception as e:
            self.__logger.error(f"Failed to fetch CDRs for query {query}: {str(e)}")
            raise

    async def find_all_cdrs_on_the_basis_of_partner_id(
        self, partner_id: int, offset: int, limit: int, created_at: int | None = None
    ) -> list[dict]:
        try:
            async with self.__db_manager.collection(TalkoCDR.CollectionName.TalkoCDR) as collection:
                skip_count: int = (offset - 1) * limit

                # Base filter
                query: dict = {"partner_id": partner_id}

                # Add created_at filter if provided
                if created_at is not None:
                    query["created_at"] = {"$gt": created_at}

                cursor: dict | None = collection.find(query).skip(skip_count).limit(limit).max_time_ms(250000)
                results: list = []
                async for cdr in cursor:
                    results.append(cdr)
                return list(results)
        except Exception as e:
            self.__logger.error(f"Failed to retrieve partner CDRs: {str(e)}")
            raise

    async def find_all_call_logs_on_the_basis_of_user_id(
        self,
        user_id,
        limit,
        offset,
        query,
        projection=None,
        status_match: dict | None = None,
    ):
        try:
            async with self.__db_manager.collection(TalkoCDR.CollectionName.TalkoCDR) as collection:
                self.__logger.debug(
                    f"Retrieving call logs for user_id: {user_id}, query: {query}, status_match: {status_match}, limit: {limit}, offset: {offset}"
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
                # $addFields) from scratch. At TalkoCDR's scale (tens of millions of
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

                facet_result = await collection.aggregate(facet_pipeline, allowDiskUse=True, maxTimeMS=250000).to_list(
                    1
                )

                if not facet_result:
                    return [], 0

                total_count = facet_result[0]["count"][0]["total"] if facet_result[0]["count"] else 0
                results = facet_result[0]["data"]

                self.__logger.debug(f"Total count for query: {total_count}, skip: {skip_count}, limit: {limit}")

                if total_count > 0 and skip_count >= total_count:
                    self.__logger.warning(f"Offset {offset} exceeds total_count {total_count}")

                return results, total_count
        except Exception as e:
            self.__logger.error(f"Failed to retrieve agent CDRs: {str(e)}. Query: {query}")
            raise

    async def find_one_cdr_by_identifier(
        self,
        call_id: str | None = None,
        call_uuid: str | None = None,
        vendor_config_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Fetch a single TalkoCDR using call_id or call_uuid and return only
        fields required for CallRecordHistoryResponse.
        """
        try:
            if call_id is None and call_uuid is None:
                self.__logger.error("find_call_record_history_by_identifier requires call_id or call_uuid")
                return None

            query: dict[str, Any] = {}
            identifier_filters: list[dict[str, Any]] = []

            if call_id is not None:
                identifier_filters.append({"call_id": {"$regex": f"^{re.escape(call_id)}$", "$options": "i"}})

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

            projection: dict[str, int] = {
                "_id": 0,
                "partner_id": 1,
                "agent": 1,
                "lead_id": 1,
                "workspace_id": 1,
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

            async with self.__db_manager.collection(TalkoCDR.CollectionName.TalkoCDR) as collection:
                cdr: dict[str, Any] | None = await collection.find_one(query, projection)

            self.__logger.info(f"Fetched call record history by identifier. query: {query}")
            return cdr

        except Exception as e:
            self.__logger.error(f"Failed to fetch call record history by identifier: {str(e)}")
            raise

    async def update_one(self, filter_query: dict, update_data: dict) -> bool:
        try:
            async with self.__db_manager.collection(TalkoCDR.CollectionName.TalkoCDR) as collection:
                result = await collection.update_one(filter_query, update_data)
                self.__logger.info(
                    f"Updated TalkoCDR — matched: {result.matched_count}, modified: {result.modified_count}"
                )
                return result.modified_count > 0
        except Exception as e:
            self.__logger.error(f"Failed to update TalkoCDR: {str(e)}")
            raise

    async def find_cdr_by_call_id(self, call_id: str) -> dict[str, Any] | None:
        """
        Fetch a single TalkoCDR by call_id for the purpose of setting custom
        field values (needs partner_id for tenant checks and the existing
        custom_fields map to merge into).
        """
        try:
            projection: dict[str, int] = {
                "_id": 1,
                "call_id": 1,
                "call_uuid": 1,
                "partner_id": 1,
                "custom_fields": 1,
            }
            async with self.__db_manager.collection(TalkoCDR.CollectionName.TalkoCDR) as collection:
                cdr: dict[str, Any] | None = await collection.find_one({"call_id": call_id}, projection)
            self.__logger.info(f"Fetched TalkoCDR by call_id: {call_id}")
            return cdr
        except Exception as e:
            self.__logger.error(f"Failed to fetch TalkoCDR by call_id {call_id}: {str(e)}")
            raise

    async def set_custom_field_values(
        self, call_id: str, values: dict[str, Any], updated_at: int
    ) -> dict[str, Any] | None:
        """
        Merge the given slug -> value pairs into the TalkoCDR's custom_fields map
        using dot-notation $set, and return the updated document.
        """
        try:
            update_ops: dict[str, Any] = {f"custom_fields.{slug}": value for slug, value in values.items()}
            update_ops["updated_at"] = updated_at

            async with self.__db_manager.collection(TalkoCDR.CollectionName.TalkoCDR) as collection:
                result: dict[str, Any] | None = await collection.find_one_and_update(
                    {"call_id": call_id},
                    {"$set": update_ops},
                    projection={"_id": 1, "call_id": 1, "custom_fields": 1},
                    return_document=True,
                )
            self.__logger.info(f"Set custom field values for call_id {call_id}: {values}")
            return result
        except Exception as e:
            self.__logger.error(f"Failed to set custom field values for call_id {call_id}: {str(e)}")
            raise
