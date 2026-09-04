from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from bson import ObjectId
from pymongo.results import DeleteResult, InsertOneResult, UpdateResult

from src.components.did_management.constants import DIDStatus, DIDType
from src.components.did_management.models import DidHistoryModel, PhoneNumberManagement
from src.core.doc_db import DocDatabaseSessionManager
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.datetime_util import DateTimeUtil
from src.utils.phone_number_utils import normalize_phone_number


class DidRepository:
    """
    Repository class for handling DID-related database operations.
    """

    def __init__(
        self, db_manager: DocDatabaseSessionManager, logger: HollerServiceLogger
    ) -> None:
        self.__db_manager: DocDatabaseSessionManager = db_manager
        self.__logger: HollerServiceLogger = logger

    async def insert_did_default_attendance(
        self, did_data: Dict[str, Any]
    ) -> Dict[str, Any]:
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
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                result: InsertOneResult = await collection.insert_one(did_data)
                return {**did_data, "_id": result.inserted_id}
        except Exception as e:
            self.__logger.error("Failed to insert DID attendance: {}".format(str(e)))
            raise

    async def insert_did_history(self, history_data: Dict[str, Any]) -> Dict[str, Any]:
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
            async with self.__db_manager.collection(
                DidHistoryModel.CollectionName.DID_HISTORY
            ) as collection:
                result: InsertOneResult = await collection.insert_one(history_data)
                return {**history_data, "_id": result.inserted_id}
        except Exception as e:
            self.__logger.error("Failed to insert DID history: {}".format(str(e)))
            raise

    async def find_did_attendance(
        self, did_number: str, partner_id: int
    ) -> Optional[Dict[str, Any]]:
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
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                return await collection.find_one(
                    {"did_number": did_number, "partner_id": partner_id}
                )
        except Exception as e:
            self.__logger.error("Failed to find DID attendance: {}".format(str(e)))
            raise

    async def delete_did_default_attendance(
        self, did_number: str, partner_id: int
    ) -> bool:
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
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                result: DeleteResult = await collection.delete_one(
                    {"did_number": did_number, "partner_id": partner_id}
                )
                return result.deleted_count > 0
        except Exception as e:
            self.__logger.error("Failed to delete DID attendance: {}".format(str(e)))
            raise

    async def update_did_history(
        self, did_number: str, partner_id: int, update_dict: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
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
            async with self.__db_manager.collection(
                DidHistoryModel.CollectionName.DID_HISTORY
            ) as collection:
                result: UpdateResult = await collection.find_one_and_update(
                    {"did_number": did_number, "partner_id": partner_id},
                    {"$set": update_dict},
                    return_document=True,
                )
                return result
        except Exception as e:
            self.__logger.error("Failed to update DID history: {}".format(str(e)))
            raise

    async def get_assigned_dids(self, vendor_id: ObjectId) -> List[str]:
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
            self.__logger.info("Fetching assigned DIDs for vendor {}".format(vendor_id))
            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(
                    {
                        "vendor_id": vendor_id,
                        "partner_id": {"$ne": 0},
                        "did_type": DIDType.NORMAL.value,
                        "is_active": True,
                    }
                )
                assigned_dids: List[str] = [doc["did_number"] async for doc in cursor]
                self.__logger.info("Fetched assigned DIDs: {}".format(assigned_dids))
                return assigned_dids
        except Exception as e:
            self.__logger.error("Failed to fetch assigned DIDs: {}".format(str(e)))
            raise

    async def get_available_dids(
        self, vendor_id: ObjectId, vendor_config_id: Optional[ObjectId] = None
    ) -> List[str]:
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
            self.__logger.info(
                "Fetching available DIDs for vendor {}".format(vendor_id)
            )
            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(
                    {
                        "vendor_id": vendor_id,
                        "partner_id": 0,
                        "vendor_config_id": vendor_config_id,
                        "status": DIDStatus.AVAILABLE.value,
                        "did_type": DIDType.NORMAL.value,
                        "is_active": True,
                    }
                )
                available_dids: List[str] = [doc["did_number"] async for doc in cursor]
                self.__logger.info("Fetched available DIDs: {}".format(available_dids))
                return available_dids
        except Exception as e:
            self.__logger.error("Failed to fetch available DIDs: {}".format(str(e)))
            raise

    async def find_did_by_did_number_and_vendor_id(
        self, did_number: str, vendor_id: ObjectId
    ) -> Optional[Dict[str, Any]]:
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
            self.__logger.debug(
                "Searching for DID {} with vendor_id {}".format(did_number, vendor_id)
            )
            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                query = {"did_number": did_number, "vendor_id": vendor_id}
                self.__logger.debug("Executing query: {}".format(query))
                result: Optional[Dict[str, Any]] = await collection.find_one(query)
                if result:
                    self.__logger.debug(
                        "Found DID {} for vendor {}".format(did_number, vendor_id)
                    )
                    return result
                self.__logger.warning(
                    "DID {} not found for vendor {} with query {}".format(
                        did_number, vendor_id, query
                    )
                )
                return None
        except Exception as e:
            self.__logger.error(
                "Unexpected error finding DID {}: {}".format(did_number, str(e))
            )
            raise

    async def update_did_attendance(
        self, did_number: str, partner_id: int, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
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
            self.__logger.debug(
                "Updating DID {} for partner {} with data {}".format(
                    did_number, partner_id, update_data
                )
            )
            # Read-check-then-write: needs the transaction connect() provides
            # (unlike the plain collection() helper) so the availability
            # check and the reassignment stay atomic against concurrent
            # callers racing for the same DID.
            async with self.__db_manager.connect() as db:
                collection = db[
                    PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
                ]
                query = {"did_number": did_number, "partner_id": 0}
                self.__logger.debug("Executing initial query: {}".format(query))
                existing_did: Optional[Dict[str, Any]] = await collection.find_one(
                    query
                )
                if not existing_did:
                    self.__logger.warning(
                        "DID {} not available (partner_id != 0)".format(did_number)
                    )
                    return None

                update_query: Dict[str, Any] = {"did_number": did_number}
                update_data["partner_id"] = partner_id
                update_data["status_changed_at"] = DateTimeUtil().get_current_time()
                self.__logger.debug(
                    "Executing update query: {} with data {}".format(
                        update_query, update_data
                    )
                )
                result: UpdateResult = await collection.find_one_and_update(
                    update_query, {"$set": update_data}, return_document=True
                )
                if result:
                    self.__logger.info(
                        "Successfully updated DID {} to partner {}".format(
                            did_number, partner_id
                        )
                    )
                    return result
                self.__logger.warning(
                    "Failed to update DID {} to partner {}".format(
                        did_number, partner_id
                    )
                )
                return None
        except Exception as e:
            self.__logger.error(
                "Unexpected error updating DID {}: {}".format(did_number, str(e))
            )
            raise

    async def get_dids_by_partner_and_vendor(
        self, partner_id: int, vendor_id: ObjectId
    ) -> List[str]:
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
            self.__logger.info(
                "Fetching DIDs for partner {} and vendor {}".format(
                    partner_id, vendor_id
                )
            )
            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(
                    {
                        "partner_id": partner_id,
                        "vendor_id": vendor_id,
                        "did_type": DIDType.NORMAL.value,
                        "is_active": True,
                    }
                )
                dids: List[str] = [doc["did_number"] async for doc in cursor]
                self.__logger.info(
                    "Fetched DIDs get partner and vendor: {}".format(dids)
                )
                return dids
        except Exception as e:
            self.__logger.error(
                "Failed to fetch DIDs for partner {}: {}".format(partner_id, str(e))
            )
            raise

    async def get_dids_by_partner_service_board_and_vendor(
        self,
        partner_id: int,
        service_board_id: int,
        vendor_id: ObjectId,
        vendor_config_id: Optional[ObjectId] = None,
    ) -> List[str]:
        """
        Fetch all DIDs for a specific partner, service board, and vendor.

        Args:
            partner_id (int): The partner ID to filter by.
            service_board_id (int): The service board ID to filter by.
            vendor_id (ObjectId): The vendor ID to filter by.
            vendor_config_id (Optional[ObjectId]): The vendor config ID to filter by (optional).

        Returns:
            List[str]: List of DID numbers.
        """
        try:
            self.__logger.info(
                "Fetching DIDs for partner {}, service_board {}, vendor {} and vendor_config {}".format(
                    partner_id, service_board_id, vendor_id, vendor_config_id
                )
            )

            query: Dict[str, Any] = {
                "partner_id": partner_id,
                "service_board_id": service_board_id,
                "vendor_id": vendor_id,
                "status": DIDStatus.MAPPED.value,
                "did_type": DIDType.NORMAL.value,
                "is_active": True,
            }

            # Only add vendor_config_id to query if provided
            if vendor_config_id:
                query["vendor_config_id"] = vendor_config_id

            self.__logger.info("Executing query: {}".format(query))

            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(query)
                dids: List[str] = [doc["did_number"] async for doc in cursor]
                self.__logger.info(
                    "Fetched DIDs for partner service board and vendor: {}".format(dids)
                )
                return dids
        except Exception as e:
            self.__logger.error(
                "Failed to fetch DIDs for partner {}, service_board {}: {}".format(
                    partner_id, service_board_id, str(e)
                )
            )
            raise

    async def get_dids_by_partner_agent_service_board_and_vendor(
        self, partner_id: int, user_id: int, service_board_id: int, vendor_id: ObjectId
    ) -> List[str]:
        """
        Fetch all DIDs for a specific partner, agent, service board, and vendor.

        Args:
            partner_id (int): The partner ID to filter by.
            user_id (int): The agent ID to filter by.
            service_board_id (int): The service board ID to filter by.
            vendor_id (ObjectId): The vendor ID to filter by.

        Returns:
            List[str]: List of DID numbers.

        Raises:
            Exception: For unexpected errors during retrieval.
        """
        try:
            self.__logger.info(
                "Fetching DIDs for partner {}, agent {}, service_board {}, and vendor {}".format(
                    partner_id, user_id, service_board_id, vendor_id
                )
            )
            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(
                    {
                        "partner_id": partner_id,
                        "agent_id": user_id,
                        "service_board_id": service_board_id,
                        "vendor_id": vendor_id,
                        "did_type": DIDType.NORMAL.value,
                        "is_active": True,
                    }
                )
                dids = [doc["did_number"] async for doc in cursor]
                self.__logger.info(
                    "Fetched DIDs get did by partner agent service board and vendor: {}".format(
                        dids
                    )
                )
                return dids
        except Exception as e:
            self.__logger.error(
                "Failed to fetch DIDs for partner {}, agent {}, service_board {}: {}".format(
                    partner_id, user_id, service_board_id, str(e)
                )
            )
            raise

    async def get_did_by_number(
        self, call_to_number: str, partner_id: Optional[int] = None
    ) -> Optional[Dict]:
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
            self.__logger.debug("Searching DID for number: {}".format(call_to_number))
            # Normalize: try last 10 digits and with 91 prefix
            candidates: str = normalize_phone_number(call_to_number, with_plus=False)

            self.__logger.info(
                "Normalized candidates for DID search: {}".format(candidates)
            )

            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                query: dict = {"did_number": candidates, "is_active": True}
                if partner_id is not None:
                    query["partner_id"] = partner_id
                did_record: Optional[Dict[str, Any]] = await collection.find_one(query)

            if did_record:
                self.__logger.debug("Found DID record: {}".format(did_record))
                return did_record
            self.__logger.info("No DID record found for given number")
            return None
        except Exception as e:
            self.__logger.error("Error finding DID by number: {}".format(str(e)))
            raise

    async def get_dids_by_service_board(
        self, service_board_id: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch all DID records for a given service board ID.
        """
        try:
            self.__logger.info(
                "Fetching DIDs for service_board_id={}".format(service_board_id)
            )
            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(
                    {
                        "service_board_id": service_board_id,
                        "status": DIDStatus.MAPPED.value,
                        "did_type": DIDType.NORMAL.value,
                        "is_active": True,
                    }
                )
                records: List[Dict[str, Any]] = await cursor.to_list(length=None)
                return records
        except Exception as e:
            self.__logger.error(
                "Failed to fetch DIDs for service_board_id={}: {}".format(
                    service_board_id, str(e)
                )
            )
            raise

    async def get_details_by_dids(self, did_numbers: List[str]) -> List[Dict[str, Any]]:
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
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(
                    {"did_number": {"$in": did_numbers}}, {"did_number": 1}
                )
                records: List[Dict[str, Any]] = []
                async for doc in cursor:
                    records.append(
                        {
                            "did_number": doc["did_number"],
                            "instance_id": str(doc["_id"]),
                        }
                    )

            self.__logger.info("Fetched DID instance details: {}".format(records))
            return records

        except Exception as e:
            self.__logger.error(
                "Failed to fetch instance_id for statusDIDs {}: {}".format(
                    did_numbers, str(e)
                )
            )
            raise

    async def unassign_did_to_partner(self, did_number: str, partner_id: int) -> int:
        """
        Unassigns a DID from a partner by setting partner_id to 0.

        :param did_number: The DID number to unassign.
        """
        try:
            self.__logger.info(
                "Unassigning DiD {} to partner_id: {}".format(did_number, partner_id)
            )

            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                result: UpdateResult = await collection.update_one(
                    {"did_number": did_number},
                    {
                        "$set": {
                            "partner_id": 0,
                            "agent_id": None,
                            "service_board_id": None,
                        }
                    },
                )

            if result.modified_count > 0:
                self.__logger.info("Successfully unassigned DID {}".format(did_number))
            else:
                self.__logger.warning(
                    "No records updated for DID {}".format(did_number)
                )

            return result.modified_count > 0

        except Exception as e:
            self.__logger.error(
                "Failed to fetch instance_id for DIDs {}: {}".format(did_number, str(e))
            )
            raise

    async def update_did_status(
        self, did_number: str, partner_id: int, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
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
            self.__logger.debug(
                "Updating DID {} for partner {} with data {}".format(
                    did_number, partner_id, update_data
                )
            )
            # Read-check-then-write — see update_did_attendance's comment on
            # why this needs connect()'s transaction rather than collection().
            async with self.__db_manager.connect() as db:
                collection = db[
                    PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
                ]
                candidates: List[str] = normalize_phone_number(
                    did_number, with_plus=False
                )

                self.__logger.info(
                    "Normalized candidates for DID search: {}".format(candidates)
                )
                query: Dict[str, Any] = {
                    "did_number": candidates,
                    "partner_id": partner_id,
                }
                self.__logger.debug("Executing initial query: {}".format(query))
                existing_did: Optional[Dict[str, Any]] = await collection.find_one(
                    query
                )
                if not existing_did:
                    self.__logger.warning(
                        "DID {} not available (partner_id != 0)".format(did_number)
                    )
                    return None

                update_query = {"did_number": did_number}
                update_data["partner_id"] = partner_id
                update_data["status_changed_at"] = DateTimeUtil().get_current_time()
                self.__logger.debug(
                    "Executing update query: {} with data {}".format(
                        update_query, update_data
                    )
                )
                result: Optional[Dict[str, Any]] = await collection.find_one_and_update(
                    update_query, {"$set": update_data}, return_document=True
                )
                if result:
                    self.__logger.info(
                        "Successfully updated DID {} to partner {}".format(
                            did_number, partner_id
                        )
                    )
                    return result
                self.__logger.warning(
                    "Failed to update DID {} to partner {}".format(
                        did_number, partner_id
                    )
                )
                return None
        except Exception as e:
            self.__logger.error(
                "Unexpected error updating DID {}: {}".format(did_number, str(e))
            )
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
            self.__logger.debug(
                "Incrementing spam_count for DID: {}".format(did_number)
            )

            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                result: UpdateResult = await collection.update_one(
                    {"did_number": did_number}, {"$inc": {"spam_count": 1}}
                )

            if result.modified_count > 0:
                self.__logger.info(
                    "Successfully incremented spam_count for DID {}".format(did_number)
                )
                return True
            else:
                self.__logger.warning(
                    "No document found to increment spam_count for DID {}".format(
                        did_number
                    )
                )
                return False

        except Exception as e:
            self.__logger.error(
                "Failed to increment spam_count for DID {}: {}".format(
                    did_number, str(e)
                )
            )
            raise

    async def get_dids_by_partner(
        self,
        partner_id: int,
        user_id: Optional[int] = None,
        service_board_id: Optional[int] = None,
        vendor_id: Optional[ObjectId] = None,
        vendor_config_id: Optional[ObjectId] = None,
        status: Optional[str] = None,
        did_number: Optional[str] = None,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all DIDs for a specific partner, agent, service board, vendor, and status.
        """

        try:
            self.__logger.info(
                "Fetching DIDs for partner {}, agent {}, service_board {}, vendor {}, vendor_config_id {}, status {}, did_number={}, offset {}, limit {}".format(
                    partner_id,
                    user_id,
                    service_board_id,
                    vendor_id,
                    vendor_config_id,
                    status,
                    did_number,
                    offset,
                    limit,
                )
            )

            # Base query
            query: Dict[str, Any] = {
                "partner_id": partner_id,
                "is_active": True,
                "did_type": DIDType.NORMAL.value,
            }

            # Optional filters mapping
            optional_filters: Dict[str, Any] = {
                "agent_id": user_id,
                "service_board_id": service_board_id,
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

            self.__logger.debug("Executing query: {}".format(query))

            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                total: int = await collection.count_documents(query)

                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(
                    query
                ).sort("status_changed_at", -1)

                if offset is not None and limit is not None:
                    skip: int = (offset - 1) * limit
                    cursor: AsyncGenerator[Dict[str, Any], None] = cursor.skip(
                        skip
                    ).limit(limit)

                docs: List[Dict[str, Any]] = [doc async for doc in cursor]

            self.__logger.info(
                "Fetched DIDs count={} for partner={} agent={} service_board={}".format(
                    len(docs), partner_id, user_id, service_board_id
                )
            )

            return docs, total
        except Exception as e:
            self.__logger.error(
                "Failed to fetch DIDs partner={} agent={} service_board={} error={}".format(
                    partner_id,
                    user_id,
                    service_board_id,
                    str(e),
                )
            )
            raise

    async def get_ai_agent_dids(
        self,
        partner_id: int,
        agent_bot_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all ai_agent DIDs assigned to a given agent_bot_id.
        """
        try:
            self.__logger.info(
                "Fetching ai_agent DIDs for partner_id={} agent_bot_id={}".format(
                    partner_id, agent_bot_id
                )
            )
            query: Dict[str, Any] = {
                "partner_id": partner_id,
                "did_type": DIDType.AI_AGENT.value,
                "is_active": True,
            }
            if agent_bot_id is not None:
                query["agent_bot_id"] = agent_bot_id

            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(query)
                return [doc async for doc in cursor]
        except Exception as e:
            self.__logger.error(
                "Failed to fetch ai_agent DIDs for agent_bot_id={}: {}".format(
                    agent_bot_id, str(e)
                )
            )
            raise

    async def get_mapped_ai_agent_dids(
        self,
        partner_id: int,
        agent_bot_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Fetch ai_agent DIDs with status=MAPPED for a given agent_bot_id.
        """
        try:
            self.__logger.info(
                "Fetching mapped ai_agent DIDs for partner_id={} agent_bot_id={}".format(
                    partner_id, agent_bot_id
                )
            )
            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(
                    {
                        "partner_id": partner_id,
                        "did_type": DIDType.AI_AGENT.value,
                        "agent_bot_id": agent_bot_id,
                        "status": DIDStatus.MAPPED.value,
                        "is_active": True,
                    }
                )
                return [doc async for doc in cursor]
        except Exception as e:
            self.__logger.error(
                "Failed to fetch mapped ai_agent DIDs for agent_bot_id={}: {}".format(
                    agent_bot_id, str(e)
                )
            )
            raise

    async def get_available_ai_agent_dids(
        self,
        partner_id: int,
    ) -> List[str]:
        """
        Fetch all available ai_agent DIDs for a specific partner.
        A DID is considered free if partner_id == 0 and status == AVAILABLE.
        """
        try:
            self.__logger.info(
                "Fetching available ai_agent DIDs for partner_id={}".format(partner_id)
            )
            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                query: Dict[str, Any] = {
                    "partner_id": partner_id,
                    "status": DIDStatus.AVAILABLE.value,
                    "did_type": DIDType.AI_AGENT.value,
                    "is_active": True,
                }

                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(query)
                dids: List[str] = [doc["did_number"] async for doc in cursor]
                self.__logger.info("Fetched available ai_agent DIDs: {}".format(dids))
                return dids
        except Exception as e:
            self.__logger.error(
                "Failed to fetch available ai_agent DIDs: {}".format(str(e))
            )
            raise

    async def update_did_values(
        self,
        did_number: str,
        partner_id: Optional[int] = None,
        update_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
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
                collection = db[
                    PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
                ]

                # === Build Find Query ===
                find_query: Dict[str, Any] = {"did_number": did_number}

                # Priority 1: Use partner_id passed as parameter
                if partner_id is not None:
                    find_query["partner_id"] = partner_id

                # Priority 2: Default for new assignments (available DIDs)
                else:
                    find_query["partner_id"] = 0

                self.__logger.debug(f"Find query built: {find_query}")

                existing_did = await collection.find_one(find_query)
                if not existing_did:
                    self.__logger.warning(
                        f"DID {did_number} not found or not available with query: {find_query}"
                    )
                    return None

                # === Prepare Update Payload ===
                update_payload = update_data.copy()
                update_payload["status_changed_at"] = DateTimeUtil().get_current_time()

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

    async def get_display_names_by_dids(
        self, did_numbers: List[str]
    ) -> Dict[str, str]:
        """
        Fetch display_name for a list of DID numbers, keyed by the *normalized*
        did_number (no leading '+'), since phone_number_management stores
        did_number without '+' while CDR documents may store it with '+'.
        Callers must look up using the same normalized form.
        """
        if not did_numbers:
            return {}
        try:
            normalized_numbers = [
                normalize_phone_number(d, with_plus=False) for d in did_numbers
            ]
            self.__logger.info(
                "Fetching display names for normalized DIDs: {}".format(
                    normalized_numbers
                )
            )
            async with self.__db_manager.collection(
                PhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
            ) as collection:
                cursor: AsyncGenerator[Dict[str, Any], None] = collection.find(
                    {"did_number": {"$in": normalized_numbers}},
                    {"did_number": 1, "display_name": 1},
                )
                display_name_map: Dict[str, str] = {}
                async for doc in cursor:
                    display_name_map[doc["did_number"]] = doc.get("display_name") or ""

            self.__logger.info(
                "Fetched display name map for {} DIDs".format(len(display_name_map))
            )
            return display_name_map
        except Exception as e:
            self.__logger.error(
                "Failed to fetch display names for DIDs {}: {}".format(
                    did_numbers, str(e)
                )
            )
            raise
