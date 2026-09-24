from collections.abc import AsyncGenerator
from typing import Any

from bson import ObjectId
from pymongo.results import DeleteResult, InsertOneResult, UpdateResult

from src.components.did_management.constants import (
    TalkoDIDLayer,
    TalkoDIDStatus,
    TalkoDIDType,
)
from src.components.did_management.models import TalkoDidHistoryModel, TalkoPhoneNumberManagement
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil
from src.utils.phone_number_utils import normalize_phone_number


class TalkoDidRepository:
    """
    Repository class for handling DID-related database operations.
    """

    def __init__(self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger) -> None:
        self.__db_manager: TalkoDocDatabaseSessionManager = db_manager
        self.__logger: TalkoServiceLogger = logger

    async def insert_did_default_attendance(self, did_data: dict[str, Any]) -> dict[str, Any]:
        """
        Insert a new DID default attendance record.

        Args:
            did_data (Dict[str, Any]): Data to insert for DID attendance.

        Returns:
            Dict[str, Any]: Inserted record with _id added.

        Raises:
            Exception: For unexpected errors during insertion.
        """
        try:
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                result: InsertOneResult = await collection.insert_one(did_data)
                return {**did_data, "_id": result.inserted_id}
        except Exception as e:
            self.__logger.error(f"Failed to insert DID attendance: {str(e)}")
            raise

    async def insert_did_history(self, history_data: dict[str, Any]) -> dict[str, Any]:
        """
        Insert a new DID history record.

        Args:
            history_data (Dict[str, Any]): Data to insert for DID history.

        Returns:
            Dict[str, Any]: Inserted record with _id added.

        Raises:
            Exception: For unexpected errors during insertion.
        """
        try:
            async with self.__db_manager.collection(TalkoDidHistoryModel.CollectionName.DID_HISTORY) as collection:
                result: InsertOneResult = await collection.insert_one(history_data)
                return {**history_data, "_id": result.inserted_id}
        except Exception as e:
            self.__logger.error(f"Failed to insert DID history: {str(e)}")
            raise

    async def find_did_attendance(self, did_number: str, partner_id: int) -> dict[str, Any] | None:
        """
        Find a DID attendance record by DID number and parlast_10tner ID.

        Args:
            did_number (str): The DID number to search for.
            partner_id (int): The partner ID to filter by.

        Returns:
            Optional[Dict[str, Any]]: Found record or None if not found.

        Raises:
            Exception: For unexpected errors during retrieval.
        """
        try:
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                return await collection.find_one({"did_number": did_number, "partner_id": partner_id})
        except Exception as e:
            self.__logger.error(f"Failed to find DID attendance: {str(e)}")
            raise

    async def delete_did_default_attendance(self, did_number: str, partner_id: int) -> bool:
        """
        Delete a DID default attendance record by DID number and partner ID.

        Args:
            did_number (str): The DID number to delete.
            partner_id (int): The partner ID to filter by.

        Returns:
            bool: True if deleted, False otherwise.

        Raises:
            Exception: For unexpected errors during deletion.
        """
        try:
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                result: DeleteResult = await collection.delete_one({"did_number": did_number, "partner_id": partner_id})
                return result.deleted_count > 0
        except Exception as e:
            self.__logger.error(f"Failed to delete DID attendance: {str(e)}")
            raise

    async def update_did_history(
        self, did_number: str, partner_id: int, update_dict: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Update a DID history record by DID number and partner ID.

        Args:
            did_number (str): The DID number to update.
            partner_id (int): The partner ID to filter by.
            update_dict (Dict[str, Any]): The update data.

        Returns:
            Optional[Dict[str, Any]]: Updated record or None if not found.

        Raises:
            Exception: For unexpected errors during update.
        """
        try:
            async with self.__db_manager.collection(TalkoDidHistoryModel.CollectionName.DID_HISTORY) as collection:
                result: UpdateResult = await collection.find_one_and_update(
                    {"did_number": did_number, "partner_id": partner_id},
                    {"$set": update_dict},
                    return_document=True,
                )
                return result
        except Exception as e:
            self.__logger.error(f"Failed to update DID history: {str(e)}")
            raise

    async def get_assigned_dids(self, vendor_id: ObjectId) -> list[str]:
        """
        Fetch all assigned DIDs for a specific vendor.

        Args:
            vendor_id (ObjectId): The vendor ID to filter by.

        Returns:
            List[str]: List of assigned DID numbers.

        Raises:
            Exception: For unexpected errors during retrieval.
        """
        try:
            self.__logger.info(f"Fetching assigned DIDs for vendor {vendor_id}")
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(
                    {
                        "vendor_id": vendor_id,
                        "partner_id": {"$ne": 0},
                        "did_type": TalkoDIDType.NORMAL.value,
                        "is_active": True,
                    }
                )
                assigned_dids: list[str] = [doc["did_number"] async for doc in cursor]
                self.__logger.info(f"Fetched assigned DIDs: {assigned_dids}")
                return assigned_dids
        except Exception as e:
            self.__logger.error(f"Failed to fetch assigned DIDs: {str(e)}")
            raise

    async def get_available_dids(self, vendor_id: ObjectId, vendor_config_id: ObjectId | None = None) -> list[str]:
        """
        Fetch all available DIDs for a specific vendor.

        Args:
            vendor_id (ObjectId): The vendor ID to filter by.

        Returns:
            List[str]: List of available DID numbers.

        Raises:
            Exception: For unexpected errors during retrieval.
        """
        try:
            self.__logger.info(f"Fetching available DIDs for vendor {vendor_id}")
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(
                    {
                        "vendor_id": vendor_id,
                        "partner_id": 0,
                        "vendor_config_id": vendor_config_id,
                        "status": TalkoDIDStatus.AVAILABLE.value,
                        "did_type": TalkoDIDType.NORMAL.value,
                        "is_active": True,
                    }
                )
                available_dids: list[str] = [doc["did_number"] async for doc in cursor]
                self.__logger.info(f"Fetched available DIDs: {available_dids}")
                return available_dids
        except Exception as e:
            self.__logger.error(f"Failed to fetch available DIDs: {str(e)}")
            raise

    async def find_did_by_did_number_and_vendor_id(self, did_number: str, vendor_id: ObjectId) -> dict[str, Any] | None:
        """
        Find a DID record by DID number and vendor ID.

        Args:
            did_number (str): The DID number to search for.
            vendor_id (ObjectId): The vendor ID to filter by.

        Returns:
            Optional[Dict[str, Any]]: Found record or None if not found.

        Raises:
            Exception: For unexpected errors during retrieval.
        """
        try:
            self.__logger.debug(f"Searching for DID {did_number} with vendor_id {vendor_id}")
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                query = {"did_number": did_number, "vendor_id": vendor_id}
                self.__logger.debug(f"Executing query: {query}")
                result: dict[str, Any] | None = await collection.find_one(query)
                if result:
                    self.__logger.debug(f"Found DID {did_number} for vendor {vendor_id}")
                    return result
                self.__logger.warning(f"DID {did_number} not found for vendor {vendor_id} with query {query}")
                return None
        except Exception as e:
            self.__logger.error(f"Unexpected error finding DID {did_number}: {str(e)}")
            raise

    async def update_did_attendance(
        self, did_number: str, partner_id: int, update_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Update a DID attendance record by DID number and assign to a partner.

        Args:
            did_number (str): The DID number to update.
            partner_id (int): The partner ID to assign.
            update_data (Dict[str, Any]): The update data.

        Returns:
            Optional[Dict[str, Any]]: Updated record or None if not available.

        Raises:
            Exception: For unexpected errors during update.
        """
        try:
            self.__logger.debug(f"Updating DID {did_number} for partner {partner_id} with data {update_data}")
            # Read-check-then-write: needs the transaction connect() provides
            # (unlike the plain collection() helper) so the availability
            # check and the reassignment stay atomic against concurrent
            # callers racing for the same DID.
            async with self.__db_manager.connect() as db:
                collection = db[TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT]
                query = {"did_number": did_number, "partner_id": 0}
                self.__logger.debug(f"Executing initial query: {query}")
                existing_did: dict[str, Any] | None = await collection.find_one(query)
                if not existing_did:
                    self.__logger.warning(f"DID {did_number} not available (partner_id != 0)")
                    return None

                update_query: dict[str, Any] = {"did_number": did_number}
                update_data["partner_id"] = partner_id
                update_data["status_changed_at"] = TalkoDateTimeUtil().get_current_time()
                self.__logger.debug(f"Executing update query: {update_query} with data {update_data}")
                result: UpdateResult = await collection.find_one_and_update(
                    update_query, {"$set": update_data}, return_document=True
                )
                if result:
                    self.__logger.info(f"Successfully updated DID {did_number} to partner {partner_id}")
                    return result
                self.__logger.warning(f"Failed to update DID {did_number} to partner {partner_id}")
                return None
        except Exception as e:
            self.__logger.error(f"Unexpected error updating DID {did_number}: {str(e)}")
            raise

    async def get_dids_by_partner_and_vendor(self, partner_id: int, vendor_id: ObjectId) -> list[str]:
        """
        Fetch all DIDs assigned to a specific partner and vendor.

        Args:
            partner_id (int): The partner ID to filter by.
            vendor_id (ObjectId): The vendor ID to filter by.

        Returns:
            List[str]: List of DID numbers.

        Raises:
            Exception: For unexpected errors during retrieval.
        """
        try:
            self.__logger.info(f"Fetching DIDs for partner {partner_id} and vendor {vendor_id}")
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(
                    {
                        "partner_id": partner_id,
                        "vendor_id": vendor_id,
                        "did_type": TalkoDIDType.NORMAL.value,
                        "is_active": True,
                    }
                )
                dids: list[str] = [doc["did_number"] async for doc in cursor]
                self.__logger.info(f"Fetched DIDs get partner and vendor: {dids}")
                return dids
        except Exception as e:
            self.__logger.error(f"Failed to fetch DIDs for partner {partner_id}: {str(e)}")
            raise

    async def get_dids_by_partner_workspace_and_vendor(
        self,
        partner_id: int,
        workspace_id: int,
        vendor_id: ObjectId,
        vendor_config_id: ObjectId | None = None,
    ) -> list[str]:
        """
        Fetch all DIDs for a specific partner, workspace, and vendor.

        Args:
            partner_id (int): The partner ID to filter by.
            workspace_id (int): The workspace ID to filter by.
            vendor_id (ObjectId): The vendor ID to filter by.
            vendor_config_id (Optional[ObjectId]): The vendor config ID to filter by (optional).

        Returns:
            List[str]: List of DID numbers.
        """
        try:
            self.__logger.info(
                f"Fetching DIDs for partner {partner_id}, workspace {workspace_id}, vendor {vendor_id} and vendor_config {vendor_config_id}"
            )

            query: dict[str, Any] = {
                "partner_id": partner_id,
                "workspace_id": workspace_id,
                "vendor_id": vendor_id,
                "status": TalkoDIDStatus.MAPPED.value,
                "did_type": TalkoDIDType.NORMAL.value,
                "is_active": True,
            }

            # Only add vendor_config_id to query if provided
            if vendor_config_id:
                query["vendor_config_id"] = vendor_config_id

            self.__logger.info(f"Executing query: {query}")

            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(query)
                dids: list[str] = [doc["did_number"] async for doc in cursor]
                self.__logger.info(f"Fetched DIDs for partner workspace and vendor: {dids}")
                return dids
        except Exception as e:
            self.__logger.error(f"Failed to fetch DIDs for partner {partner_id}, workspace {workspace_id}: {str(e)}")
            raise

    async def get_dids_by_partner_agent_workspace_and_vendor(
        self, partner_id: int, user_id: int, workspace_id: int, vendor_id: ObjectId
    ) -> list[str]:
        """
        Fetch all DIDs for a specific partner, agent, workspace, and vendor.

        Args:
            partner_id (int): The partner ID to filter by.
            user_id (int): The agent ID to filter by.
            workspace_id (int): The workspace ID to filter by.
            vendor_id (ObjectId): The vendor ID to filter by.

        Returns:
            List[str]: List of DID numbers.

        Raises:
            Exception: For unexpected errors during retrieval.
        """
        try:
            self.__logger.info(
                f"Fetching DIDs for partner {partner_id}, agent {user_id}, workspace {workspace_id}, and vendor {vendor_id}"
            )
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(
                    {
                        "partner_id": partner_id,
                        "agent_id": user_id,
                        "workspace_id": workspace_id,
                        "vendor_id": vendor_id,
                        "did_type": TalkoDIDType.NORMAL.value,
                        "is_active": True,
                    }
                )
                dids = [doc["did_number"] async for doc in cursor]
                self.__logger.info(f"Fetched DIDs get did by partner agent workspace and vendor: {dids}")
                return dids
        except Exception as e:
            self.__logger.error(
                f"Failed to fetch DIDs for partner {partner_id}, agent {user_id}, workspace {workspace_id}: {str(e)}"
            )
            raise

    async def get_did_by_number(self, call_to_number: str, partner_id: int | None = None) -> dict | None:
        """
        Retrieve a DID record by the last 10 digits of the phone number.

        Args:
            call_to_number (str): The phone number to look up.

        Returns:
            Optional[Dict]: The DID record, or None if not found.

        Raises:
            Exception: For unexpected database errors.
        """
        try:
            self.__logger.debug(f"Searching DID for number: {call_to_number}")
            # Normalize: try last 10 digits and with 91 prefix
            candidates: str = normalize_phone_number(call_to_number, with_plus=False)

            self.__logger.info(f"Normalized candidates for DID search: {candidates}")

            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                query: dict = {"did_number": candidates, "is_active": True}
                if partner_id is not None:
                    query["partner_id"] = partner_id
                did_record: dict[str, Any] | None = await collection.find_one(query)

            if did_record:
                self.__logger.debug(f"Found DID record: {did_record}")
                return did_record
            self.__logger.info("No DID record found for given number")
            return None
        except Exception as e:
            self.__logger.error(f"Error finding DID by number: {str(e)}")
            raise

    async def get_dids_by_workspace(self, workspace_id: int) -> list[dict[str, Any]]:
        """
        Fetch all DID records for a given workspace ID.
        """
        try:
            self.__logger.info(f"Fetching DIDs for workspace_id={workspace_id}")
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(
                    {
                        "workspace_id": workspace_id,
                        "status": TalkoDIDStatus.MAPPED.value,
                        "did_type": TalkoDIDType.NORMAL.value,
                        "is_active": True,
                    }
                )
                records: list[dict[str, Any]] = await cursor.to_list(length=None)
                return records
        except Exception as e:
            self.__logger.error(f"Failed to fetch DIDs for workspace_id={workspace_id}: {str(e)}")
            raise

    async def get_details_by_dids(self, did_numbers: list[str]) -> list[dict[str, Any]]:
        """
        Fetch the _id (to be treated as instance_id) and did_number for a list of DID numbers.

        Args:
            did_numbers (List[str]): List of DID numbers to search for.

        Returns:
            List[Dict[str, Any]]: List of records containing 'did_number' and 'instance_id'.
        """
        try:
            self.__logger.info(f"Fetching instance IDs for DIDs: {did_numbers}")

            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(
                    {"did_number": {"$in": did_numbers}}, {"did_number": 1}
                )
                records: list[dict[str, Any]] = []
                async for doc in cursor:
                    records.append(
                        {
                            "did_number": doc["did_number"],
                            "instance_id": str(doc["_id"]),
                        }
                    )

            self.__logger.info(f"Fetched DID instance details: {records}")
            return records

        except Exception as e:
            self.__logger.error(f"Failed to fetch instance_id for DIDs {did_numbers}: {str(e)}")
            raise

    async def unassign_did_to_partner(self, did_number: str, partner_id: int) -> int:
        """
        Unassigns a DID from a partner by setting partner_id to 0.

        :param did_number: The DID number to unassign.
        """
        try:
            self.__logger.info(f"Unassigning DiD {did_number} to partner_id: {partner_id}")

            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                result: UpdateResult = await collection.update_one(
                    {"did_number": did_number},
                    {
                        "$set": {
                            "partner_id": 0,
                            "agent_id": None,
                            "workspace_id": None,
                        }
                    },
                )

            if result.modified_count > 0:
                self.__logger.info(f"Successfully unassigned DID {did_number}")
            else:
                self.__logger.warning(f"No records updated for DID {did_number}")

            return result.modified_count > 0

        except Exception as e:
            self.__logger.error(f"Failed to fetch instance_id for DIDs {did_number}: {str(e)}")
            raise

    async def update_did_status(
        self, did_number: str, partner_id: int, update_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Update a DID attendance record by DID number and assign to a partner.

        Args:
            did_number (str): The DID number to update.
            partner_id (int): The partner ID to assign.
            update_data (Dict[str, Any]): The update data.

        Returns:
            Optional[Dict[str, Any]]: Updated record or None if not available.

        Raises:
            Exception: For unexpected errors during update.
        """
        try:
            self.__logger.debug(f"Updating DID {did_number} for partner {partner_id} with data {update_data}")
            # Read-check-then-write — see update_did_attendance's comment on
            # why this needs connect()'s transaction rather than collection().
            async with self.__db_manager.connect() as db:
                collection = db[TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT]
                candidates: list[str] = normalize_phone_number(did_number, with_plus=False)

                self.__logger.info(f"Normalized candidates for DID search: {candidates}")
                query: dict[str, Any] = {
                    "did_number": candidates,
                    "partner_id": partner_id,
                }
                self.__logger.debug(f"Executing initial query: {query}")
                existing_did: dict[str, Any] | None = await collection.find_one(query)
                if not existing_did:
                    self.__logger.warning(f"DID {did_number} not available (partner_id != 0)")
                    return None

                update_query = {"did_number": did_number}
                update_data["partner_id"] = partner_id
                update_data["status_changed_at"] = TalkoDateTimeUtil().get_current_time()
                self.__logger.debug(f"Executing update query: {update_query} with data {update_data}")
                result: dict[str, Any] | None = await collection.find_one_and_update(
                    update_query, {"$set": update_data}, return_document=True
                )
                if result:
                    self.__logger.info(f"Successfully updated DID {did_number} to partner {partner_id}")
                    return result
                self.__logger.warning(f"Failed to update DID {did_number} to partner {partner_id}")
                return None
        except Exception as e:
            self.__logger.error(f"Unexpected error updating DID {did_number}: {str(e)}")
            raise

    async def increment_spam_count(self, did_number: str) -> bool:
        """
        Atomically increments the spam_count field by 1 for a given DID.

        Args:
            did_number (str): The DID number to update.

        Returns:
            bool: True if the document was found and updated, False otherwise.

        Raises:
            Exception: For unexpected database errors.
        """
        try:
            self.__logger.debug(f"Incrementing spam_count for DID: {did_number}")

            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                result: UpdateResult = await collection.update_one(
                    {"did_number": did_number}, {"$inc": {"spam_count": 1}}
                )

            if result.modified_count > 0:
                self.__logger.info(f"Successfully incremented spam_count for DID {did_number}")
                return True
            else:
                self.__logger.warning(f"No document found to increment spam_count for DID {did_number}")
                return False

        except Exception as e:
            self.__logger.error(f"Failed to increment spam_count for DID {did_number}: {str(e)}")
            raise

    async def get_dids_by_partner(
        self,
        partner_id: int,
        user_id: int | None = None,
        workspace_id: int | None = None,
        vendor_id: ObjectId | None = None,
        vendor_config_id: ObjectId | None = None,
        status: str | None = None,
        did_number: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch all DIDs for a specific partner, agent, workspace, vendor, and status.
        """

        try:
            self.__logger.info(
                f"Fetching DIDs for partner {partner_id}, agent {user_id}, workspace {workspace_id}, vendor {vendor_id}, vendor_config_id {vendor_config_id}, status {status}, did_number={did_number}, offset {offset}, limit {limit}"
            )

            # Base query
            query: dict[str, Any] = {
                "partner_id": partner_id,
                "is_active": True,
                "did_type": TalkoDIDType.NORMAL.value,
            }

            # Optional filters mapping
            optional_filters: dict[str, Any] = {
                "agent_id": user_id,
                "workspace_id": workspace_id,
                "vendor_id": vendor_id,
                "vendor_config_id": vendor_config_id,
                "status": status,
                "is_active": True,
            }

            # Add only non-None values
            query.update({k: v for k, v in optional_filters.items() if v is not None})

            # Partial DID number search (contains substring, case-insensitive)
            if did_number:
                cleaned: str = did_number.strip().replace(" ", "")
                if cleaned:
                    query["did_number"] = {"$regex": cleaned, "$options": "i"}

            self.__logger.debug(f"Executing query: {query}")

            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                total: int = await collection.count_documents(query)

                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(query).sort("status_changed_at", -1)

                if offset is not None and limit is not None:
                    skip: int = (offset - 1) * limit
                    cursor: AsyncGenerator[dict[str, Any], None] = cursor.skip(skip).limit(limit)

                docs: list[dict[str, Any]] = [doc async for doc in cursor]

            self.__logger.info(
                f"Fetched DIDs count={len(docs)} for partner={partner_id} agent={user_id} workspace={workspace_id}"
            )

            return docs, total
        except Exception as e:
            self.__logger.error(
                f"Failed to fetch DIDs partner={partner_id} agent={user_id} workspace={workspace_id} error={str(e)}"
            )
            raise

    async def get_ai_agent_dids(
        self,
        partner_id: int,
        agent_bot_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch all ai_agent DIDs assigned to a given agent_bot_id.
        """
        try:
            self.__logger.info(f"Fetching ai_agent DIDs for partner_id={partner_id} agent_bot_id={agent_bot_id}")
            query: dict[str, Any] = {
                "partner_id": partner_id,
                "did_type": TalkoDIDType.AI_AGENT.value,
                "is_active": True,
            }
            if agent_bot_id is not None:
                query["agent_bot_id"] = agent_bot_id

            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(query)
                return [doc async for doc in cursor]
        except Exception as e:
            self.__logger.error(f"Failed to fetch ai_agent DIDs for agent_bot_id={agent_bot_id}: {str(e)}")
            raise

    async def get_mapped_ai_agent_dids(
        self,
        partner_id: int,
        agent_bot_id: int,
    ) -> list[dict[str, Any]]:
        """
        Fetch ai_agent DIDs with status=MAPPED for a given agent_bot_id.
        """
        try:
            self.__logger.info(f"Fetching mapped ai_agent DIDs for partner_id={partner_id} agent_bot_id={agent_bot_id}")
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(
                    {
                        "partner_id": partner_id,
                        "did_type": TalkoDIDType.AI_AGENT.value,
                        "agent_bot_id": agent_bot_id,
                        "status": TalkoDIDStatus.MAPPED.value,
                        "is_active": True,
                    }
                )
                return [doc async for doc in cursor]
        except Exception as e:
            self.__logger.error(f"Failed to fetch mapped ai_agent DIDs for agent_bot_id={agent_bot_id}: {str(e)}")
            raise

    async def get_available_ai_agent_dids(
        self,
        partner_id: int,
    ) -> list[str]:
        """
        Fetch all available ai_agent DIDs for a specific partner.
        A DID is considered free if partner_id == 0 and status == AVAILABLE.
        """
        try:
            self.__logger.info(f"Fetching available ai_agent DIDs for partner_id={partner_id}")
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                query: dict[str, Any] = {
                    "partner_id": partner_id,
                    "status": TalkoDIDStatus.AVAILABLE.value,
                    "did_type": TalkoDIDType.AI_AGENT.value,
                    "is_active": True,
                }

                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(query)
                dids: list[str] = [doc["did_number"] async for doc in cursor]
                self.__logger.info(f"Fetched available ai_agent DIDs: {dids}")
                return dids
        except Exception as e:
            self.__logger.error(f"Failed to fetch available ai_agent DIDs: {str(e)}")
            raise

    async def update_did_values(
        self,
        did_number: str,
        partner_id: int | None = None,
        update_data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Flexible DID update method.

        - If partner_id is provided in update_data or as parameter → search using that partner_id.
        - Otherwise (new assignment case) → search with partner_id = 0.
        """
        if update_data is None:
            update_data = {}

        try:
            self.__logger.debug(
                f"update_did_values called -> did_number={did_number}, "
                f"partner_id={partner_id}, update_data={update_data}"
            )

            # Read-check-then-write — see update_did_attendance's comment on
            # why this needs connect()'s transaction rather than collection().
            async with self.__db_manager.connect() as db:
                collection = db[TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT]

                # === Build Find Query ===
                find_query: dict[str, Any] = {"did_number": did_number}

                # Priority 1: Use partner_id passed as parameter
                if partner_id is not None:
                    find_query["partner_id"] = partner_id

                # Priority 2: Default for new assignments (available DIDs)
                else:
                    find_query["partner_id"] = 0

                self.__logger.debug(f"Find query built: {find_query}")

                existing_did = await collection.find_one(find_query)
                if not existing_did:
                    self.__logger.warning(f"DID {did_number} not found or not available with query: {find_query}")
                    return None

                # === Prepare Update Payload ===
                update_payload = update_data.copy()
                update_payload["status_changed_at"] = TalkoDateTimeUtil().get_current_time()

                # Ensure partner_id is set in update if provided
                if partner_id is not None:
                    update_payload["partner_id"] = partner_id

                update_query = {"did_number": did_number}

                result = await collection.find_one_and_update(
                    update_query, {"$set": update_payload}, return_document=True
                )

                if result:
                    self.__logger.info(f"Successfully updated DID {did_number}")
                    return result
                else:
                    self.__logger.warning(f"Update failed for DID {did_number}")
                    return None

        except Exception as e:
            self.__logger.error(f"Error updating DID {did_number}: {str(e)}")
            raise

    async def get_display_names_by_dids(self, did_numbers: list[str]) -> dict[str, str]:
        """
        Fetch display_name for a list of DID numbers, keyed by the *normalized*
        did_number (no leading '+'), since phone_number_management stores
        did_number without '+' while TalkoCDR documents may store it with '+'.
        Callers must look up using the same normalized form.
        """
        if not did_numbers:
            return {}
        try:
            normalized_numbers = [normalize_phone_number(d, with_plus=False) for d in did_numbers]
            self.__logger.info(f"Fetching display names for normalized DIDs: {normalized_numbers}")
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[dict[str, Any], None] = collection.find(
                    {"did_number": {"$in": normalized_numbers}},
                    {"did_number": 1, "display_name": 1},
                )
                display_name_map: dict[str, str] = {}
                async for doc in cursor:
                    display_name_map[doc["did_number"]] = doc.get("display_name") or ""

            self.__logger.info(f"Fetched display name map for {len(display_name_map)} DIDs")
            return display_name_map
        except Exception as e:
            self.__logger.error(f"Failed to fetch display names for DIDs {did_numbers}: {str(e)}")
            raise

    async def find_external_did(self, did_number: str, vendor_id: ObjectId | None = None) -> dict[str, Any] | None:
        """Find an EXTERNAL layer DID by number (optionally scoped to vendor)."""
        try:
            query: dict[str, Any] = {
                "did_number": did_number,
                "did_layer": TalkoDIDLayer.EXTERNAL.value,
            }
            if vendor_id is not None:
                query["vendor_id"] = vendor_id
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                return await collection.find_one(query)
        except Exception as e:
            self.__logger.error(f"Failed to find external DID {did_number}: {str(e)}")
            raise

    async def find_internal_by_parent(
        self, parent_did_number: str, partner_id: int | None = None
    ) -> list[dict[str, Any]]:
        """List INTERNAL DIDs provisioned from a given EXTERNAL parent."""
        try:
            query: dict[str, Any] = {
                "did_layer": TalkoDIDLayer.INTERNAL.value,
                "parent_did_number": parent_did_number,
            }
            if partner_id is not None:
                query["partner_id"] = partner_id
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor = collection.find(query)
                return [doc async for doc in cursor]
        except Exception as e:
            self.__logger.error(f"Failed to find internal DIDs for parent {parent_did_number}: {str(e)}")
            raise

    async def get_pool_utilization(self, vendor_id: ObjectId | None = None) -> list[dict[str, Any]]:
        """Aggregate counts by (did_layer, status) for pool dashboard."""
        try:
            pipeline: list[dict[str, Any]] = []
            if vendor_id is not None:
                pipeline.append({"$match": {"vendor_id": vendor_id}})
            pipeline.append(
                {
                    "$group": {
                        "_id": {
                            "did_layer": {"$ifNull": ["$did_layer", TalkoDIDLayer.EXTERNAL.value]},
                            "status": "$status",
                        },
                        "count": {"$sum": 1},
                    }
                }
            )
            async with self.__db_manager.collection(
                TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor = collection.aggregate(pipeline)
                rows = [doc async for doc in cursor]
                return [
                    {
                        "did_layer": doc["_id"].get("did_layer", TalkoDIDLayer.EXTERNAL.value),
                        "status": doc["_id"].get("status"),
                        "count": doc.get("count", 0),
                    }
                    for doc in rows
                ]
        except Exception as e:
            self.__logger.error(f"Failed to get pool utilization: {str(e)}")
            raise
