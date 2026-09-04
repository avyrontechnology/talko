import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives.asymmetric import rsa

from src.components.call_agent_map.repository import TalkoAgentMappingRepository
from src.components.call_agent_map.services import TalkoAgentMappingService
from src.components.call_management import messages as call_messages
from src.components.call_management.dto import TalkoContract
from src.components.call_management.handlers.base_handler import TalkoVendorCallHandler
from src.components.call_management.messages import (
    NO_DID_ASSIGNED_TO_PARTNER,
    PARTNER_CONFIG_NOT_FOUND,
    UNSUPPORTED_VENDOR,
    VENDOR_CONFIG_FOR_VENDOR_ID_NOT_FOUND,
)
from src.components.call_management.repository import TalkoCallRepository
from src.components.call_management.tata_tele.call_service import TalkoTataTeleCallHandler
from src.components.cdr.constants import TalkoEntityType
from src.components.cdr.entity_fields import derive_entity_fields
from src.components.cdr.models import TalkoCDR
from src.components.did_management.constants import USABLE_STATUSES, TalkoDIDStatus
from src.components.did_management.services import TalkoDidManagementService
from src.components.partner_config.repository import TalkoPartnerConfigRepository
from src.components.vendor_config.repository import TalkoVendorConfigRepository
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.assignment_strategy import TalkoRoundRobinAssignment
from src.utils.crypto_utils import TalkoRSAKeyHandler
from src.utils.datetime_util import TalkoDateTimeUtil
from src.utils.enums import TalkoNumberType, TalkoVendorType


class TalkoCallProcessorHelper:
    """
    Helper class responsible for orchestrating the initiation of outbound calls.
    It handles retrieving partner configurations, selecting the appropriate DID,
    determining the correct vendor handler, and preparing the TalkoCDR.
    """

    def __init__(
        self,
        repository: TalkoCallRepository,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
        partner_config_repo: TalkoPartnerConfigRepository,
        vendor_config_repo: TalkoVendorConfigRepository,
        agent_mapping_service: TalkoAgentMappingService,
        agent_mapping_repository: TalkoAgentMappingRepository,
        did_management_service: TalkoDidManagementService,
    ) -> None:
        try:
            self.__repository: TalkoCallRepository = repository
            self.__logger: TalkoServiceLogger = logger
            self.__datetime_util: TalkoDateTimeUtil = datetime_util
            self.__partner_config_repo: TalkoPartnerConfigRepository = partner_config_repo
            self.__vendor_config_repo: TalkoVendorConfigRepository = vendor_config_repo
            self.__agent_mapping_service: TalkoAgentMappingService = agent_mapping_service
            self.__agent_mapping_repository: TalkoAgentMappingRepository = (
                agent_mapping_repository
            )
            self.__did_management_service: TalkoDidManagementService = did_management_service
            self.__round_robin: TalkoRoundRobinAssignment = TalkoRoundRobinAssignment()
            self.__logger.info("TalkoCallProcessorHelper initialized successfully")
        except Exception as e:
            self.__logger.error(
                "Failed to initialize TalkoCallProcessorHelper: {}".format(str(e))
            )
            raise

    async def get_partner_config(self, partner_id: int) -> Dict[str, Any]:
        try:
            partner_config: Optional[Dict[str, Any]] = (
                await self.__repository.get_partner_config_by_partner_id(partner_id)
            )
            if not partner_config:
                self.__logger.error(
                    "Partner config for partner_id {} not found".format(partner_id)
                )
                raise TalkoResourceNotFound(call_messages.PARTNER_CONFIG_NOT_FOUND)

            if "did_indices" not in partner_config:
                partner_config["did_indices"] = {"round_robin": 0}
                await self.__repository.update_partner_config_did_indices(
                    partner_id,
                    partner_config["did_indices"],
                    self.__datetime_util.get_current_time(),
                )
                self.__logger.info(
                    "Initialized did_indices for partner_id {}".format(partner_id)
                )

            self.__logger.info(
                "Retrieved partner config for partner_id {}".format(partner_id)
            )
            return partner_config
        except Exception as e:
            self.__logger.error(
                "Error retrieving partner config for {}: {}".format(partner_id, str(e))
            )
            raise

    async def get_agent_assign_did_in_agent_mapping(
        self,
        agent_id: int,
        partner_id: int,
        active_did_pool: List[str],
        service_board_id: Optional[int] = None,
    ) -> Optional[str]:
        try:
            mapping: Optional[Dict[str, Any]] = (
                await self.__agent_mapping_repository.get_agent_did_mapping(
                    agent_id, partner_id
                )
            )
            if mapping:
                assigned_did = mapping.get("did", [None])[0]
                if assigned_did in active_did_pool:
                    if (
                        service_board_id
                        and mapping.get("service_board_id") != service_board_id
                    ):
                        self.__logger.debug(
                            "Agent {} mapped to different service board {}".format(
                                agent_id, mapping.get("service_board_id")
                            )
                        )
                        return None
                    self.__logger.debug(
                        "Assigned DID from mapping for agent {}: {}".format(
                            agent_id, assigned_did
                        )
                    )
                    return assigned_did
            return None
        except Exception as e:
            self.__logger.error(
                "Error getting DID mapping for agent {}: {}".format(agent_id, str(e))
            )
            raise

    async def validate_given_did(
        self,
        did: str,
        partner_id: int,
        service_board_id: Optional[int] = None,
    ) -> None:
        self.__logger.info(
            "Validating provided DID {} for partner {}".format(did, partner_id)
        )

        did_record = await self.__did_management_service.get_dids_by_number(did)
        if not did_record:
            self.__logger.warning(
                "Attempt to use non-existent DID: {} by partner {}".format(
                    did, partner_id
                )
            )
            raise TalkoResourceNotFound("DID {} does not exist in the system".format(did))

        self.__logger.debug("Fetched DID record for {}: {}".format(did, did_record))

        if not did_record.get("is_active"):
            raise TalkoBadRequestError("The dedicated DID {} is not active".format(did))

        # Available DIDs already carry a real partner_id here — that's the
        # normal state for a campaign's dedicated DID (Section 16.x): the
        # campaign picker deliberately never calls assign-ai-agent (which is
        # what flips a DID to Mapped) since that would tie the DID to one
        # specific agent_bot_id, and a campaign needs to hold several DIDs
        # not bound to any single agent. Available vs Mapped has no
        # vendor/SIP-side effect — it's purely Talko's own bookkeeping — so
        # both are equally valid for an explicit dedicated_did call as long
        # as the DID genuinely belongs to the requesting partner (checked
        # just below).
        current_status = did_record.get("status")
        if current_status not in USABLE_STATUSES:
            status_display = current_status or "Unknown"
            raise TalkoBadRequestError(
                "DID {} cannot be used for calls (current status: {}). Only available or mapped DIDs are allowed for outbound calls.".format(
                    did, status_display
                )
            )

        if str(did_record.get("partner_id")) != str(partner_id):
            self.__logger.warning(
                "Partner {} tried to use DID {} that belongs to partner {}".format(
                    partner_id, did, did_record.get("partner_id")
                )
            )
            raise TalkoBadRequestError(
                "DID {} is not assigned to your partner account".format(did)
            )

        if service_board_id is not None:
            did_board_id = did_record.get("service_board_id")
            if did_board_id is not None and str(did_board_id) != str(service_board_id):
                raise TalkoBadRequestError(
                    "DID {} is restricted to service board {}, but request is for service board {}".format(
                        did, did_board_id, service_board_id
                    )
                )

        self.__logger.debug(
            "Validated dedicated DID {} for partner {}".format(did, partner_id)
        )

    async def select_did(
        self,
        partner_config: Dict[str, Any],
        partner_id: int,
        user_id: int,
        service_board_id: Optional[int] = None,
    ) -> str:
        try:
            self.__logger.info(
                "Selecting DID for partner {}, user {}, service_board_id {}".format(
                    partner_id, user_id, service_board_id
                )
            )
            enable_agent_mapping: bool = partner_config.get(
                "enable_agent_mapping", False
            )
            enable_service_board: bool = partner_config.get(
                "enable_service_board", False
            )
            enable_round_robin: bool = partner_config.get("enable_round_robin", False)
            vendor_id: str = str(partner_config.get("vendor_id"))

            if enable_service_board and not service_board_id:
                self.__logger.error(
                    "Service board ID is required when service boards are enabled"
                )
                raise TalkoBadRequestError(
                    "Service board ID is required when service boards are enabled."
                )

            if enable_agent_mapping:
                dids: List[str] = (
                    await self.__did_management_service.get_dids_by_partner_agent_service_board_and_vendor(
                        partner_id, user_id, service_board_id, vendor_id
                    )
                )
            elif enable_service_board:
                dids: List[str] = (
                    await self.__did_management_service.get_dids_by_partner_service_board_and_vendor(
                        partner_id,
                        service_board_id,
                        vendor_id,
                        vendor_config_id=partner_config.get("vendor_config_id"),
                    )
                )
            elif enable_round_robin:
                dids: List[str] = (
                    await self.__did_management_service.get_dids_by_partner_and_vendor(
                        partner_id, vendor_id
                    )
                )
            else:
                dids = []

            if not dids:
                self.__logger.error(
                    "No DIDs available for partner {} with strategy {}".format(
                        partner_id, partner_config
                    )
                )
                raise TalkoResourceNotFound(NO_DID_ASSIGNED_TO_PARTNER)

            if enable_round_robin or enable_service_board:
                from_number: str = await self._assign_round_robin_did(
                    partner_config, partner_id, dids, service_board_id
                )
            elif enable_agent_mapping:
                from_number = await self.get_agent_assign_did_in_agent_mapping(
                    user_id, partner_id, dids, service_board_id
                )
                if not from_number:
                    from_number = await self._assign_round_robin_did(
                        partner_config, partner_id, dids
                    )
            else:
                raise TalkoResourceNotFound(NO_DID_ASSIGNED_TO_PARTNER)

            self.__logger.info(
                "Selected DID {} for partner {}".format(from_number, partner_id)
            )
            return from_number
        except Exception as e:
            self.__logger.error(
                "Error selecting DID for partner {}: {}".format(partner_id, str(e))
            )
            raise

    async def _assign_round_robin_did(
        self,
        partner_config: Dict[str, Any],
        partner_id: int,
        did_list: List[str],
        service_board_id: Optional[int] = None,
    ) -> str:
        if not did_list:
            self.__logger.error(
                "No round_robin_dids available for round-robin for partner {}".format(
                    partner_id
                )
            )
            raise TalkoResourceNotFound(NO_DID_ASSIGNED_TO_PARTNER)

        index_key = "round_robin" if service_board_id is None else str(service_board_id)
        self.__logger.debug(
            "Current did_indices: {}".format(partner_config["did_indices"])
        )
        index_value = partner_config["did_indices"].get(str(index_key), 0)
        did_index = index_value % len(did_list)
        assignments: Dict[int, str] = self.__round_robin.assign(
            [partner_id], did_list, did_index
        )
        from_number: str = assignments[partner_id]
        self.__logger.debug("Current did_index for {}: {}".format(index_key, did_index))

        next_did_index: int = (did_index + 1) % len(did_list)
        current_timestamp: int = self.__datetime_util.get_current_time()
        self.__logger.debug(
            "Next did_index for {}: {}".format(index_key, next_did_index)
        )

        partner_config["did_indices"][str(index_key)] = next_did_index
        update_result: Optional[Dict[str, Any]] = (
            await self.__repository.update_partner_config_did_indices(
                partner_id, partner_config["did_indices"], current_timestamp
            )
        )

        if not update_result:
            self.__logger.error(
                "Failed to update did_indices for partner_id {}".format(partner_id)
            )
            raise TalkoResourceNotFound(PARTNER_CONFIG_NOT_FOUND)

        return from_number

    async def get_vendor_handler(
        self, vendor_id: str, vendor_config_id: Optional[str] = None
    ) -> TalkoVendorCallHandler:
        try:
            self.__logger.info(
                "Get vendor config data, vendor id: {}, vendor config id: {}".format(
                    vendor_id, vendor_config_id
                )
            )
            vendor_config: Optional[Dict[str, Any]] = (
                await self.__repository.get_vendor_config(vendor_id, vendor_config_id)
            )
            if not vendor_config:
                self.__logger.error(
                    "Vendor config for vendor_id {} not found".format(vendor_id)
                )
                raise TalkoResourceNotFound(VENDOR_CONFIG_FOR_VENDOR_ID_NOT_FOUND)

            vendor_type: Optional[str] = vendor_config.get("vendor_type")
            if vendor_type in [TalkoVendorType.TATA_TELE.value, TalkoVendorType.ACEFHONE.value]:
                self.__logger.info(
                    "Retrieved vendor handler for vendor_id {}".format(vendor_id)
                )
                return TalkoTataTeleCallHandler(vendor_config, self.__logger, vendor_type)

            self.__logger.error(
                "Unsupported vendor type {} for vendor_id {}".format(
                    vendor_type, vendor_id
                )
            )
            raise TalkoBadRequestError(UNSUPPORTED_VENDOR.format(vendor_type))
        except Exception as e:
            self.__logger.error(
                "Error getting vendor handler for {}: {}".format(vendor_id, str(e))
            )
            raise

    def _derive_entity_fields(
        self,
        call_data: Optional[TalkoContract.CallCreate] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        entity_name: Optional[str] = None,
        lead_id: Optional[int] = None,
        lead_name: Optional[str] = None,
        default_entity_type: Optional[TalkoEntityType] = None,
    ) -> Dict[str, Optional[Any]]:
        entity_type = (
            entity_type
            or getattr(call_data, "entity_type", None)
            or getattr(call_data, "entitytype", None)
        )
        entity_id = (
            entity_id
            if entity_id is not None
            else getattr(call_data, "entity_id", None)
        )
        if entity_id is None:
            entity_id = getattr(call_data, "entityid", None)
        entity_name = (
            entity_name
            or getattr(call_data, "entity_name", None)
            or getattr(call_data, "entityname", None)
        )
        lead_id = (
            lead_id if lead_id is not None else getattr(call_data, "lead_id", None)
        )
        if lead_id is None:
            lead_id = getattr(call_data, "leadid", None)
        lead_name = (
            lead_name
            or getattr(call_data, "lead_name", None)
            or getattr(call_data, "leadname", None)
        )

        return derive_entity_fields(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            lead_id=lead_id,
            lead_name=lead_name,
            default_entity_type=default_entity_type,
        )

    def prepare_cdr(
        self,
        call_data: TalkoContract.CallCreate,
        call_id: str,
        call_uuid: str,
        call_status: str,
        timestamp: Any,
        partner_id: int,
        user_id: int,
        from_number: str,
        to_number: Optional[str] = None,
        vendor_id: Optional[str] = None,
        vendor_config_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            entity_fields = self._derive_entity_fields(call_data=call_data)

            cdr = TalkoCDR(
                action="outbound",
                calling_mode="clicktocall",
                date_time=timestamp,
                solution="sales",
                sr_number="SR_{}".format(call_uuid[:8]),
                customer=to_number,
                agent=user_id,
                call_status=call_status,
                customer_status="unknown",
                agent_status="unknown",
                total_call_duration=0,
                talk_time=0,
                call_actions=[],
                call_uuid=call_uuid,
                hangup_by="none",
                partner_id=partner_id,
                call_id=call_id,
                lead_id=entity_fields["lead_id"],
                lead_name=entity_fields["lead_name"],
                entity_type=entity_fields["entity_type"],
                entity_id=entity_fields["entity_id"],
                entity_name=entity_fields["entity_name"],
                service_board_id=call_data.service_board_id,
                start_stamp=0,
                end_stamp=0,
                answer_stamp=0,
                reason_key="initiated",
                agent_number=call_data.agent_number,
                did_number=from_number,
                vendor_id=str(vendor_id) if vendor_id is not None else None,
                vendor_config_id=(
                    str(vendor_config_id) if vendor_config_id is not None else None
                ),
            )
            self.__logger.info("Prepared TalkoCDR for call_id {}".format(call_id))
            return cdr.model_dump()
        except Exception as e:
            self.__logger.error(
                "Error preparing TalkoCDR for call_id {}: {}".format(call_id, str(e))
            )
            raise

    def decrypt_lead_data(
        self,
        call_data: TalkoContract.CallCreate,
    ) -> Dict[str, Any]:
        decrypted_lead_data: dict = {}
        if call_data.lead_secret:
            try:
                self.__logger.debug(
                    "Attempting to process lead_secret: {}...".format(
                        call_data.lead_secret[:32]
                    )
                )
                private_key: rsa.RSAPrivateKey = TalkoRSAKeyHandler.load_private_key()
                try:
                    self.__logger.debug("Trying to decrypt lead_secret as hex")
                    decrypted_lead_data = TalkoRSAKeyHandler.decrypt_with_private_key(
                        call_data.lead_secret, private_key
                    )
                    self.__logger.debug("Successfully decrypted lead_secret as hex")
                    return decrypted_lead_data
                except ValueError as hex_error:
                    self.__logger.debug(
                        "Hex decryption failed: {}".format(str(hex_error))
                    )
                    raise ValueError(call_messages.FAILED_TO_DECRYPT_LEAD_SECRET_AS_HEX)
            except ValueError as ve:
                self.__logger.error("Failed to decrypt lead_secret: {}".format(str(ve)))
                raise
            except Exception as e:
                self.__logger.error(
                    "Unexpected error during decryption: {}".format(str(e))
                )
                raise
        return decrypted_lead_data

    def extract_to_number(
        self, call_data: TalkoContract.CallCreate, decrypted_lead_data: Dict[str, Any]
    ) -> str:
        try:
            to_number: str = ""
            if call_data.number_type == TalkoNumberType.PRIMARY_NUMBER.value:
                to_number = decrypted_lead_data.get("phone_number")
            elif call_data.number_type == TalkoNumberType.ADDITIONAL_NUMBER.value:
                to_number = decrypted_lead_data.get("additional_number")
            elif call_data.number_type == TalkoNumberType.WHATSAPP_NUMBER.value:
                to_number = decrypted_lead_data.get("whatsapp_number")

            if not to_number:
                raise ValueError(call_messages.NO_VALID_PHONE_NUMBER_FOUND_FOR_LEAD)

            return to_number
        except Exception as e:
            self.__logger.error("Error extracting to_number: {}".format(str(e)))
            raise

    async def create_incoming_cdr(
        self,
        request_data: Dict,
        partner_id: int,
        agent_id: Optional[int] = None,
        service_board_id: Optional[int] = None,
        agent_number: Optional[str] = None,
        agent_ids: Optional[List[Dict]] = None,
        lead_id: Optional[int] = None,
        lead_name: Optional[str] = None,
        vendor_id: Optional[str] = None,
        vendor_config_id: Optional[str] = None,
        inbound_type: Optional[str] = None,
        cloud_agent_number: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        entity_name: Optional[str] = None,
    ) -> None:
        self.__logger.info("Creating new TalkoCDR for incoming call")
        self.__logger.debug("Request data for TalkoCDR creation: {}".format(request_data))
        self.__logger.debug(
            "Partner ID: {}, agent id: {}, service board id: {}, agent_numbers: {}, "
            "agent_ids: {}, lead_id: {}, lead_name: {}, vendor_id: {}, "
            "vendor_config_id: {}, inbound_type: {}, cloud_agent_number: {}, "
            "entity_type: {}, entity_id: {}, entity_name: {}".format(
                partner_id,
                agent_id,
                service_board_id,
                agent_number,
                agent_ids,
                lead_id,
                lead_name,
                vendor_id,
                vendor_config_id,
                inbound_type,
                cloud_agent_number,
                entity_type,
                entity_id,
                entity_name,
            )
        )

        timestamp = self.__datetime_util.get_current_time()
        call_uuid = request_data.get("uuid", str(uuid.uuid4()))
        call_id = request_data.get("call_id", "")

        raw_start_stamp = request_data.get("start_stamp", "")
        start_stamp = 0
        if raw_start_stamp:
            start_stamp = int(
                datetime.strptime(raw_start_stamp, "%Y-%m-%d %H:%M:%S").timestamp()
            )
        self.__logger.debug("Parsed start_stamp: {}".format(start_stamp))

        entity_fields = self._derive_entity_fields(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            lead_id=lead_id,
            lead_name=lead_name,
            default_entity_type=TalkoEntityType.LEAD,
        )

        cdr_model = TalkoCDR(
            action="inbound",
            calling_mode="inbound",
            date_time=timestamp,
            solution="sales",
            sr_number="SR_{}".format(call_uuid[:8]),
            customer=request_data.get("caller_id_number", ""),
            agent=agent_id,
            call_status="initiated",
            customer_status="unknown",
            agent_status="unknown",
            total_call_duration=0,
            talk_time=0,
            call_actions=[],
            call_uuid=call_uuid,
            hangup_by="none",
            partner_id=partner_id,
            call_id=call_id,
            lead_id=entity_fields["lead_id"],
            lead_name=entity_fields["lead_name"],
            entity_type=entity_fields["entity_type"],
            entity_id=entity_fields["entity_id"],
            entity_name=entity_fields["entity_name"],
            service_board_id=service_board_id,
            start_stamp=start_stamp,
            end_stamp=0,
            answer_stamp=0,
            reason_key="initiated",
            did_number=request_data.get("call_to_number", ""),
            agent_ids=agent_ids,
            agent_number=agent_number,
            vendor_id=vendor_id,
            vendor_config_id=vendor_config_id,
            inbound_type=inbound_type,
            cloud_agent_number=cloud_agent_number,
        )

        new_cdr = cdr_model.model_dump()
        await self.__repository.insert_cdr(new_cdr)
        self.__logger.info("Created new TalkoCDR for incoming call: {}".format(new_cdr))
