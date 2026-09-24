from collections import defaultdict
from typing import Any

from bson import ObjectId

from src.components.did_management.constants import (
    ADMIN_ACTION_MARK_SPAMMED,
    TalkoDIDLayer,
    TalkoDIDStatus,
    TalkoDIDType,
)
from src.components.did_management.dto import TalkoContract
from src.components.did_management.helpers import TalkoDidStatusUpdateHelper
from src.components.did_management.messages import (
    DID_ALREADY_MAPPED,
    DID_ASSIGNMENT_SUCCESS,
    DID_UNASSIGNMENT_SUCCESS,
    EXTERNAL_DID_NOT_FOUND,
    INTERNAL_DID_NOT_FOUND,
    MISSING_AGENT_MAPPING_DIDS,
    MISSING_DID_ASSIGNMENT_CRITERIA,
    MISSING_ROUND_ROBIN_DIDS,
    MISSING_WORKSPACE_MAPPING_DIDS,
    PARTNER_CONFIG_NOT_FOUND,
)
from src.components.did_management.models import TalkoDidHistoryModel, TalkoPhoneNumberManagement
from src.components.did_management.repositories import TalkoDidRepository
from src.components.did_management.validator import TalkoDidValidator
from src.components.partner_config.repository import TalkoPartnerConfigRepository
from src.exceptions import TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil
from src.utils.mongo_utils import stringify_object_ids


class TalkoDidManagementService:
    """
    Service class for managing DID assignments, default attendances, and history.
    """

    def __init__(
        self,
        did_repository: TalkoDidRepository,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
        validator: TalkoDidValidator,
        partner_config_repository: TalkoPartnerConfigRepository,
    ):
        self.__did_repository: TalkoDidRepository = did_repository
        self.__logger: TalkoServiceLogger = logger
        self.__datetime_util: TalkoDateTimeUtil = datetime_util
        self.__validator: TalkoDidValidator = validator
        self.__partner_config_repository: TalkoPartnerConfigRepository = partner_config_repository

    async def assign_did(
        self,
        workspace_id: int,
        did_number: str,
        partner_id: int,
        vendor_id: str,
        vendor_config_id: str | None = None,
        agent_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Assign a DID to a workspace, partner, and optionally an agent.
        """
        self.__logger.info(
            f"Starting assign_did with did_number: {did_number}, partner_id: {partner_id}, vendor_id: {vendor_id}, workspace_id: {workspace_id}, agent_id: {agent_id}"
        )
        try:
            current_timestamp: int = self.__datetime_util.get_current_time()
            vendor_id_obj: ObjectId = ObjectId(vendor_id)
            vendor_config_obj: ObjectId | None = ObjectId(vendor_config_id) if vendor_config_id else None
            self.__logger.debug(
                f"Converted vendor_id to ObjectId: {vendor_id_obj}, vendor_config_id to ObjectId: {vendor_config_obj}"
            )
            did_data: dict[str, Any] = TalkoPhoneNumberManagement(
                workspace_id=workspace_id,
                did_number=did_number,
                partner_id=partner_id,
                vendor_id=vendor_id_obj,
                vendor_config_id=vendor_config_obj,
                agent_id=agent_id,
                assign_date=current_timestamp,
                mapped_date=current_timestamp if agent_id else None,
                did_type=TalkoDIDType.NORMAL.value,
                agent_bot_id=0,
                did_layer=TalkoDIDLayer.EXTERNAL.value,
            ).model_dump()
            self.__logger.debug(f"Created did_data: {did_data}")

            existing_did: dict[str, Any] | None = await self.__did_repository.find_did_attendance(
                did_number, partner_id
            )
            if existing_did and existing_did.get("vendor_id") == vendor_id_obj:
                self.__logger.info(f"DID {did_number} already assigned for vendor {vendor_id} and partner {partner_id}")
                raise ValueError("DID already exists")

            await self.__validator.validate_did_assignment(did_data)
            self.__logger.debug("Validated did_data successfully")
            did_record: dict[str, Any] = await self.__did_repository.insert_did_default_attendance(did_data)
            self.__logger.debug(f"Inserted DID record: {did_record}")

            history_data: dict[str, Any] = TalkoDidHistoryModel(
                did_number=did_number,
                partner_id=partner_id,
                vendor_id=vendor_id_obj,
                agent_id=agent_id,
                assign_date=current_timestamp,
                workspace_id=workspace_id,
                vendor_config_id=vendor_config_obj,
            ).model_dump()
            self.__logger.debug(f"Created history_data: {history_data}")
            await self.__did_repository.insert_did_history(history_data)
            self.__logger.debug("Inserted DID history")

            self.__logger.info(f"DID {did_number} assigned successfully")
            return did_record
        except Exception as e:
            self.__logger.error(f"Failed to assign DID {did_number}: {str(e)}")
            raise

    async def unassign_did(self, did_number: str, partner_id: int) -> dict[str, Any]:
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
                "workspace_id": 0,
                "status": TalkoDIDStatus.AVAILABLE.value,
                "status_changed_at": current_timestamp,
            }

            updated_did = await self.__did_repository.update_did_values(
                did_number=did_number,
                partner_id=partner_id,  # for verification
                update_data=update_data,
            )

            if not updated_did:
                raise TalkoResourceNotFound(f"DID {did_number} not found for partner {partner_id}")

            # Update History
            history_update: dict[str, Any] = {
                "unassign_date": current_timestamp,
                "status": TalkoDIDStatus.AVAILABLE.value,
            }

            await self.__did_repository.update_did_history(did_number, partner_id, history_update)

            self.__logger.info(f"DID {did_number} unassigned successfully (reset to available)")
            return updated_did

        except Exception as e:
            self.__logger.error(f"Failed to unassign DID {did_number}: {str(e)}")
            raise

    async def update_did_status(
        self,
        vendor_id: ObjectId,
        remove_from_available: list[str],
        add_to_available: list[str],
        remove_from_assigned: list[str],
        add_to_assigned: list[str],
        timestamp: int,
    ) -> None:
        """
        Update DID status by assigning/unassigning DIDs.
        """
        self.__logger.info(f"Starting update_did_status for vendor_id: {vendor_id}")
        try:
            self.__logger.debug(
                f"Update did status data - vendor_id: {vendor_id}, remove_from_available: {remove_from_available}, add_to_available: {add_to_available}, remove_from_assigned: {remove_from_assigned}, add_to_assigned: {add_to_assigned}"
            )
            for did in add_to_assigned:
                self.__logger.debug(f"Assigning DID {did} for vendor {vendor_id}")
                await self.assign_did(0, did, 1, str(vendor_id))
            for did in remove_from_assigned:
                self.__logger.debug(f"Unassigning DID {did} for vendor {vendor_id}")
                await self.unassign_did(did, 1)
            self.__logger.info(f"DID status updated successfully for vendor {vendor_id}")
        except Exception as e:
            self.__logger.error(f"Failed to update DID status for vendor {vendor_id}: {str(e)}")
            raise

    async def get_assigned_dids(self, vendor_id: ObjectId) -> list[str]:
        """
        Retrieve list of assigned DIDs for a vendor.
        """
        self.__logger.info(f"Starting get_assigned_dids for vendor_id: {vendor_id}")
        try:
            assigned_dids = await self.__did_repository.get_assigned_dids(vendor_id)
            self.__logger.debug(f"Retrieved assigned DIDs: {assigned_dids}")
            self.__logger.info(f"Successfully retrieved assigned DIDs for vendor {vendor_id}")
            return assigned_dids
        except Exception as e:
            self.__logger.error(f"Failed to retrieve assigned DIDs for vendor {vendor_id}: {str(e)}")
            raise

    async def get_available_dids(self, vendor_id: ObjectId, vendor_config_id: ObjectId | None = None) -> list[str]:
        """
        Retrieve list of available DIDs for a vendor.
        """
        self.__logger.info(
            f"Starting get_available_dids for vendor_id: {vendor_id}, vendor_config_id: {vendor_config_id}"
        )
        try:
            available_dids = await self.__did_repository.get_available_dids(vendor_id, vendor_config_id)
            self.__logger.debug(f"Retrieved available DIDs: {available_dids}")
            self.__logger.info(f"Successfully retrieved available DIDs for vendor {vendor_id}")
            return available_dids
        except Exception as e:
            self.__logger.error(f"Failed to retrieve available DIDs for vendor {vendor_id}: {str(e)}")
            raise

    async def update_did(
        self,
        did_number: str,
        vendor_id: str,
        partner_id: int,
        workspace_id: int | None = None,
        agent_id: int | None = None,
        vendor_config_id: ObjectId | None = None,
    ) -> dict[str, Any]:
        """
        Update a DID's assignment details.
        """
        self.__logger.info(
            f"Starting update_did for did_number: {did_number}, partner_id: {partner_id}, vendor_id: {vendor_id}, workspace_id: {workspace_id}, agent_id: {agent_id}"
        )
        try:
            vendor_id_obj: ObjectId = ObjectId(vendor_id)
            self.__logger.debug(f"Converted vendor_id to ObjectId: {vendor_id_obj}")
            current_timestamp: int = self.__datetime_util.get_current_time()
            self.__logger.debug(f"Current timestamp: {current_timestamp}")

            existing_did: dict[str, Any] | None = await self.__did_repository.find_did_by_did_number_and_vendor_id(
                did_number, vendor_id_obj
            )
            self.__logger.debug(f"Found existing DID: {existing_did}")
            if not existing_did:
                self.__logger.error(f"DID {did_number} not found for vendor {vendor_id}")
                raise TalkoResourceNotFound(f"DID {did_number} not found for the specified vendor")

            update_data: dict[str, Any] = {}
            if workspace_id is not None:
                update_data["workspace_id"] = workspace_id
            if agent_id is not None:
                update_data["agent_id"] = agent_id
                update_data["mapped_date"] = current_timestamp
            if existing_did.get("partner_id") in (None, 0):
                update_data["partner_id"] = partner_id
                update_data["assign_date"] = current_timestamp
            if update_data:
                update_data["updated_at"] = current_timestamp

            update_data["status"] = TalkoDIDStatus.MAPPED.value
            self.__logger.debug(f"Prepared update data: {update_data}")

            if not update_data:
                self.__logger.info(f"No updates provided for DID {did_number}")
                return existing_did

            updated_did: dict[str, Any] = await self.__did_repository.update_did_attendance(
                did_number, partner_id, update_data
            )
            self.__logger.debug(f"Updated DID: {updated_did}")
            if not updated_did:
                self.__logger.error(f"Failed to update DID {did_number}")
                raise TalkoResourceNotFound(f"Failed to update DID {did_number}")

            history_data: dict[str, Any] = TalkoDidHistoryModel(
                did_number=did_number,
                partner_id=partner_id,
                vendor_id=vendor_id_obj,
                agent_id=agent_id or existing_did.get("agent_id"),
                assign_date=existing_did.get("assign_date") or current_timestamp,
                workspace_id=workspace_id or existing_did.get("workspace_id"),
                update_date=current_timestamp,
                vendor_config_id=vendor_config_id,
            ).model_dump()
            self.__logger.debug(f"Created history data: {history_data}")
            await self.__did_repository.insert_did_history(history_data)
            self.__logger.debug(f"Inserted DID history for DID {did_number}")

            self.__logger.info(f"DID {did_number} updated successfully")
            return updated_did
        except Exception as e:
            self.__logger.error(f"Failed to update DID {did_number}: {str(e)}")
            raise

    async def get_dids_by_partner_and_vendor(self, partner_id: int, vendor_id: str) -> list[str]:
        """
        Retrieve DIDs for a specific partner and vendor.
        """
        self.__logger.info(
            f"Starting get_dids_by_partner_and_vendor for partner_id: {partner_id}, vendor_id: {vendor_id}"
        )
        try:
            vendor_id_obj: ObjectId = ObjectId(vendor_id)
            self.__logger.debug(f"Converted vendor_id to ObjectId: {vendor_id_obj}")
            dids = await self.__did_repository.get_dids_by_partner_and_vendor(partner_id, vendor_id_obj)
            self.__logger.debug(f"Retrieved DIDs: {dids}")
            self.__logger.info(f"Successfully retrieved DIDs for partner_id: {partner_id}, vendor_id: {vendor_id}")
            return dids
        except Exception as e:
            self.__logger.error(
                f"Failed to retrieve DIDs for partner_id: {partner_id}, vendor_id: {vendor_id}: {str(e)}"
            )
            raise

    async def get_dids_by_partner_workspace_and_vendor(
        self,
        partner_id: int,
        workspace_id: int,
        vendor_id: str,
        vendor_config_id: str | None = None,
    ) -> list[str]:
        """
        Retrieve DIDs for a specific partner, workspace, and vendor.
        """
        self.__logger.info(
            f"Starting get_dids_by_partner_workspace_and_vendor for partner_id: {partner_id}, "
            f"workspace_id: {workspace_id}, vendor_id: {vendor_id}, vendor_config_id: {vendor_config_id}"
        )
        try:
            vendor_id_obj: ObjectId = ObjectId(vendor_id)

            # Convert vendor_config_id to ObjectId only if provided
            vendor_config_id_obj: ObjectId | None = ObjectId(vendor_config_id) if vendor_config_id else None

            self.__logger.debug(f"Converted vendor_id: {vendor_id_obj}, vendor_config_id: {vendor_config_id_obj}")

            dids = await self.__did_repository.get_dids_by_partner_workspace_and_vendor(
                partner_id, workspace_id, vendor_id_obj, vendor_config_id_obj
            )

            self.__logger.debug(f"Retrieved DIDs: {dids}")
            return dids
        except Exception as e:
            self.__logger.error(
                f"Failed to retrieve DIDs for partner_id: {partner_id}, workspace_id: {workspace_id}, "
                f"vendor_id: {vendor_id}, vendor_config_id: {vendor_config_id}: {str(e)}"
            )
            raise

    async def get_dids_by_partner_agent_workspace_and_vendor(
        self, partner_id: int, user_id: int, workspace_id: int, vendor_id: str
    ) -> list[str]:
        """
        Retrieve DIDs for a specific partner, agent, workspace, and vendor.
        """
        self.__logger.info(
            f"Starting get_dids_by_partner_agent_workspace_and_vendor for partner_id: {partner_id}, user_id: {user_id}, workspace_id: {workspace_id}, vendor_id: {vendor_id}"
        )
        try:
            vendor_id_obj: ObjectId = ObjectId(vendor_id)
            self.__logger.debug(f"Converted vendor_id to ObjectId: {vendor_id_obj}")
            dids = await self.__did_repository.get_dids_by_partner_agent_workspace_and_vendor(
                partner_id, user_id, workspace_id, vendor_id_obj
            )
            self.__logger.debug(f"Retrieved DIDs: {dids}")
            self.__logger.info(
                f"Successfully retrieved DIDs for partner_id: {partner_id}, user_id: {user_id}, workspace_id: {workspace_id}, vendor_id: {vendor_id}"
            )
            return dids
        except Exception as e:
            self.__logger.error(
                f"Failed to retrieve DIDs for partner_id: {partner_id}, user_id: {user_id}, workspace_id: {workspace_id}, vendor_id: {vendor_id}: {str(e)}"
            )
            raise

    async def get_dids_by_number(self, call_to_number: str) -> dict | None:
        """
        Retrieve DIDs by phone number.
        """
        self.__logger.info(f"Starting get_dids_by_number for call_to_number: {call_to_number}")
        try:
            dids = await self.__did_repository.get_did_by_number(call_to_number)
            self.__logger.debug(f"Retrieved DIDs: {dids}")
            self.__logger.info(f"Successfully retrieved DIDs for call_to_number: {call_to_number}")
            return dids
        except Exception as e:
            self.__logger.error(f"Failed to retrieve DIDs for call_to_number {call_to_number}: {str(e)}")
            raise

    async def get_dids_by_workspace(self, workspace_id: int) -> list[dict[str, Any]]:
        """
        Service method to fetch all DIDs for a workspace ID.
        Cleans ObjectId and converts to strings for safe schema parsing.
        """
        self.__logger.info(f"Starting get_dids_by_workspace for workspace_id: {workspace_id}")
        try:
            records = await self.__did_repository.get_dids_by_workspace(workspace_id)
            self.__logger.debug(f"Retrieved records: {records}")

            cleaned_records = []
            for doc in records:
                # Convert ObjectId fields → str (central helper; legacy docs
                # may store ids as ints/strings already — helper is a no-op).
                doc = stringify_object_ids(doc)

                # display_name may not exist on older docs, or may be stored as "" —
                # fall back to the DID number itself so the UI always has something to show.
                doc["display_name"] = doc.get("display_name") or doc.get("did_number") or ""

                cleaned_records.append(doc)
            self.__logger.debug(f"Cleaned records: {cleaned_records}")

            result = [TalkoContract.DIDResponse(**doc) for doc in cleaned_records]
            self.__logger.info(f"Successfully retrieved DIDs for workspace_id: {workspace_id}")
            return result
        except Exception as e:
            self.__logger.error(f"Error fetching DIDs for workspace {workspace_id}: {str(e)}")
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
            self.__logger.debug(f"Length of did_number : {did_number} is 10")
            return did_number[:2]

        if len(did_number) > 10:
            if did_number.startswith("+"):
                self.__logger.debug(f"Length of did_number : {did_number} is > 10 and it contains + in the starting")
                return did_number[3:5]
            else:
                self.__logger.debug(
                    f"Length of did_number : {did_number} is > 10 and it does not contains + in the starting"
                )
                return did_number[2:4]

        # fallback
        self.__logger.debug("Returning to Fallback case in extract series key")
        return did_number[2:4]

    async def get_dids_available_for_assignment(self, partner_id: int) -> list[TalkoContract.DIDSeriesResponse]:
        """
        Fetch available DIDs for a partner based on vendor configuration,
        include instance_id, and group them by series.
        """

        try:
            self.__logger.info(f"Received partner_id: {partner_id}")

            # Check if partner_config for received partner_id exists or not
            partner_config: dict | None = await self.__partner_config_repository.find_partner_config_by_partner_id(
                partner_id
            )

            if not partner_config:
                self.__logger.error(f"No partner config found for partner_id: {partner_id}")
                raise ValueError(PARTNER_CONFIG_NOT_FOUND)

            self.__logger.info(f"PartnerConfig received: {partner_config}")

            vendor_id: ObjectId = ObjectId(partner_config["vendor_id"])
            self.__logger.info(f"Extracted vendor_id: {vendor_id} from partner_config")

            free_dids: list[str] = await self.get_available_dids(vendor_id)
            self.__logger.debug(f"Retrieved free DIDs: {free_dids}")

            if not free_dids:
                self.__logger.info(f"No free DIDs found for vendor_id: {vendor_id}")
                return []

            phone_number_details: list[dict[str, Any]] = await self.__did_repository.get_details_by_dids(free_dids)

            self.__logger.debug(f"Phone Number Details: {phone_number_details}")

            instance_map: dict[str, str | None] = {
                entry["did_number"]: entry.get("instance_id") for entry in phone_number_details
            }

            self.__logger.debug(f"Instance Map: {instance_map}")

            dids_with_details: list[dict[str, str | None]] = [
                {"number": did_number, "instance_id": instance_map.get(did_number)} for did_number in free_dids
            ]

            self.__logger.debug(f"DIDs With Details: {dids_with_details}")

            grouped_dids: defaultdict[str, list[dict[str, str | None]]] = defaultdict(list)
            for did in dids_with_details:
                series_key: str = self.extract_series_key(did["number"])
                grouped_dids[series_key].append(did)

            self.__logger.debug(f"Grouped DIDs: {grouped_dids}")

            response: list[TalkoContract.DIDSeriesResponse] = [
                TalkoContract.DIDSeriesResponse(
                    series=series,
                    dids=[
                        TalkoContract.DIDDetail(number=did["number"], instance_id=did.get("instance_id"))
                        for did in did_list
                    ],
                    count=len(did_list),
                )
                for series, did_list in grouped_dids.items()
            ]

            self.__logger.info(f"Successfully grouped and retrieved DIDs for partner_id: {partner_id}")

            return response
        except ValueError as ve:
            self.__logger.error(f"Error in retrieving free DIDs: PartnerConfig not found: {str(ve)}")
            raise
        except Exception as e:
            self.__logger.error(f"Error in retrieving free DIDs for partner_id {partner_id}: {str(e)}")
            raise

    async def assign_dids_available_for_assignment(
        self,
        partner_id: int,
        assign_did_data: TalkoContract.AssignDIDToPartner,
    ) -> dict:
        """
        Assigns available DIDs to a partner based on provided configurations.
        """
        try:
            self.__logger.info(
                f"Assign DID Numbers(Service) => Received partner_id: {partner_id}, assign_did_data: {assign_did_data}"
            )

            partner_config = await self.__partner_config_repository.find_partner_config_by_partner_id(partner_id)
            if not partner_config:
                self.__logger.error(f"No partner config found for partner_id: {partner_id}")
                raise ValueError(PARTNER_CONFIG_NOT_FOUND)

            self.__logger.info(f"PartnerConfig received: {partner_config}")
            vendor_id = ObjectId(partner_config["vendor_id"])
            vendor_config_id = ObjectId(partner_config.get("vendor_config_id"))
            self.__logger.info(f"Extracted vendor_id: {vendor_id} from partner_config")

            if partner_config.get("enable_round_robin"):
                await self._assign_round_robin_dids_to_partner(vendor_id, partner_id, assign_did_data, vendor_config_id)
            elif partner_config.get("enable_workspace"):
                await self._assign_workspace_dids_to_partner(vendor_id, partner_id, assign_did_data, vendor_config_id)
            elif partner_config.get("enable_agent_mapping"):
                await self._assign_agent_mapping_dids_to_partner(
                    vendor_id, partner_id, assign_did_data, vendor_config_id
                )
            else:
                raise ValueError(MISSING_DID_ASSIGNMENT_CRITERIA.format(partner_id))

            self.__logger.info(f"Successfully grouped and assigned DIDs for partner_id: {partner_id}")
            return {"message": DID_ASSIGNMENT_SUCCESS}

        except ValueError as ve:
            self.__logger.error(f"PartnerConfig not found: {ve}")
            raise
        except Exception as e:
            self.__logger.error(f"Error in assigning DIDs for partner_id {partner_id}: {e}")
            raise

    async def _assign_round_robin_dids_to_partner(
        self,
        vendor_id: ObjectId,
        partner_id: int,
        assign_did_data: TalkoContract.AssignDIDToPartner,
        vendor_config_id: ObjectId | None = None,
    ):
        round_robin_dids: list[str] = assign_did_data.dids_for_round_robin or []
        if not round_robin_dids:
            raise ValueError(MISSING_ROUND_ROBIN_DIDS)
        for did in round_robin_dids:
            await self.update_did(
                did_number=did,
                vendor_id=str(vendor_id),
                partner_id=partner_id,
                workspace_id=None,
                agent_id=None,
                vendor_config_id=vendor_config_id,
            )

    async def _assign_workspace_dids_to_partner(
        self,
        vendor_id: ObjectId,
        partner_id: int,
        assign_did_data: TalkoContract.AssignDIDToPartner,
        vendor_config_id: ObjectId | None = None,
    ):
        workspace_dids: list[TalkoContract.WorkspaceDIDMapping] = assign_did_data.dids_for_workspace or []
        if not workspace_dids:
            raise ValueError(MISSING_WORKSPACE_MAPPING_DIDS)
        for mapping in workspace_dids:
            workspace_id = mapping.workspace_id
            for did in mapping.did_numbers:
                await self.update_did(
                    did_number=did,
                    vendor_id=str(vendor_id),
                    partner_id=partner_id,
                    workspace_id=int(workspace_id),
                    agent_id=None,
                    vendor_config_id=vendor_config_id,
                )

    async def _assign_agent_mapping_dids_to_partner(
        self,
        vendor_id: ObjectId,
        partner_id: int,
        assign_did_data: TalkoContract.AssignDIDToPartner,
        vendor_config_id: ObjectId | None = None,
    ):
        agent_mapping_dids: list[dict[str, Any]] = assign_did_data.dids_for_agent_mapping or []
        if not agent_mapping_dids:
            raise ValueError(MISSING_AGENT_MAPPING_DIDS)
        for mapping in agent_mapping_dids:
            await self.update_did(
                did_number=mapping.get("did_number"),
                vendor_id=str(vendor_id),
                partner_id=partner_id,
                workspace_id=None,
                agent_id=int(mapping.get("agent_id")),
                vendor_config_id=vendor_config_id,
            )

    async def unassign_dids_for_partner(self, partner_id: int, did_numbers: list[str]) -> dict:
        """
        Unassigned DIDs by updating partner_id to 0 in phone number management collection
        """
        try:
            self.__logger.info(f"Unassign DID Numbers(Service)=> Received partner_id: {partner_id}")

            # Check if partner_config for received partner_id exists or not
            partner_config: dict | None = await self.__partner_config_repository.find_partner_config_by_partner_id(
                partner_id
            )

            if not partner_config:
                self.__logger.error(
                    f"Unssign DID Numbers(Service)=> No partner config found for partner_id: {partner_id}"
                )
                raise ValueError(PARTNER_CONFIG_NOT_FOUND)

            self.__logger.info(f"Unassign DID Numbers(Service)=> PartnerConfig received: {partner_config}")

            for did in did_numbers:
                current_timestamp: int = self.__datetime_util.get_current_time()

                self.__logger.debug(f"Unassign DID Numbers(Service)=> Current timestamp: {current_timestamp}")

                result: bool = await self.__did_repository.unassign_did_to_partner(did, partner_id)
                self.__logger.info(f"Unassign DID Numbers(Service)=> Record updated count for did {did}: {result}")

                history_update: dict[str, Any] = {"unassign_date": current_timestamp}
                self.__logger.debug(f"Unassign DID Numbers(Service)=> Prepared history update: {history_update}")

                updated_history: dict[str, Any] = await self.__did_repository.update_did_history(
                    did, partner_id, history_update
                )
                self.__logger.debug(f"Unassign DID Numbers(Service)=> Updated DID history: {updated_history}")

            self.__logger.info(
                f"Unassign DID Numbers(Service)=> Successfully unassigned DIDs for partner_id: {partner_id}"
            )

            return {"message": DID_UNASSIGNMENT_SUCCESS}

        except ValueError as ve:
            self.__logger.error(f"Error in unassigning DIDs: PartnerConfig not found: {str(ve)}")
            raise

        except Exception as e:
            self.__logger.error(f"Error in unassigning DIDs for partner_id {partner_id}: {str(e)}")
            raise

    async def apply_did_status_update(self, partner_id: int, payload: TalkoContract.AdminDIDAction) -> dict:
        now = self.__datetime_util.get_current_time()
        self.__logger.info(
            f"Applying action '{payload.action}' to DIDs: {payload.did_numbers}, partner_id: {partner_id}"
        )

        results = [
            await self.__process_single_did(did_number, partner_id, payload, now) for did_number in payload.did_numbers
        ]
        return TalkoDidStatusUpdateHelper.build_summary(payload.did_numbers, results)

    async def __process_single_did(
        self,
        did_number: str,
        partner_id: int,
        payload: TalkoContract.AdminDIDAction,
        now: int,
    ) -> dict:
        doc = await self.__did_repository.get_did_by_number(did_number, partner_id)
        current_status = (doc or {}).get("status", TalkoDIDStatus.AVAILABLE.value)

        error = TalkoDidStatusUpdateHelper.validate_did(doc, did_number, current_status, payload.action)
        if error:
            self.__logger.warning(f"Validation failed for DID {did_number}: {error}")
            return error

        try:
            handler = TalkoDidStatusUpdateHelper.ACTION_HANDLERS[payload.action]
            update_data = TalkoDidStatusUpdateHelper.prepare_update_data(handler, current_status, payload, now)

            updated = await self.__did_repository.update_did_status(
                did_number=did_number, update_data=update_data, partner_id=partner_id
            )
            self.__logger.info(f"Action '{payload.action}' applied to DID {did_number}: updated={bool(updated)}")

            if payload.action == ADMIN_ACTION_MARK_SPAMMED:
                await self.__did_repository.increment_spam_count(did_number)
                self.__logger.info(f"Incremented spam count for DID {did_number}")

            return {"did_number": did_number, "success": True, "status": "updated"}

        except ValueError as e:
            return TalkoDidStatusUpdateHelper.parse_value_error(did_number, e)

    async def list_dids(
        self,
        status: str | None = None,
        partner_id: int | None = None,
        workspace_id: int | None = None,
        did_number: str | None = None,
        page: int = 1,
        limit: int = 20,
        did_layer: str | None = None,
    ) -> dict[str, Any]:
        """
        List DIDs for a partner with optional filters and pagination.

        Args:
            status: Optional status filter (case-insensitive aliases supported)
            partner_id: Required partner ID
            workspace_id: Optional workspace filter
            page: Page number (1-based)
            limit: Items per page

        Returns:
            Dict with total, page, limit, and list of cleaned DID items

        Raises:
            ValueError: If partner_id missing or invalid status provided
        """
        self.__logger.info(
            f"Listing DIDs with filters - status: {status}, partner_id: {partner_id}, workspace_id: {workspace_id}, page: {page}, limit: {limit}"
        )
        if partner_id is None:
            self.__logger.error("partner_id is required for listing DIDs")
            raise ValueError("partner_id is required for listing DIDs")

        normalized_layer: str | None = None
        if did_layer is not None:
            layer_clean = did_layer.lower().strip()
            if layer_clean not in (
                TalkoDIDLayer.EXTERNAL.value,
                TalkoDIDLayer.INTERNAL.value,
            ):
                raise ValueError(f"Invalid did_layer filter: '{did_layer}'. Supported: external, internal")
            normalized_layer = layer_clean

        normalized_status: str | None = None
        if status is not None:
            status_clean = status.lower().replace("_", "").replace(" ", "")

            status_mapping: dict[str, str] = {
                "available": TalkoDIDStatus.AVAILABLE.value,
                "mapped": TalkoDIDStatus.MAPPED.value,
                "coolingperiod": TalkoDIDStatus.COOLING_PERIOD.value,
                "cooling": TalkoDIDStatus.COOLING_PERIOD.value,
                "cooldowncompleted": TalkoDIDStatus.COOLDOWN_COMPLETED.value,
                "cooldown": TalkoDIDStatus.COOLDOWN_COMPLETED.value,
                "cooling period": TalkoDIDStatus.COOLING_PERIOD.value,
                "cooldown completed": TalkoDIDStatus.COOLDOWN_COMPLETED.value,
            }

            normalized_status = status_mapping.get(status_clean)
            if normalized_status is None:
                raise ValueError(
                    f"Invalid status filter: '{status}'. "
                    + "Supported values: available, mapped, cooling_period, cooldown_completed "
                    "(case-insensitive, underscores/spaces allowed)"
                )

        self.__logger.debug(f"Normalized status filter: {normalized_status}")

        docs: list[dict[str, Any]]
        total: int
        docs, total = await self.__did_repository.get_dids_by_partner(
            partner_id=partner_id,
            workspace_id=workspace_id,
            status=normalized_status,  # use normalized value
            did_number=did_number,
            offset=page,
            limit=limit,
        )

        self.__logger.debug(f"Fetched DIDs from repository: total: {total}, docs count: {len(docs)}")

        cleaned_dids: list[dict[str, Any]] = []
        for doc in docs:
            clean = stringify_object_ids(doc)
            clean.pop("_id", None)
            if (
                normalized_layer is not None
                and clean.get("did_layer", TalkoDIDLayer.EXTERNAL.value) != normalized_layer
            ):
                continue

            cleaned_dids.append(
                {
                    "did_number": clean.get("did_number", ""),
                    "status": clean.get("status", TalkoDIDStatus.AVAILABLE.value),
                    "partner_id": clean.get("partner_id", 0),
                    "workspace_id": clean.get("workspace_id"),
                    "agent_id": clean.get("agent_id"),
                    "vendor_id": str(clean.get("vendor_id", "")),
                    "spam_count": clean.get("spam_count", 0),
                    "last_spam_detected_at": clean.get("last_spam_detected_at"),
                    "cooldown_until": clean.get("cooldown_until"),
                    "status_changed_at": clean.get("status_changed_at", 0),
                    "assign_date": clean.get("assign_date"),
                    "mapped_date": clean.get("mapped_date"),
                    "did_layer": clean.get("did_layer", TalkoDIDLayer.EXTERNAL.value),
                    "parent_did_number": clean.get("parent_did_number"),
                }
            )

        return {"total": total, "page": page, "limit": limit, "dids": cleaned_dids}

    async def assign_ai_agent_did(
        self,
        partner_id: int,
        agent_bot_id: int | None = 0,
        did_number: str | None = None,
    ) -> dict[str, Any]:
        """Assign an available ai_agent DID.

        Two modes (same row, no migration):
        - makun-ai: agent_bot_id=<real bot> (existing behavior).
        - VoiceAI/engine-routed (partner-only): agent_bot_id=0/None. Talko
          stores did_number -> partner_id only; the agent lives in the engine
          Numbers UI and is resolved per call.
        """
        # Normalize None -> 0 (partner-only VoiceAI path).
        if agent_bot_id is None:
            agent_bot_id = 0
        try:
            self.__logger.info(f"Assigning AI agent DID. partner_id={partner_id}, agent_bot_id={agent_bot_id}")

            existing: dict[str, Any] | None = None

            # Find or auto-pick available ai_agent DID
            if did_number:
                existing = await self.__did_repository.find_did_attendance(
                    did_number,
                    partner_id,
                )

                if (
                    not existing
                    or existing.get("did_type") != TalkoDIDType.AI_AGENT.value
                    or existing.get("status") != TalkoDIDStatus.AVAILABLE.value
                ):
                    raise ValueError("DID must be ai_agent type and AVAILABLE")

            updated_did: dict[str, Any] = await self.__did_repository.update_did_values(
                did_number=did_number,
                partner_id=partner_id,
                update_data={
                    "partner_id": partner_id,
                    "agent_bot_id": agent_bot_id,
                    "status": TalkoDIDStatus.MAPPED.value,
                },
            )

            updated_did_record: dict[str, Any] = {
                "did_number": updated_did.get("did_number"),
                "partner_id": updated_did.get("partner_id"),
                "agent_bot_id": updated_did.get("agent_bot_id"),
                "status": updated_did.get("status"),
            }

            return updated_did_record

        except Exception as e:
            error_message: str = str(e)

            self.__logger.error(
                f"Error assigning AI agent DID for partner_id={partner_id} agent_bot_id={agent_bot_id} error={error_message}"
            )
            raise

    async def claim_did_for_campaign(
        self,
        partner_id: int,
        did_number: str,
        agent_bot_id: int,
    ) -> dict[str, Any]:
        """
        Marks a partner-owned ai_agent DID as Mapped and binds it to the
        campaign's own agent_bot_id. Used when makun-ai adds a DID to a
        campaign's did_selection.

        agent_bot_id IS required here, unlike an earlier version of this
        method: TalkoPSTNBridgeService/CallManagementService._pre_create_session
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
            existing: dict[str, Any] | None = await self.__did_repository.find_did_attendance(did_number, partner_id)
            if not existing or existing.get("did_type") != TalkoDIDType.AI_AGENT.value:
                raise TalkoResourceNotFound(f"ai_agent DID {did_number} not found for partner {partner_id}")

            current_status = existing.get("status")
            if current_status == TalkoDIDStatus.MAPPED.value:
                if existing.get("agent_bot_id") == agent_bot_id:
                    self.__logger.info(
                        f"DID {did_number} already Mapped to agent_bot_id={agent_bot_id}, claim is a no-op"
                    )
                    return {"did_number": did_number, "status": current_status}
                raise ValueError(
                    "DID {} is already Mapped to a different agent_bot_id={}".format(
                        did_number, existing.get("agent_bot_id")
                    )
                )

            if current_status != TalkoDIDStatus.AVAILABLE.value:
                raise ValueError(f"DID {did_number} cannot be claimed from status {current_status}")

            updated_did: dict[str, Any] = await self.__did_repository.update_did_values(
                did_number=did_number,
                partner_id=partner_id,
                update_data={
                    "status": TalkoDIDStatus.MAPPED.value,
                    "agent_bot_id": agent_bot_id,
                },
            )

            self.__logger.info(
                f"DID {did_number} claimed for campaign use (partner_id={partner_id}, agent_bot_id={agent_bot_id})"
            )
            return {"did_number": did_number, "status": updated_did.get("status")}

        except Exception as e:
            self.__logger.error(f"Error claiming DID {did_number} for campaign use, partner_id={partner_id}: {str(e)}")
            raise

    async def release_campaign_did(
        self,
        partner_id: int,
        did_number: str,
        agent_bot_id: int,
    ) -> dict[str, Any]:
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
            existing: dict[str, Any] | None = await self.__did_repository.find_did_attendance(did_number, partner_id)
            if not existing:
                raise TalkoResourceNotFound(f"DID {did_number} not found for partner {partner_id}")

            current_status = existing.get("status")
            if current_status != TalkoDIDStatus.MAPPED.value or existing.get("agent_bot_id") != agent_bot_id:
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

            updated_did: dict[str, Any] = await self.__did_repository.update_did_values(
                did_number=did_number,
                partner_id=partner_id,
                update_data={
                    "status": TalkoDIDStatus.AVAILABLE.value,
                    "agent_bot_id": 0,
                },
            )

            self.__logger.info(f"DID {did_number} released from campaign use (partner_id={partner_id})")
            return {"did_number": did_number, "status": updated_did.get("status")}

        except Exception as e:
            self.__logger.error(f"Error releasing campaign DID {did_number} for partner_id={partner_id}: {str(e)}")
            raise

    async def release_ai_agent_did(
        self,
        partner_id: int,
        agent_bot_id: int,
    ) -> list[str]:
        """Release all DIDs assigned to an AI agent bot."""
        try:
            self.__logger.info(f"Releasing AI agent DIDs. partner_id={partner_id}, agent_bot_id={agent_bot_id}")

            assigned_dids: list[dict[str, Any]] = await self.__did_repository.get_mapped_ai_agent_dids(
                partner_id=partner_id,
                agent_bot_id=agent_bot_id,
            )

            released_dids: list[str] = []

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
                f"Error releasing AI agent DIDs for partner_id={partner_id} agent_bot_id={agent_bot_id} error={error_message}"
            )
            raise

    async def get_ai_agent_dids(
        self,
        partner_id: int,
        agent_bot_id: int,
    ) -> list[str]:
        """Get all DIDs assigned to an AI agent bot."""
        try:
            dids: list[dict[str, Any]] = await self.__did_repository.get_ai_agent_dids(
                partner_id=partner_id,
                agent_bot_id=agent_bot_id,
            )

            did_numbers: list[str] = [did["did_number"] for did in dids]

            return did_numbers

        except Exception as e:
            error_message: str = str(e)

            self.__logger.error(
                f"Error fetching AI agent DIDs for partner_id={partner_id} agent_bot_id={agent_bot_id} error={error_message}"
            )
            raise

    async def list_ai_agent_dids(self, partner_id: int) -> list[dict[str, Any]]:
        """List all ai_agent-type DIDs for a partner, assigned or not."""
        try:
            self.__logger.info(f"Listing all ai_agent DIDs for partner_id={partner_id}")

            dids: list[dict[str, Any]] = await self.__did_repository.get_ai_agent_dids(partner_id=partner_id)

            cleaned_dids: list[dict[str, Any]] = [
                {
                    "did_number": did.get("did_number", ""),
                    "display_name": did.get("display_name"),
                    "status": did.get("status", TalkoDIDStatus.AVAILABLE.value),
                    "agent_bot_id": did.get("agent_bot_id") or 0,
                    "mapped_date": did.get("mapped_date"),
                    "vendor_id": str(did.get("vendor_id", "")),
                    "spam_count": did.get("spam_count", 0),
                    "cooldown_until": did.get("cooldown_until"),
                }
                for did in dids
            ]

            self.__logger.info(f"Found {len(cleaned_dids)} ai_agent DIDs for partner_id={partner_id}")

            return cleaned_dids

        except Exception as e:
            self.__logger.error(f"Error listing ai_agent DIDs for partner_id={partner_id} error={str(e)}")
            raise

    async def get_available_ai_agent_dids(
        self,
        partner_id: int,
    ) -> list[str]:
        """Get available ai_agent DIDs for a partner."""
        try:
            dids: list[dict[str, Any]] = await self.__did_repository.get_available_ai_agent_dids(
                partner_id=partner_id,
            )

            did_numbers: list[str] = [did["did_number"] for did in dids]

            return did_numbers

        except Exception as e:
            error_message: str = str(e)

            self.__logger.error(
                f"Error fetching available AI agent DIDs for partner_id={partner_id} error={error_message}"
            )
            raise

    async def list_unassigned_available_ai_agent_dids(
        self,
        partner_id: int,
    ) -> list[str]:
        """
        Return ai_agent DIDs that are not mapped to any partner and are AVAILABLE.
        """
        try:
            self.__logger.info(f"Listing unassigned available ai_agent DIDs for partner_id={partner_id}")

            dids: list[str] = await self.__did_repository.get_available_ai_agent_dids(partner_id=partner_id)

            self.__logger.info(f"Found {len(dids)} unassigned available ai_agent DIDs for partner_id={partner_id}")

            return dids

        except Exception:
            self.__logger.error(f"Error listing unassigned available ai_agent DIDs for partner_id={partner_id}")
            raise

    # ── Dual-layer: External / Internal ────────────────────────────────────

    async def import_external_dids(
        self,
        vendor_id: str,
        did_numbers: list[str],
        vendor_config_id: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        """Bulk-import wholesaler-owned EXTERNAL DIDs into the pool (partner_id=0)."""
        current_timestamp: int = self.__datetime_util.get_current_time()
        vendor_id_obj: ObjectId = ObjectId(vendor_id)
        vendor_config_obj: ObjectId | None = ObjectId(vendor_config_id) if vendor_config_id else None
        imported: list[str] = []
        skipped: list[dict[str, str]] = []
        for did_number in did_numbers:
            existing = await self.__did_repository.find_did_by_did_number_and_vendor_id(did_number, vendor_id_obj)
            if existing:
                skipped.append({"did_number": did_number, "reason": "already exists"})
                continue
            did_data: dict[str, Any] = TalkoPhoneNumberManagement(
                workspace_id=0,
                did_number=did_number,
                partner_id=0,
                vendor_id=vendor_id_obj,
                vendor_config_id=vendor_config_obj,
                assign_date=current_timestamp,
                status=TalkoDIDStatus.AVAILABLE.value,
                did_type=TalkoDIDType.NORMAL.value,
                agent_bot_id=0,
                display_name=display_name,
                did_layer=TalkoDIDLayer.EXTERNAL.value,
            ).model_dump()
            await self.__validator.validate_did_assignment(did_data)
            await self.__did_repository.insert_did_default_attendance(did_data)
            imported.append(did_number)
        return {"imported": imported, "skipped": skipped, "count": len(imported)}

    async def provision_internal_did(
        self,
        parent_did_number: str,
        partner_id: int,
        workspace_id: int | None = None,
        agent_id: int | None = None,
        vendor_config_id: str | None = None,
    ) -> dict[str, Any]:
        """Provision an INTERNAL routable DID cloned from an EXTERNAL parent."""
        current_timestamp: int = self.__datetime_util.get_current_time()
        parent = await self.__did_repository.get_did_by_number(parent_did_number)
        if not parent or parent.get("did_layer", TalkoDIDLayer.EXTERNAL.value) != TalkoDIDLayer.EXTERNAL.value:
            raise TalkoResourceNotFound(
                EXTERNAL_DID_NOT_FOUND.format(parent_did_number, parent.get("vendor_id") if parent else "unknown")
            )
        vendor_id_obj: ObjectId = parent["vendor_id"]
        if isinstance(vendor_id_obj, str):
            vendor_id_obj = ObjectId(vendor_id_obj)
        vendor_config_obj: ObjectId | None = (
            ObjectId(vendor_config_id) if vendor_config_id else parent.get("vendor_config_id")
        )
        if isinstance(vendor_config_obj, str):
            vendor_config_obj = ObjectId(vendor_config_obj)
        internal_number = parent_did_number
        existing = await self.__did_repository.find_did_attendance(internal_number, partner_id)
        if existing and existing.get("did_layer") == TalkoDIDLayer.INTERNAL.value:
            return {
                "did_number": internal_number,
                "status": existing.get("status"),
                "did_layer": TalkoDIDLayer.INTERNAL.value,
            }
        did_data: dict[str, Any] = TalkoPhoneNumberManagement(
            workspace_id=workspace_id or 0,
            did_number=internal_number,
            partner_id=partner_id,
            vendor_id=vendor_id_obj,
            vendor_config_id=vendor_config_obj,
            agent_id=agent_id,
            assign_date=current_timestamp,
            mapped_date=current_timestamp,
            status=TalkoDIDStatus.MAPPED.value,
            did_type=TalkoDIDType.NORMAL.value,
            agent_bot_id=0,
            did_layer=TalkoDIDLayer.INTERNAL.value,
            parent_did_id=parent.get("_id"),
            parent_did_number=parent_did_number,
        ).model_dump()
        record = await self.__did_repository.insert_did_default_attendance(did_data)
        record.pop("_id", None)
        return stringify_object_ids(record)

    async def map_external_internal(
        self, external_did_number: str, internal_did_number: str, partner_id: int
    ) -> dict[str, Any]:
        """Bind an existing INTERNAL DID to an EXTERNAL parent (re-map)."""
        external = await self.__did_repository.get_did_by_number(external_did_number)
        if not external or external.get("did_layer", TalkoDIDLayer.EXTERNAL.value) != TalkoDIDLayer.EXTERNAL.value:
            raise TalkoResourceNotFound(EXTERNAL_DID_NOT_FOUND.format(external_did_number, "unknown"))
        internal = await self.__did_repository.find_did_attendance(internal_did_number, partner_id)
        if not internal or internal.get("did_layer") != TalkoDIDLayer.INTERNAL.value:
            raise TalkoResourceNotFound(INTERNAL_DID_NOT_FOUND.format(internal_did_number, partner_id))
        current_parent = internal.get("parent_did_number")
        if current_parent and current_parent != external_did_number:
            raise ValueError(DID_ALREADY_MAPPED.format(internal_did_number))
        updated = await self.__did_repository.update_did_values(
            did_number=internal_did_number,
            partner_id=partner_id,
            update_data={
                "parent_did_id": external.get("_id"),
                "parent_did_number": external_did_number,
                "status": TalkoDIDStatus.MAPPED.value,
            },
        )
        if not updated:
            raise TalkoResourceNotFound(INTERNAL_DID_NOT_FOUND.format(internal_did_number, partner_id))
        return {
            "did_number": internal_did_number,
            "parent_did_number": external_did_number,
            "status": updated.get("status"),
        }

    async def get_pool_utilization(self, vendor_id: str | None = None) -> list[dict[str, Any]]:
        """Counts by (did_layer, status) for admin pool dashboard."""
        vendor_obj: ObjectId | None = ObjectId(vendor_id) if vendor_id else None
        return await self.__did_repository.get_pool_utilization(vendor_obj)
