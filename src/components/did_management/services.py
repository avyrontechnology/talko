from collections import defaultdict
from typing import Any, Dict, List, Optional, Union

from bson import ObjectId

from src.components.common.responses import BadRequestResponse
from src.components.did_management.constants import (
    ADMIN_ACTION_MARK_SPAMMED,
    DIDStatus,
    DIDType,
)
from src.components.did_management.dto import Contract
from src.components.did_management.helpers import DidStatusUpdateHelper
from src.components.did_management.messages import (
    DID_ASSIGNMENT_SUCCESS,
    DID_UNASSIGNMENT_SUCCESS,
    MISSING_AGENT_MAPPING_DIDS,
    MISSING_DID_ASSIGNMENT_CRITERIA,
    MISSING_ROUND_ROBIN_DIDS,
    MISSING_SERVICE_BOARD_MAPPING_DIDS,
    PARTNER_CONFIG_NOT_FOUND,
)
from src.components.did_management.models import DidHistoryModel, PhoneNumberManagement
from src.components.did_management.repositories import DidRepository
from src.components.did_management.validator import DidValidator
from src.components.partner_config.repository import PartnerConfigRepository
from src.exceptions import ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.datetime_util import DateTimeUtil


class DidManagementService:
    """
    Service class for managing DID assignments, default attendances, and history.
    """

    def __init__(
        self,
        did_repository: DidRepository,
        logger: HollerServiceLogger,
        datetime_util: DateTimeUtil,
        validator: DidValidator,
        partner_config_repository: PartnerConfigRepository,
    ):
        self.__did_repository: DidRepository = did_repository
        self.__logger: HollerServiceLogger = logger
        self.__datetime_util: DateTimeUtil = datetime_util
        self.__validator: DidValidator = validator
        self.__partner_config_repository: PartnerConfigRepository = (
            partner_config_repository
        )

    async def assign_did(
        self,
        service_board_id: int,
        did_number: str,
        partner_id: int,
        vendor_id: str,
        vendor_config_id: Optional[str] = None,
        agent_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Assign a DID to a service board, partner, and optionally an agent.
        """
        self.__logger.info(
            "Starting assign_did with did_number: {}, partner_id: {}, vendor_id: {}, service_board_id: {}, agent_id: {}".format(
                did_number, partner_id, vendor_id, service_board_id, agent_id
            )
        )
        try:
            current_timestamp: int = self.__datetime_util.get_current_time()
            vendor_id_obj: ObjectId = ObjectId(vendor_id)
            vendor_config_obj: Optional[ObjectId] = (
                ObjectId(vendor_config_id) if vendor_config_id else None
            )
            self.__logger.debug(
                "Converted vendor_id to ObjectId: {}, vendor_config_id to ObjectId: {}".format(
                    vendor_id_obj, vendor_config_obj
                )
            )
            did_data: Dict[str, Any] = PhoneNumberManagement(
                service_board_id=service_board_id,
                did_number=did_number,
                partner_id=partner_id,
                vendor_id=vendor_id_obj,
                vendor_config_id=vendor_config_obj,
                agent_id=agent_id,
                assign_date=current_timestamp,
                mapped_date=current_timestamp if agent_id else None,
                did_type=DIDType.NORMAL.value,
                agent_bot_id=0,
            ).model_dump()
            self.__logger.debug("Created did_data: {}".format(did_data))

            existing_did: Optional[Dict[str, Any]] = (
                await self.__did_repository.find_did_attendance(did_number, partner_id)
            )
            if existing_did and existing_did.get("vendor_id") == vendor_id_obj:
                self.__logger.info(
                    "DID {} already assigned for vendor {} and partner {}".format(
                        did_number, vendor_id, partner_id
                    )
                )
                raise ValueError("DID already exists")

            await self.__validator.validate_did_assignment(did_data)
            self.__logger.debug("Validated did_data successfully")
            did_record: Dict[str, Any] = (
                await self.__did_repository.insert_did_default_attendance(did_data)
            )
            self.__logger.debug("Inserted DID record: {}".format(did_record))

            history_data: Dict[str, Any] = DidHistoryModel(
                did_number=did_number,
                partner_id=partner_id,
                vendor_id=vendor_id_obj,
                agent_id=agent_id,
                assign_date=current_timestamp,
                service_board_id=service_board_id,
                vendor_config_id=vendor_config_obj,
            ).model_dump()
            self.__logger.debug("Created history_data: {}".format(history_data))
            await self.__did_repository.insert_did_history(history_data)
            self.__logger.debug("Inserted DID history")

            self.__logger.info("DID {} assigned successfully".format(did_number))
            return did_record
        except Exception as e:
            self.__logger.error(
                "Failed to assign DID {}: {}".format(did_number, str(e))
            )
            raise

    async def unassign_did(self, did_number: str, partner_id: int) -> Dict[str, Any]:
        """
        Unassign a DID by resetting it to available state instead of deleting.
        """
        self.__logger.info(f"Unassigning DID {did_number} from partner {partner_id}")
        try:
            current_timestamp: int = self.__datetime_util.get_current_time()

            # Update main attendance record (Don't delete)
            update_data = {
                "partner_id": 0,
                "agent_bot_id": 0,
                "agent_id": 0,
                "service_board_id": 0,
                "status": DIDStatus.AVAILABLE.value,
                "status_changed_at": current_timestamp,
            }

            updated_did = await self.__did_repository.update_did_values(
                did_number=did_number,
                partner_id=partner_id,  # for verification
                update_data=update_data,
            )

            if not updated_did:
                raise ResourceNotFound(
                    f"DID {did_number} not found for partner {partner_id}"
                )

            # Update History
            history_update: Dict[str, Any] = {
                "unassign_date": current_timestamp,
                "status": DIDStatus.AVAILABLE.value,
            }

            await self.__did_repository.update_did_history(
                did_number, partner_id, history_update
            )

            self.__logger.info(
                f"DID {did_number} unassigned successfully (reset to available)"
            )
            return updated_did

        except Exception as e:
            self.__logger.error(f"Failed to unassign DID {did_number}: {str(e)}")
            raise

    async def update_did_status(
        self,
        vendor_id: ObjectId,
        remove_from_available: List[str],
        add_to_available: List[str],
        remove_from_assigned: List[str],
        add_to_assigned: List[str],
        timestamp: int,
    ) -> None:
        """
        Update DID status by assigning/unassigning DIDs.
        """
        self.__logger.info(
            "Starting update_did_status for vendor_id: {}".format(vendor_id)
        )
        try:
            self.__logger.debug(
                "Update did status data - vendor_id: {}, remove_from_available: {}, add_to_available: {}, remove_from_assigned: {}, add_to_assigned: {}".format(
                    vendor_id,
                    remove_from_available,
                    add_to_available,
                    remove_from_assigned,
                    add_to_assigned,
                )
            )
            for did in add_to_assigned:
                self.__logger.debug(
                    "Assigning DID {} for vendor {}".format(did, vendor_id)
                )
                await self.assign_did(0, did, 1, str(vendor_id))
            for did in remove_from_assigned:
                self.__logger.debug(
                    "Unassigning DID {} for vendor {}".format(did, vendor_id)
                )
                await self.unassign_did(did, 1)
            self.__logger.info(
                "DID status updated successfully for vendor {}".format(vendor_id)
            )
        except Exception as e:
            self.__logger.error(
                "Failed to update DID status for vendor {}: {}".format(
                    vendor_id, str(e)
                )
            )
            raise

    async def get_assigned_dids(self, vendor_id: ObjectId) -> List[str]:
        """
        Retrieve list of assigned DIDs for a vendor.
        """
        self.__logger.info(
            "Starting get_assigned_dids for vendor_id: {}".format(vendor_id)
        )
        try:
            assigned_dids = await self.__did_repository.get_assigned_dids(vendor_id)
            self.__logger.debug("Retrieved assigned DIDs: {}".format(assigned_dids))
            self.__logger.info(
                "Successfully retrieved assigned DIDs for vendor {}".format(vendor_id)
            )
            return assigned_dids
        except Exception as e:
            self.__logger.error(
                "Failed to retrieve assigned DIDs for vendor {}: {}".format(
                    vendor_id, str(e)
                )
            )
            raise

    async def get_available_dids(
        self, vendor_id: ObjectId, vendor_config_id: Optional[ObjectId] = None
    ) -> List[str]:
        """
        Retrieve list of available DIDs for a vendor.
        """
        self.__logger.info(
            "Starting get_available_dids for vendor_id: {}, vendor_config_id: {}".format(
                vendor_id, vendor_config_id
            )
        )
        try:
            available_dids = await self.__did_repository.get_available_dids(
                vendor_id, vendor_config_id
            )
            self.__logger.debug("Retrieved available DIDs: {}".format(available_dids))
            self.__logger.info(
                "Successfully retrieved available DIDs for vendor {}".format(vendor_id)
            )
            return available_dids
        except Exception as e:
            self.__logger.error(
                "Failed to retrieve available DIDs for vendor {}: {}".format(
                    vendor_id, str(e)
                )
            )
            raise

    async def update_did(
        self,
        did_number: str,
        vendor_id: str,
        partner_id: int,
        service_board_id: Optional[int] = None,
        agent_id: Optional[int] = None,
        vendor_config_id: Optional[ObjectId] = None,
    ) -> Dict[str, Any]:
        """
        Update a DID's assignment details.
        """
        self.__logger.info(
            "Starting update_did for did_number: {}, partner_id: {}, vendor_id: {}, service_board_id: {}, agent_id: {}".format(
                did_number, partner_id, vendor_id, service_board_id, agent_id
            )
        )
        try:
            vendor_id_obj: ObjectId = ObjectId(vendor_id)
            self.__logger.debug(
                "Converted vendor_id to ObjectId: {}".format(vendor_id_obj)
            )
            current_timestamp: int = self.__datetime_util.get_current_time()
            self.__logger.debug("Current timestamp: {}".format(current_timestamp))

            existing_did: Optional[Dict[str, Any]] = (
                await self.__did_repository.find_did_by_did_number_and_vendor_id(
                    did_number, vendor_id_obj
                )
            )
            self.__logger.debug("Found existing DID: {}".format(existing_did))
            if not existing_did:
                self.__logger.error(
                    "DID {} not found for vendor {}".format(did_number, vendor_id)
                )
                raise ResourceNotFound(
                    "DID {} not found for the specified vendor".format(did_number)
                )

            update_data: Dict[str, Any] = {}
            if service_board_id is not None:
                update_data["service_board_id"] = service_board_id
            if agent_id is not None:
                update_data["agent_id"] = agent_id
                update_data["mapped_date"] = current_timestamp
            if existing_did.get("partner_id") in (None, 0):
                update_data["partner_id"] = partner_id
                update_data["assign_date"] = current_timestamp
            if update_data:
                update_data["updated_at"] = current_timestamp

            update_data["status"] = DIDStatus.MAPPED.value
            self.__logger.debug("Prepared update data: {}".format(update_data))

            if not update_data:
                self.__logger.info("No updates provided for DID {}".format(did_number))
                return existing_did

            updated_did: Dict[str, Any] = (
                await self.__did_repository.update_did_attendance(
                    did_number, partner_id, update_data
                )
            )
            self.__logger.debug("Updated DID: {}".format(updated_did))
            if not updated_did:
                self.__logger.error("Failed to update DID {}".format(did_number))
                raise ResourceNotFound("Failed to update DID {}".format(did_number))

            history_data: Dict[str, Any] = DidHistoryModel(
                did_number=did_number,
                partner_id=partner_id,
                vendor_id=vendor_id_obj,
                agent_id=agent_id or existing_did.get("agent_id"),
                assign_date=existing_did.get("assign_date") or current_timestamp,
                service_board_id=service_board_id
                or existing_did.get("service_board_id"),
                update_date=current_timestamp,
                vendor_config_id=vendor_config_id,
            ).model_dump()
            self.__logger.debug("Created history data: {}".format(history_data))
            await self.__did_repository.insert_did_history(history_data)
            self.__logger.debug("Inserted DID history for DID {}".format(did_number))

            self.__logger.info("DID {} updated successfully".format(did_number))
            return updated_did
        except Exception as e:
            self.__logger.error(
                "Failed to update DID {}: {}".format(did_number, str(e))
            )
            raise

    async def get_dids_by_partner_and_vendor(
        self, partner_id: int, vendor_id: str
    ) -> List[str]:
        """
        Retrieve DIDs for a specific partner and vendor.
        """
        self.__logger.info(
            "Starting get_dids_by_partner_and_vendor for partner_id: {}, vendor_id: {}".format(
                partner_id, vendor_id
            )
        )
        try:
            vendor_id_obj: ObjectId = ObjectId(vendor_id)
            self.__logger.debug(
                "Converted vendor_id to ObjectId: {}".format(vendor_id_obj)
            )
            dids = await self.__did_repository.get_dids_by_partner_and_vendor(
                partner_id, vendor_id_obj
            )
            self.__logger.debug("Retrieved DIDs: {}".format(dids))
            self.__logger.info(
                "Successfully retrieved DIDs for partner_id: {}, vendor_id: {}".format(
                    partner_id, vendor_id
                )
            )
            return dids
        except Exception as e:
            self.__logger.error(
                "Failed to retrieve DIDs for partner_id: {}, vendor_id: {}: {}".format(
                    partner_id, vendor_id, str(e)
                )
            )
            raise

    async def get_dids_by_partner_service_board_and_vendor(
        self,
        partner_id: int,
        service_board_id: int,
        vendor_id: str,
        vendor_config_id: Optional[str] = None,
    ) -> List[str]:
        """
        Retrieve DIDs for a specific partner, service board, and vendor.
        """
        self.__logger.info(
            "Starting get_dids_by_partner_service_board_and_vendor for partner_id: {}, "
            "service_board_id: {}, vendor_id: {}, vendor_config_id: {}".format(
                partner_id, service_board_id, vendor_id, vendor_config_id
            )
        )
        try:
            vendor_id_obj: ObjectId = ObjectId(vendor_id)

            # Convert vendor_config_id to ObjectId only if provided
            vendor_config_id_obj: Optional[ObjectId] = (
                ObjectId(vendor_config_id) if vendor_config_id else None
            )

            self.__logger.debug(
                "Converted vendor_id: {}, vendor_config_id: {}".format(
                    vendor_id_obj, vendor_config_id_obj
                )
            )

            dids = await self.__did_repository.get_dids_by_partner_service_board_and_vendor(
                partner_id, service_board_id, vendor_id_obj, vendor_config_id_obj
            )

            self.__logger.debug("Retrieved DIDs: {}".format(dids))
            return dids
        except Exception as e:
            self.__logger.error(
                "Failed to retrieve DIDs for partner_id: {}, service_board_id: {}, "
                "vendor_id: {}, vendor_config_id: {}: {}".format(
                    partner_id, service_board_id, vendor_id, vendor_config_id, str(e)
                )
            )
            raise

    async def get_dids_by_partner_agent_service_board_and_vendor(
        self, partner_id: int, user_id: int, service_board_id: int, vendor_id: str
    ) -> List[str]:
        """
        Retrieve DIDs for a specific partner, agent, service board, and vendor.
        """
        self.__logger.info(
            "Starting get_dids_by_partner_agent_service_board_and_vendor for partner_id: {}, user_id: {}, service_board_id: {}, vendor_id: {}".format(
                partner_id, user_id, service_board_id, vendor_id
            )
        )
        try:
            vendor_id_obj: ObjectId = ObjectId(vendor_id)
            self.__logger.debug(
                "Converted vendor_id to ObjectId: {}".format(vendor_id_obj)
            )
            dids = await self.__did_repository.get_dids_by_partner_agent_service_board_and_vendor(
                partner_id, user_id, service_board_id, vendor_id_obj
            )
            self.__logger.debug("Retrieved DIDs: {}".format(dids))
            self.__logger.info(
                "Successfully retrieved DIDs for partner_id: {}, user_id: {}, service_board_id: {}, vendor_id: {}".format(
                    partner_id, user_id, service_board_id, vendor_id
                )
            )
            return dids
        except Exception as e:
            self.__logger.error(
                "Failed to retrieve DIDs for partner_id: {}, user_id: {}, service_board_id: {}, vendor_id: {}: {}".format(
                    partner_id, user_id, service_board_id, vendor_id, str(e)
                )
            )
            raise

    async def get_dids_by_number(self, call_to_number: str) -> Optional[Dict]:
        """
        Retrieve DIDs by phone number.
        """
        self.__logger.info(
            "Starting get_dids_by_number for call_to_number: {}".format(call_to_number)
        )
        try:
            dids = await self.__did_repository.get_did_by_number(call_to_number)
            self.__logger.debug("Retrieved DIDs: {}".format(dids))
            self.__logger.info(
                "Successfully retrieved DIDs for call_to_number: {}".format(
                    call_to_number
                )
            )
            return dids
        except Exception as e:
            self.__logger.error(
                "Failed to retrieve DIDs for call_to_number {}: {}".format(
                    call_to_number, str(e)
                )
            )
            raise

    async def get_dids_by_service_board(
        self, service_board_id: int
    ) -> List[Dict[str, Any]]:
        """
        Service method to fetch all DIDs for a service board ID.
        Cleans ObjectId and converts to strings for safe schema parsing.
        """
        self.__logger.info(
            "Starting get_dids_by_service_board for service_board_id: {}".format(
                service_board_id
            )
        )
        try:
            records = await self.__did_repository.get_dids_by_service_board(
                service_board_id
            )
            self.__logger.debug("Retrieved records: {}".format(records))

            cleaned_records = []
            for doc in records:
                # Convert ObjectId fields → str
                if "_id" in doc and isinstance(doc["_id"], ObjectId):
                    doc["_id"] = str(doc["_id"])
                if "vendor_id" in doc and isinstance(doc["vendor_id"], ObjectId):
                    doc["vendor_id"] = str(doc["vendor_id"])
                if "partner_id" in doc and isinstance(doc["partner_id"], ObjectId):
                    doc["partner_id"] = int(doc["partner_id"])
                if "agent_id" in doc and isinstance(doc["agent_id"], ObjectId):
                    doc["agent_id"] = int(doc["agent_id"])

                # display_name may not exist on older docs, or may be stored as "" —
                # fall back to the DID number itself so the UI always has something to show.
                doc["display_name"] = (
                    doc.get("display_name") or doc.get("did_number") or ""
                )

                cleaned_records.append(doc)
            self.__logger.debug("Cleaned records: {}".format(cleaned_records))

            result = [Contract.DIDResponse(**doc) for doc in cleaned_records]
            self.__logger.info(
                "Successfully retrieved DIDs for service_board_id: {}".format(
                    service_board_id
                )
            )
            return result
        except Exception as e:
            self.__logger.error(
                "Error fetching DIDs for service board {}: {}".format(
                    service_board_id, str(e)
                )
            )
            raise

    def extract_series_key(self, did_number: str) -> str:
        """
        Extracts the DID series key based on the format and length of the given DID number.

        Rules:
        - If the DID number length is exactly 10: take the first two digits.
        - If the length is greater than 10:
            - If it starts with '+': skip '+' and the next two digits (country code),
              then take the following two digits.
            - Else (does not start with '+'): skip the first two digits and take the next two.
        - For shorter or invalid numbers, a fallback logic takes characters at positions [2:4].

        Args:
            did_number (str): The full DID number (e.g., '919876543210', '+919876543210', '9876543210').

        Returns:
            str: Extracted two-digit series key.

        Example:
            extract_series_key("9876543210")
            '98'
            extract_series_key("+919876543210")
            '87'
            extract_series_key("919876543210")
            '98'
        """
        if len(did_number) == 10:
            self.__logger.debug("Length of did_number : {} is 10".format(did_number))
            return did_number[:2]

        if len(did_number) > 10:
            if did_number.startswith("+"):
                self.__logger.debug(
                    "Length of did_number : {} is > 10 and it contains + in the starting".format(
                        did_number
                    )
                )
                return did_number[3:5]
            else:
                self.__logger.debug(
                    "Length of did_number : {} is > 10 and it does not contains + in the starting".format(
                        did_number
                    )
                )
                return did_number[2:4]

        # fallback
        self.__logger.debug("Returning to Fallback case in extract series key")
        return did_number[2:4]

    async def get_dids_available_for_assignment(
        self, partner_id: int
    ) -> List[Contract.DIDSeriesResponse]:
        """
        Fetch available DIDs for a partner based on vendor configuration,
        include instance_id, and group them by series.
        """

        try:
            self.__logger.info("Received partner_id: {}".format(partner_id))

            # Check if partner_config for received partner_id exists or not
            partner_config: Union[dict, None] = (
                await self.__partner_config_repository.find_partner_config_by_partner_id(
                    partner_id
                )
            )

            if not partner_config:
                self.__logger.error(
                    "No partner config found for partner_id: {}".format(partner_id)
                )
                raise ValueError(PARTNER_CONFIG_NOT_FOUND)

            self.__logger.info("PartnerConfig received: {}".format(partner_config))

            vendor_id: ObjectId = ObjectId(partner_config["vendor_id"])
            self.__logger.info(
                "Extracted vendor_id: {} from partner_config".format(vendor_id)
            )

            free_dids: List[str] = await self.get_available_dids(vendor_id)
            self.__logger.debug("Retrieved free DIDs: {}".format(free_dids))

            if not free_dids:
                self.__logger.info(
                    "No free DIDs found for vendor_id: {}".format(vendor_id)
                )
                return []

            phone_number_details: List[Dict[str, Any]] = (
                await self.__did_repository.get_details_by_dids(free_dids)
            )

            self.__logger.debug("Phone Number Details: {}".format(phone_number_details))

            instance_map: Dict[str, Optional[str]] = {
                entry["did_number"]: entry.get("instance_id")
                for entry in phone_number_details
            }

            self.__logger.debug("Instance Map: {}".format(instance_map))

            dids_with_details: List[Dict[str, Optional[str]]] = [
                {"number": did_number, "instance_id": instance_map.get(did_number)}
                for did_number in free_dids
            ]

            self.__logger.debug("DIDs With Details: {}".format(dids_with_details))

            grouped_dids: defaultdict[str, List[Dict[str, Optional[str]]]] = (
                defaultdict(list)
            )
            for did in dids_with_details:
                series_key: str = self.extract_series_key(did["number"])
                grouped_dids[series_key].append(did)

            self.__logger.debug("Grouped DIDs: {}".format(grouped_dids))

            response: List[Contract.DIDSeriesResponse] = [
                Contract.DIDSeriesResponse(
                    series=series,
                    dids=[
                        Contract.DIDDetail(
                            number=did["number"], instance_id=did.get("instance_id")
                        )
                        for did in did_list
                    ],
                    count=len(did_list),
                )
                for series, did_list in grouped_dids.items()
            ]

            self.__logger.info(
                "Successfully grouped and retrieved DIDs for partner_id: {}".format(
                    partner_id
                )
            )

            return response
        except ValueError as ve:
            self.__logger.error(
                "Error in retrieving free DIDs: PartnerConfig not found: {}".format(
                    str(ve)
                )
            )
            raise
        except Exception as e:
            self.__logger.error(
                "Error in retrieving free DIDs for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise

    async def assign_dids_available_for_assignment(
        self,
        partner_id: int,
        assign_did_data: Contract.AssignDIDToPartner,
    ) -> dict:
        """
        Assigns available DIDs to a partner based on provided configurations.
        """
        try:
            self.__logger.info(
                f"Assign DID Numbers(Service) => Received partner_id: {partner_id}, "
                f"assign_did_data: {assign_did_data}"
            )

            partner_config = await self.__partner_config_repository.find_partner_config_by_partner_id(
                partner_id
            )
            if not partner_config:
                self.__logger.error(
                    f"No partner config found for partner_id: {partner_id}"
                )
                raise ValueError(PARTNER_CONFIG_NOT_FOUND)

            self.__logger.info(f"PartnerConfig received: {partner_config}")
            vendor_id = ObjectId(partner_config["vendor_id"])
            vendor_config_id = ObjectId(partner_config.get("vendor_config_id"))
            self.__logger.info(f"Extracted vendor_id: {vendor_id} from partner_config")

            if partner_config.get("enable_round_robin"):
                await self._assign_round_robin_dids_to_partner(
                    vendor_id, partner_id, assign_did_data, vendor_config_id
                )
            elif partner_config.get("enable_service_board"):
                await self._assign_service_board_dids_to_partner(
                    vendor_id, partner_id, assign_did_data, vendor_config_id
                )
            elif partner_config.get("enable_agent_mapping"):
                await self._assign_agent_mapping_dids_to_partner(
                    vendor_id, partner_id, assign_did_data, vendor_config_id
                )
            else:
                return BadRequestResponse(
                    detail=MISSING_DID_ASSIGNMENT_CRITERIA.format(partner_id)
                )

            self.__logger.info(
                f"Successfully grouped and assigned DIDs for partner_id: {partner_id}"
            )
            return {"message": DID_ASSIGNMENT_SUCCESS}

        except ValueError as ve:
            self.__logger.error(f"PartnerConfig not found: {ve}")
            raise
        except Exception as e:
            self.__logger.error(
                f"Error in assigning DIDs for partner_id {partner_id}: {e}"
            )
            raise

    async def _assign_round_robin_dids_to_partner(
        self,
        vendor_id: ObjectId,
        partner_id: int,
        assign_did_data: Contract.AssignDIDToPartner,
        vendor_config_id: Optional[ObjectId] = None,
    ):
        round_robin_dids: List[str] = assign_did_data.dids_for_round_robin or []
        if not round_robin_dids:
            raise BadRequestResponse(detail=MISSING_ROUND_ROBIN_DIDS)
        for did in round_robin_dids:
            await self.update_did(
                did_number=did,
                vendor_id=str(vendor_id),
                partner_id=partner_id,
                service_board_id=None,
                agent_id=None,
                vendor_config_id=vendor_config_id,
            )

    async def _assign_service_board_dids_to_partner(
        self,
        vendor_id: ObjectId,
        partner_id: int,
        assign_did_data: Contract.AssignDIDToPartner,
        vendor_config_id: Optional[ObjectId] = None,
    ):
        service_board_dids: List[Contract.ServiceBoardDIDMapping] = (
            assign_did_data.dids_for_service_board or []
        )
        if not service_board_dids:
            raise BadRequestResponse(detail=MISSING_SERVICE_BOARD_MAPPING_DIDS)
        for mapping in service_board_dids:
            board_id = mapping.service_board_id
            for did in mapping.did_numbers:
                await self.update_did(
                    did_number=did,
                    vendor_id=str(vendor_id),
                    partner_id=partner_id,
                    service_board_id=int(board_id),
                    agent_id=None,
                    vendor_config_id=vendor_config_id,
                )

    async def _assign_agent_mapping_dids_to_partner(
        self,
        vendor_id: ObjectId,
        partner_id: int,
        assign_did_data: Contract.AssignDIDToPartner,
        vendor_config_id: Optional[ObjectId] = None,
    ):
        agent_mapping_dids: List[Dict[str, Any]] = (
            assign_did_data.dids_for_agent_mapping or []
        )
        if not agent_mapping_dids:
            raise BadRequestResponse(detail=MISSING_AGENT_MAPPING_DIDS)
        for mapping in agent_mapping_dids:
            await self.update_did(
                did_number=mapping.get("did_number"),
                vendor_id=str(vendor_id),
                partner_id=partner_id,
                service_board_id=None,
                agent_id=int(mapping.get("agent_id")),
                vendor_config_id=vendor_config_id,
            )

    async def unassign_dids_for_partner(
        self, partner_id: int, did_numbers: List[str]
    ) -> dict:
        """
        Unassigned DIDs by updating partner_id to 0 in phone number management collection
        """
        try:
            self.__logger.info(
                "Unassign DID Numbers(Service)=> Received partner_id: {}".format(
                    partner_id
                )
            )

            # Check if partner_config for received partner_id exists or not
            partner_config: Union[dict, None] = (
                await self.__partner_config_repository.find_partner_config_by_partner_id(
                    partner_id
                )
            )

            if not partner_config:
                self.__logger.error(
                    "Unssign DID Numbers(Service)=> No partner config found for partner_id: {}".format(
                        partner_id
                    )
                )
                raise ValueError(PARTNER_CONFIG_NOT_FOUND)

            self.__logger.info(
                "Unassign DID Numbers(Service)=> PartnerConfig received: {}".format(
                    partner_config
                )
            )

            for did in did_numbers:
                current_timestamp: int = self.__datetime_util.get_current_time()

                self.__logger.debug(
                    "Unassign DID Numbers(Service)=> Current timestamp: {}".format(
                        current_timestamp
                    )
                )

                result: bool = await self.__did_repository.unassign_did_to_partner(
                    did, partner_id
                )
                self.__logger.info(
                    "Unassign DID Numbers(Service)=> Record updated count for did {}: {}".format(
                        did, result
                    )
                )

                history_update: Dict[str, Any] = {"unassign_date": current_timestamp}
                self.__logger.debug(
                    "Unassign DID Numbers(Service)=> Prepared history update: {}".format(
                        history_update
                    )
                )

                updated_history: Dict[str, Any] = (
                    await self.__did_repository.update_did_history(
                        did, partner_id, history_update
                    )
                )
                self.__logger.debug(
                    "Unassign DID Numbers(Service)=> Updated DID history: {}".format(
                        updated_history
                    )
                )

            self.__logger.info(
                "Unassign DID Numbers(Service)=> Successfully unassigned DIDs for partner_id: {}".format(
                    partner_id
                )
            )

            return {"message": DID_UNASSIGNMENT_SUCCESS}

        except ValueError as ve:
            self.__logger.error(
                "Error in unassigning DIDs: PartnerConfig not found: {}".format(str(ve))
            )
            raise

        except Exception as e:
            self.__logger.error(
                "Error in unassigning DIDs for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise

    async def apply_did_status_update(
        self, partner_id: int, payload: Contract.AdminDIDAction
    ) -> dict:
        now = self.__datetime_util.get_current_time()
        self.__logger.info(
            "Applying action '{}' to DIDs: {}, partner_id: {}".format(
                payload.action, payload.did_numbers, partner_id
            )
        )

        results = [
            await self.__process_single_did(did_number, partner_id, payload, now)
            for did_number in payload.did_numbers
        ]
        return DidStatusUpdateHelper.build_summary(payload.did_numbers, results)

    async def __process_single_did(
        self,
        did_number: str,
        partner_id: int,
        payload: Contract.AdminDIDAction,
        now: int,
    ) -> dict:
        doc = await self.__did_repository.get_did_by_number(did_number, partner_id)
        current_status = (doc or {}).get("status", DIDStatus.AVAILABLE.value)

        error = DidStatusUpdateHelper.validate_did(
            doc, did_number, current_status, payload.action
        )
        if error:
            self.__logger.warning(
                "Validation failed for DID {}: {}".format(did_number, error)
            )
            return error

        try:
            handler = DidStatusUpdateHelper.ACTION_HANDLERS[payload.action]
            update_data = DidStatusUpdateHelper.prepare_update_data(
                handler, current_status, payload, now
            )

            updated = await self.__did_repository.update_did_status(
                did_number=did_number, update_data=update_data, partner_id=partner_id
            )
            self.__logger.info(
                "Action '{}' applied to DID {}: updated={}".format(
                    payload.action, did_number, bool(updated)
                )
            )

            if payload.action == ADMIN_ACTION_MARK_SPAMMED:
                await self.__did_repository.increment_spam_count(did_number)
                self.__logger.info(
                    "Incremented spam count for DID {}".format(did_number)
                )

            return {"did_number": did_number, "success": True, "status": "updated"}

        except ValueError as e:
            return DidStatusUpdateHelper.parse_value_error(did_number, e)

    async def list_dids(
        self,
        status: Optional[str] = None,
        partner_id: Optional[int] = None,
        service_board_id: Optional[int] = None,
        did_number: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        List DIDs for a partner with optional filters and pagination.

        Args:
            status: Optional status filter (case-insensitive aliases supported)
            partner_id: Required partner ID
            service_board_id: Optional service board filter
            page: Page number (1-based)
            limit: Items per page

        Returns:
            Dict with total, page, limit, and list of cleaned DID items

        Raises:
            ValueError: If partner_id missing or invalid status provided
        """
        self.__logger.info(
            "Listing DIDs with filters - status: {}, partner_id: {}, service_board_id: {}, page: {}, limit: {}".format(
                status, partner_id, service_board_id, page, limit
            )
        )
        if partner_id is None:
            self.__logger.error("partner_id is required for listing DIDs")
            raise ValueError("partner_id is required for listing DIDs")

        normalized_status: Optional[str] = None
        if status is not None:
            status_clean = status.lower().replace("_", "").replace(" ", "")

            status_mapping: Dict[str, str] = {
                "available": DIDStatus.AVAILABLE.value,
                "mapped": DIDStatus.MAPPED.value,
                "coolingperiod": DIDStatus.COOLING_PERIOD.value,
                "cooling": DIDStatus.COOLING_PERIOD.value,
                "cooldowncompleted": DIDStatus.COOLDOWN_COMPLETED.value,
                "cooldown": DIDStatus.COOLDOWN_COMPLETED.value,
                "cooling period": DIDStatus.COOLING_PERIOD.value,
                "cooldown completed": DIDStatus.COOLDOWN_COMPLETED.value,
            }

            normalized_status = status_mapping.get(status_clean)
            if normalized_status is None:
                raise ValueError(
                    "Invalid status filter: '{}'. ".format(status)
                    + "Supported values: available, mapped, cooling_period, cooldown_completed "
                    "(case-insensitive, underscores/spaces allowed)"
                )

        self.__logger.debug("Normalized status filter: {}".format(normalized_status))

        docs: List[Dict[str, Any]]
        total: int
        docs, total = await self.__did_repository.get_dids_by_partner(
            partner_id=partner_id,
            service_board_id=service_board_id,
            status=normalized_status,  # use normalized value
            did_number=did_number,
            offset=page,
            limit=limit,
        )

        self.__logger.debug(
            "Fetched DIDs from repository: total: {}, docs count: {}".format(
                total, len(docs)
            )
        )

        cleaned_dids: List[Dict[str, Any]] = []
        for doc in docs:
            clean: Dict[str, Any] = {
                k: str(v) if isinstance(v, ObjectId) else v for k, v in doc.items()
            }
            clean.pop("_id", None)

            cleaned_dids.append(
                {
                    "did_number": clean.get("did_number", ""),
                    "status": clean.get("status", DIDStatus.AVAILABLE.value),
                    "partner_id": clean.get("partner_id", 0),
                    "service_board_id": clean.get("service_board_id"),
                    "agent_id": clean.get("agent_id"),
                    "vendor_id": str(clean.get("vendor_id", "")),
                    "spam_count": clean.get("spam_count", 0),
                    "last_spam_detected_at": clean.get("last_spam_detected_at"),
                    "cooldown_until": clean.get("cooldown_until"),
                    "status_changed_at": clean.get("status_changed_at", 0),
                    "assign_date": clean.get("assign_date"),
                }
            )

        return {"total": total, "page": page, "limit": limit, "dids": cleaned_dids}

    async def assign_ai_agent_did(
        self,
        partner_id: int,
        agent_bot_id: int,
        did_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assign an available ai_agent DID to an AI bot."""
        try:
            self.__logger.info(
                "Assigning AI agent DID. partner_id={}, agent_bot_id={}".format(
                    partner_id, agent_bot_id
                )
            )

            existing: Optional[Dict[str, Any]] = None

            # Find or auto-pick available ai_agent DID
            if did_number:
                existing = await self.__did_repository.find_did_attendance(
                    did_number,
                    partner_id,
                )

                if (
                    not existing
                    or existing.get("did_type") != DIDType.AI_AGENT.value
                    or existing.get("status") != DIDStatus.AVAILABLE.value
                ):
                    raise ValueError("DID must be ai_agent type and AVAILABLE")

            updated_did: Dict[str, Any] = await self.__did_repository.update_did_values(
                did_number=did_number,
                partner_id=partner_id,
                update_data={
                    "partner_id": partner_id,
                    "agent_bot_id": agent_bot_id,
                    "status": DIDStatus.MAPPED.value,
                },
            )

            updated_did_record: Dict[str, Any] = {
                "did_number": updated_did.get("did_number"),
                "partner_id": updated_did.get("partner_id"),
                "agent_bot_id": updated_did.get("agent_bot_id"),
                "status": updated_did.get("status"),
            }

            return updated_did_record

        except Exception as e:
            error_message: str = str(e)

            self.__logger.error(
                "Error assigning AI agent DID for partner_id={} agent_bot_id={} error={}".format(
                    partner_id, agent_bot_id, error_message
                )
            )
            raise

    async def claim_did_for_campaign(
        self,
        partner_id: int,
        did_number: str,
        agent_bot_id: int,
    ) -> Dict[str, Any]:
        """
        Marks a partner-owned ai_agent DID as Mapped and binds it to the
        campaign's own agent_bot_id. Used when makun-ai adds a DID to a
        campaign's did_selection.

        agent_bot_id IS required here, unlike an earlier version of this
        method: PSTNBridgeService/CallManagementService._pre_create_session
        resolves which AI agent to bridge a call to purely from
        did_record.agent_bot_id (looked up by the DID the call was placed
        from), independent of context_data — an unbound DID makes AI-bridge
        session creation fail outright ("agent_id missing on DID ...").
        Binding it to the campaign's own agent_bot_id is safe for the
        "multiple DIDs per campaign" requirement: it's still many-DIDs-to-
        one-agent, never the reverse, and it's exactly what keeps the
        picker's own-agent-bound-DID exclusion correctly hiding this DID
        from other campaigns once claimed.

        Idempotent: re-claiming an already-Mapped DID bound to this same
        agent_bot_id is a no-op. Claiming a DID Mapped to a DIFFERENT
        agent_bot_id raises — something else (a concurrent claim, or a
        genuine assign-ai-agent call) already has it.
        """
        try:
            existing: Optional[Dict[str, Any]] = (
                await self.__did_repository.find_did_attendance(did_number, partner_id)
            )
            if not existing or existing.get("did_type") != DIDType.AI_AGENT.value:
                raise ResourceNotFound(
                    "ai_agent DID {} not found for partner {}".format(
                        did_number, partner_id
                    )
                )

            current_status = existing.get("status")
            if current_status == DIDStatus.MAPPED.value:
                if existing.get("agent_bot_id") == agent_bot_id:
                    self.__logger.info(
                        "DID {} already Mapped to agent_bot_id={}, claim is a "
                        "no-op".format(did_number, agent_bot_id)
                    )
                    return {"did_number": did_number, "status": current_status}
                raise ValueError(
                    "DID {} is already Mapped to a different agent_bot_id={}"
                    .format(did_number, existing.get("agent_bot_id"))
                )

            if current_status != DIDStatus.AVAILABLE.value:
                raise ValueError(
                    "DID {} cannot be claimed from status {}".format(
                        did_number, current_status
                    )
                )

            updated_did: Dict[str, Any] = await self.__did_repository.update_did_values(
                did_number=did_number,
                partner_id=partner_id,
                update_data={
                    "status": DIDStatus.MAPPED.value,
                    "agent_bot_id": agent_bot_id,
                },
            )

            self.__logger.info(
                "DID {} claimed for campaign use (partner_id={}, agent_bot_id={})".format(
                    did_number, partner_id, agent_bot_id
                )
            )
            return {"did_number": did_number, "status": updated_did.get("status")}

        except Exception as e:
            self.__logger.error(
                "Error claiming DID {} for campaign use, partner_id={}: {}".format(
                    did_number, partner_id, str(e)
                )
            )
            raise

    async def release_campaign_did(
        self,
        partner_id: int,
        did_number: str,
        agent_bot_id: int,
    ) -> Dict[str, Any]:
        """
        Reverts a campaign-claimed DID back to Available and clears its
        agent_bot_id. Used when makun-ai removes a DID from a campaign's
        did_selection (deselected, or the campaign is deleted/stopped).

        Only acts when the DID is currently Mapped to exactly this
        agent_bot_id — if it's bound to a different agent_bot_id (reassigned
        elsewhere in the meantime) or already Available, this is a no-op
        rather than an error, and never resets partner_id (the partner still
        owns the DID; it's just unclaimed by this campaign).
        """
        try:
            existing: Optional[Dict[str, Any]] = (
                await self.__did_repository.find_did_attendance(did_number, partner_id)
            )
            if not existing:
                raise ResourceNotFound(
                    "DID {} not found for partner {}".format(did_number, partner_id)
                )

            current_status = existing.get("status")
            if (
                current_status != DIDStatus.MAPPED.value
                or existing.get("agent_bot_id") != agent_bot_id
            ):
                self.__logger.info(
                    "DID {} not Mapped to agent_bot_id={} (status={}, "
                    "actual agent_bot_id={}), release is a no-op".format(
                        did_number,
                        agent_bot_id,
                        current_status,
                        existing.get("agent_bot_id"),
                    )
                )
                return {"did_number": did_number, "status": current_status}

            updated_did: Dict[str, Any] = await self.__did_repository.update_did_values(
                did_number=did_number,
                partner_id=partner_id,
                update_data={
                    "status": DIDStatus.AVAILABLE.value,
                    "agent_bot_id": 0,
                },
            )

            self.__logger.info(
                "DID {} released from campaign use (partner_id={})".format(
                    did_number, partner_id
                )
            )
            return {"did_number": did_number, "status": updated_did.get("status")}

        except Exception as e:
            self.__logger.error(
                "Error releasing campaign DID {} for partner_id={}: {}".format(
                    did_number, partner_id, str(e)
                )
            )
            raise

    async def release_ai_agent_did(
        self,
        partner_id: int,
        agent_bot_id: int,
    ) -> List[str]:
        """Release all DIDs assigned to an AI agent bot."""
        try:
            self.__logger.info(
                "Releasing AI agent DIDs. partner_id={}, agent_bot_id={}".format(
                    partner_id, agent_bot_id
                )
            )

            assigned_dids: List[Dict[str, Any]] = (
                await self.__did_repository.get_mapped_ai_agent_dids(
                    partner_id=partner_id,
                    agent_bot_id=agent_bot_id,
                )
            )

            released_dids: List[str] = []

            for did_record in assigned_dids:
                did_number: str = did_record["did_number"]

                await self.unassign_did(
                    did_number,
                    partner_id,
                )

                released_dids.append(did_number)

            return released_dids

        except Exception as e:
            error_message: str = str(e)

            self.__logger.error(
                "Error releasing AI agent DIDs for partner_id={} agent_bot_id={} error={}".format(
                    partner_id, agent_bot_id, error_message
                )
            )
            raise

    async def get_ai_agent_dids(
        self,
        partner_id: int,
        agent_bot_id: int,
    ) -> List[str]:
        """Get all DIDs assigned to an AI agent bot."""
        try:
            dids: List[Dict[str, Any]] = await self.__did_repository.get_ai_agent_dids(
                partner_id=partner_id,
                agent_bot_id=agent_bot_id,
            )

            did_numbers: List[str] = [did["did_number"] for did in dids]

            return did_numbers

        except Exception as e:
            error_message: str = str(e)

            self.__logger.error(
                "Error fetching AI agent DIDs for partner_id={} agent_bot_id={} error={}".format(
                    partner_id, agent_bot_id, error_message
                )
            )
            raise

    async def list_ai_agent_dids(self, partner_id: int) -> List[Dict[str, Any]]:
        """List all ai_agent-type DIDs for a partner, assigned or not."""
        try:
            self.__logger.info(
                "Listing all ai_agent DIDs for partner_id={}".format(partner_id)
            )

            dids: List[Dict[str, Any]] = await self.__did_repository.get_ai_agent_dids(
                partner_id=partner_id
            )

            cleaned_dids: List[Dict[str, Any]] = [
                {
                    "did_number": did.get("did_number", ""),
                    "display_name": did.get("display_name"),
                    "status": did.get("status", DIDStatus.AVAILABLE.value),
                    "agent_bot_id": did.get("agent_bot_id") or 0,
                    "mapped_date": did.get("mapped_date"),
                    "vendor_id": str(did.get("vendor_id", "")),
                    "spam_count": did.get("spam_count", 0),
                    "cooldown_until": did.get("cooldown_until"),
                }
                for did in dids
            ]

            self.__logger.info(
                "Found {} ai_agent DIDs for partner_id={}".format(
                    len(cleaned_dids), partner_id
                )
            )

            return cleaned_dids

        except Exception as e:
            self.__logger.error(
                "Error listing ai_agent DIDs for partner_id={} error={}".format(
                    partner_id, str(e)
                )
            )
            raise

    async def get_available_ai_agent_dids(
        self,
        partner_id: int,
    ) -> List[str]:
        """Get available ai_agent DIDs for a partner."""
        try:
            dids: List[Dict[str, Any]] = (
                await self.__did_repository.get_available_ai_agent_dids(
                    partner_id=partner_id,
                )
            )

            did_numbers: List[str] = [did["did_number"] for did in dids]

            return did_numbers

        except Exception as e:
            error_message: str = str(e)

            self.__logger.error(
                "Error fetching available AI agent DIDs for partner_id={} error={}".format(
                    partner_id, error_message
                )
            )
            raise

    async def list_unassigned_available_ai_agent_dids(
        self,
        partner_id: int,
    ) -> List[str]:
        """
        Return ai_agent DIDs that are not mapped to any partner and are AVAILABLE.
        """
        try:
            self.__logger.info(
                "Listing unassigned available ai_agent DIDs for partner_id={}".format(
                    partner_id
                )
            )

            dids: List[str] = await self.__did_repository.get_available_ai_agent_dids(
                partner_id=partner_id
            )

            self.__logger.info(
                "Found {} unassigned available ai_agent DIDs for partner_id={}".format(
                    len(dids), partner_id
                )
            )

            return dids

        except Exception as e:
            self.__logger.error(
                "Error listing unassigned available ai_agent DIDs for partner_id={}".format(
                    partner_id
                )
            )
            raise
