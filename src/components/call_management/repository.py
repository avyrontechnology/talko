import re
from typing import Any, Dict, Optional

from bson import ObjectId
from pymongo.results import InsertOneResult, UpdateResult

from src.components.cdr.models import CDR
from src.components.partner_config.models import PartnerConfigModel
from src.components.vendor.models import VendorModel
from src.components.vendor_config.models import VendorConfigModel
from src.core.doc_db import DocDatabaseSessionManager
from src.loggers.holler_service_logger import HollerServiceLogger


class CallRepository:
    """
    Repository for managing call-related data operations in the database.
    """

    def __init__(
        self, db_manager: DocDatabaseSessionManager, logger: HollerServiceLogger
    ):
        """
        Initialize the repository.

        Args:
            db_manager: MongoDB session manager.
            logger: Logger for capturing logs.
        """
        self.__db_manager: DocDatabaseSessionManager = db_manager
        self.__logger: HollerServiceLogger = logger

    async def get_vendor_config(
        self, vendor_id: str, vendor_config_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve vendor config by vendor_id and vendor config id, including vendor_type.

        Args:
            vendor_id: Vendor ID as a string.

        Returns:
            dict or None: Vendor config with vendor_type.
        """
        try:
            async with self.__db_manager.collection(
                VendorConfigModel.CollectionName.VENDOR_CONFIG
            ) as collection:
                self.__logger.debug("Get vendor config: {}".format(vendor_config_id))
                vendor_config: Optional[Dict[str, Any]] = await collection.find_one(
                    {"_id": ObjectId(vendor_config_id)}
                )
                if not vendor_config:
                    self.__logger.error(
                        "Vendor config for vendor_config_id {} not found".format(
                            vendor_config_id
                        )
                    )
                    return None

                # Fetch vendor_type from vendors collection
                async with self.__db_manager.collection(
                    VendorModel.CollectionName.VENDOR
                ) as vendor_collection:
                    vendor: Optional[Dict[str, Any]] = await vendor_collection.find_one(
                        {"_id": ObjectId(vendor_id)}
                    )
                    if vendor and isinstance(vendor, dict) and "vendor_type" in vendor:
                        vendor_config["vendor_type"] = vendor["vendor_type"]
                    else:
                        self.__logger.warning(
                            f"Vendor type not found for vendor_id {vendor_id}, defaulting to None"
                        )
                        vendor_config["vendor_type"] = None

                return vendor_config
        except Exception as e:
            self.__logger.error(
                "Failed to retrieve vendor config for vendor_id {}: {}".format(
                    vendor_id, str(e)
                )
            )
            raise

    async def get_partner_config_by_partner_id(
        self, partner_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve partner config by partner_id.

        Args:
            partner_id: Partner ID.

        Returns:
            dict or None: Partner configuration.
        """
        try:
            async with self.__db_manager.collection(
                PartnerConfigModel.CollectionName.PARTNER_CONFIG
            ) as collection:
                return await collection.find_one({"partner_id": partner_id})
        except Exception as e:
            self.__logger.error(
                "Failed to retrieve partner config for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise

    async def update_partner_config_did_indices(
        self, partner_id: int, did_indices: Dict[str | int, int], updated_at: int
    ) -> Optional[Dict[str, Any]]:
        """
        Update DID indices in partner config.

        Args:
            partner_id: Partner ID.
            did_indices: New DID indices dictionary.
            updated_at: Timestamp for update.

        Returns:
            dict: Updated partner config document.

        Raises:
            Exception: For unexpected database errors.
        """
        try:
            async with self.__db_manager.collection(
                PartnerConfigModel.CollectionName.PARTNER_CONFIG
            ) as collection:
                # Convert integer keys to strings
                did_indices_converted = {str(k): v for k, v in did_indices.items()}
                result: Optional[Dict[str, Any]] = await collection.find_one_and_update(
                    {"partner_id": partner_id},
                    {
                        "$set": {
                            "did_indices": did_indices_converted,
                            "updated_at": updated_at,
                        }
                    },
                    return_document=True,
                )
                if result:
                    self.__logger.info(
                        "Updated partner config did_indices for partner_id {}".format(
                            partner_id
                        )
                    )
                else:
                    self.__logger.error(
                        "No partner config found to update did_indices for partner_id {}".format(
                            partner_id
                        )
                    )
                return result
        except Exception as e:
            self.__logger.error(
                "Failed to update partner config did_indices for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise

    async def update_partner_config_inbound_round_robin_index(
        self, partner_id: int, inbound_round_robin_index: int, updated_at: int
    ) -> Optional[Dict[str, Any]]:
        """
        Update the inbound round-robin agent ringing cursor in partner config.

        Args:
            partner_id: Partner ID.
            inbound_round_robin_index: New cursor value.
            updated_at: Timestamp for update.

        Returns:
            dict: Updated partner config document.

        Raises:
            Exception: For unexpected database errors.
        """
        try:
            async with self.__db_manager.collection(
                PartnerConfigModel.CollectionName.PARTNER_CONFIG
            ) as collection:
                result: Optional[Dict[str, Any]] = await collection.find_one_and_update(
                    {"partner_id": partner_id},
                    {
                        "$set": {
                            "inbound_round_robin_index": inbound_round_robin_index,
                            "updated_at": updated_at,
                        }
                    },
                    return_document=True,
                )
                if result:
                    self.__logger.info(
                        "Updated partner config inbound_round_robin_index for partner_id {}".format(
                            partner_id
                        )
                    )
                else:
                    self.__logger.error(
                        "No partner config found to update inbound_round_robin_index for partner_id {}".format(
                            partner_id
                        )
                    )
                return result
        except Exception as e:
            self.__logger.error(
                "Failed to update partner config inbound_round_robin_index for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise

    async def insert_cdr(self, cdr_dict: dict) -> str:
        """
        Insert a new CDR record.

        Args:
            cdr_dict: CDR data to insert.

        Returns:
            str: Inserted CDR ID.
        """
        try:
            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                result: InsertOneResult = await collection.insert_one(cdr_dict)
                self.__logger.info(
                    "Inserted CDR with ID: {}".format(result.inserted_id)
                )
                return str(result.inserted_id)
        except Exception as e:
            self.__logger.error("Failed to insert CDR: {}".format(str(e)))
            raise

    async def get_cdr_by_call_id_or_uuid(
        self, call_id: Optional[str], uuid_value: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Get a CDR by call_id (or uuid if supported later).

        Args:
            call_id: Call identifier.

        Returns:
            dict or None: CDR record.
        """
        try:
            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                query: Dict[str, Any] = {}
                if uuid_value and uuid_value != "None":
                    query = {"call_uuid": uuid_value}
                if call_id and call_id != "None":
                    query = {"call_id": call_id}
                if not query:
                    return None

                return await collection.find_one(query)
        except Exception as e:
            self.__logger.error("Failed to get CDR by call id: {}".format(str(e)))
            raise

    async def update_cdr(self, cdr_id: str, updates: dict) -> bool:
        """
        Update a CDR by its ObjectId.

        Args:
            cdr_id: CDR ID.
            updates: Fields to update.

        Returns:
            bool: True if modified, False otherwise.
        """
        try:
            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                result: UpdateResult = await collection.update_one(
                    {"_id": ObjectId(cdr_id)}, {"$set": updates}
                )
                return result.modified_count > 0
        except Exception as e:
            self.__logger.error("Failed to update CDR: {}".format(str(e)))
            raise

    async def find_callback_by_parent_uuid(
        self, call_uuid: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find an outbound auto-callback CDR placed for a missed inbound call.

        Used as the exactly-once guard for the missed-call callback flow:
        the Celery ETA task, the beat sweeper, and manual re-dispatches all
        converge here — whichever execution places the callback first wins,
        every later one sees this row and skips instead of double-dialing
        the customer.
        """
        try:
            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                return await collection.find_one(
                    {"callback_for_call_uuid": call_uuid}
                )
        except Exception as e:
            self.__logger.error(
                "Failed to find callback for parent uuid {}: {}".format(
                    call_uuid, str(e)
                )
            )
            raise

    async def find_missed_inbounds_needing_callback(
        self, older_than_ms: int, newer_than_ms: int, limit: int = 50
    ) -> list:
        """
        Find missed inbound CDRs in the (newer_than_ms, older_than_ms) window
        that have no auto-callback yet — the beat sweeper's candidate set.

        Window semantics (all ms epoch), gated on immutable created_at
        (call start, seconds before the miss) — deliberately NOT updated_at:
        the 5-min CDR reconciler rewrites updated_at on every pass, which
        would keep refreshing a row's age and let it dodge the sweeper
        forever (observed on QA: updated_at marched forward every 5 min,
        age never exceeded the gate).
        - older_than_ms: candidate must be this old (ETA 100s + worker
          lateness margin) so the fast-path ETA task gets first chance and
          the sweeper never races it.
        - newer_than_ms: candidate must be this recent, so permanently
          un-callbackable rows (AI DID, disabled partner, ...) age out
          instead of being re-dispatched forever.
        Oldest first so the most overdue callbacks are healed first.
        """
        try:
            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                cursor = (
                    collection.find(
                        {
                            "action": "inbound",
                            "call_status": "missed",
                            "created_at": {
                                "$lt": older_than_ms,
                                "$gt": newer_than_ms,
                            },
                            "callback_for_call_uuid": None,
                        },
                        {"call_uuid": 1},
                    )
                    .sort("created_at", 1)
                    .limit(limit)
                )
                return await cursor.to_list(length=limit)
        except Exception as e:
            self.__logger.error(
                "Failed to find missed inbounds needing callback: {}".format(str(e))
            )
            raise

    def normalize_phone_number(self, number: str) -> str:
        """
        Normalize Indian phone numbers to format: 91XXXXXXXXXX (no +, no leading 0)
        """
        if not number:
            return ""

        # Remove all non-digits
        digits = re.sub(r"\D", "", number)

        # Handle common Indian formats
        if digits.startswith("91") and len(digits) == 12:
            return digits  # Already good: 918448326161
        elif len(digits) == 11 and digits.startswith("0"):
            return "91" + digits[1:]  # 08448326161 → 918448326161
        elif len(digits) == 10:
            return "91" + digits  # 8448326161 → 918448326161
        elif digits.startswith("+91") and len(digits) == 13:
            return digits[1:]  # +918448326161 → 918448326161
        else:
            return digits  # fallback

    async def find_cdr_by_numbers(
        self, caller_id_number: str, call_to_number: str
    ) -> Optional[Dict]:
        try:
            self.__logger.debug(
                "Searching CDR for numbers: {}, {}".format(
                    caller_id_number, call_to_number
                )
            )

            # Normalize both numbers
            normalized_caller = self.normalize_phone_number(caller_id_number)
            normalized_did = self.normalize_phone_number(call_to_number)

            if not normalized_caller or not normalized_did:
                self.__logger.debug("Invalid phone number after normalization")
                return None

            # Search using multiple possible formats for 'customer' field
            possible_customer_formats = [
                normalized_caller,  # 918448326161
                normalized_caller[2:],  # 8448326161 (without 91)
                "0" + normalized_caller[2:],  # 08448326161
                "+" + normalized_caller,  # +918448326161
            ]

            query = {
                "customer": {"$in": possible_customer_formats},
                "did_number": normalized_did,  # or also make this flexible if needed
            }

            async with self.__db_manager.collection(
                CDR.CollectionName.CDR
            ) as collection:
                cursor = collection.find(query).sort("created_at", -1).limit(1)
                cdr_list = await cursor.to_list(length=1)

            if cdr_list:
                cdr = cdr_list[0]
                self.__logger.debug(f"Found latest CDR record: {cdr}")
                return cdr

            self.__logger.debug("No CDR found for given numbers")
            return None

        except Exception as e:
            self.__logger.error(f"Error finding CDR by numbers: {str(e)}")
            raise
