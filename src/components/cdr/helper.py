import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

from cryptography.hazmat.primitives.asymmetric import rsa

from src.components.analytics.constants import CLICK_TO_CALL, INBOUND
from src.components.cdr.constants import (
    IST,
    TALK_TIME_RANGES,
    VALID_CALL_STATUSES,
    TalkoEntityType,
    TalkoTalkTimeRange,
)
from src.components.cdr.dto import TalkoContract
from src.components.cdr.utils import mask_phone_number
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.crypto_utils import TalkoRSAKeyHandler
from src.utils.enums import (
    TalkoCallStatus,
    TalkoConnectionStatus,
    TalkoHangupCause,
    TalkoNumberType,
    TalkoReasonKey,
    TalkoTimeFilter,
)
from src.utils.phone_number_utils import normalize_phone_number
from src.utils.title_case_util import TalkoTitleCaseUtil


class TalkoCommonCDRHelper:
    """
    Helper class for common TalkoCDR processing methods used across multiple service methods.
    """

    @staticmethod
    def parse_mongo_timestamp(value: Any, logger: TalkoServiceLogger) -> Optional[int]:
        """
        Convert MongoDB extended JSON timestamp to int.
        """
        logger.debug("Parsing MongoDB timestamp in common cdr helper: {}".format(value))
        if isinstance(value, dict) and "$numberLong" in value:
            try:
                timestamp = int(value["$numberLong"])
                logger.debug(
                    "Parsed $numberLong to timestamp in common cdr helper: {}".format(
                        timestamp
                    )
                )
                return timestamp
            except (ValueError, TypeError) as e:
                logger.error(
                    "Failed to parse $numberLong timestamp in common cdr helper: {}".format(
                        str(e)
                    )
                )
                return None
        elif isinstance(value, (int, float)):
            timestamp = int(value)
            logger.debug(
                "Parsed numeric timestamp in common cdr helper: {}".format(timestamp)
            )
            return timestamp

        logger.debug("Timestamp is None or invalid in common cdr helper")
        return None

    @staticmethod
    def create_filtered_cdr(
        cdr: Dict[str, Any], logger: TalkoServiceLogger
    ) -> Dict[str, Any]:
        """
        Create a filtered TalkoCDR dictionary with default values for missing fields.
        """
        logger.info("Creating filtered TalkoCDR in common cdr helper")
        logger.debug("Input TalkoCDR in common cdr helper: {}".format(cdr))

        created_at_raw = cdr.get("created_at")
        created_at_parsed = TalkoCommonCDRHelper.parse_mongo_timestamp(
            created_at_raw, logger
        )

        call_type_value = (
            "outgoing" if cdr.get("calling_mode") == CLICK_TO_CALL else "incoming"
        )

        filtered_cdr = {
            "partner_id": cdr.get("partner_id"),
            "agent": cdr.get("agent") or 0,
            "lead_id": cdr.get("lead_id"),
            "entity_type": cdr.get("entity_type"),
            "entity_id": cdr.get("entity_id"),
            "service_board_id": cdr.get("service_board_id"),
            "calling_mode": cdr.get("calling_mode"),
            "call_status": cdr.get("call_status"),
            "call_recording": cdr.get("call_recording") or "",
            "lead_number": cdr.get("customer") or "",
            "total_call_duration": cdr.get("total_call_duration") or 0,
            "talk_time": cdr.get("talk_time") or 0,
            "did_number": cdr.get("did_number") or "",
            "agent_number": cdr.get("agent_number") or "",
            "reason": cdr.get("reason") or "",
            "hangup_cause": cdr.get("hangup_cause") or "",
            "reason_key": cdr.get("reason_key") or "",
            "hangup_by": cdr.get("hangup_by") or "",
            "created_at": created_at_parsed or int(time.time() * 1000),
            "call_connected": cdr.get("call_connected") or 0,
            "lead_name": cdr.get("lead_name") or "",
            "call_type": call_type_value,
            "do_recording_url": cdr.get("do_recording_url") or "",
            "call_uuid": cdr.get("call_uuid") or "",
            "call_id": cdr.get("call_id") or "",
            "vendor_id": cdr.get("vendor_id") or "",
            "vendor_config_id": cdr.get("vendor_config_id") or "",
            "custom_fields": cdr.get("custom_fields"),
        }
        logger.debug("Filtered TalkoCDR in common cdr helper: {}".format(filtered_cdr))
        return filtered_cdr

    @staticmethod
    def mask_sensitive_data(cdr: dict, logger: TalkoServiceLogger) -> None:
        """
        Mask sensitive phone number fields in TalkoCDR.
        """
        logger.info("Masking sensitive data in TalkoCDR in common cdr helper.")
        for key in ["customer", "caller_id_number"]:
            value = cdr.get(key)
            if value is not None and value != "":
                original_value = value
                cdr[key] = mask_phone_number(value, visible_last=4, visible_first=1)
                logger.debug(f"Masked {key}: {original_value} -> {cdr[key]}")
            else:
                logger.debug(f"Skipped masking for {key}: value is None or empty.")

    @staticmethod
    def attach_agent_names(
        cdr_responses: list, agent_data: dict, logger: TalkoServiceLogger
    ) -> None:
        """
        Attach agent names to TalkoCDR responses using agent data lookup.
        """
        logger.info("Attaching agent names to TalkoCDR responses in common cdr helper.")
        logger.debug("Agent data in common cdr helper: {}".format(agent_data))
        for cdr_response in cdr_responses:
            agent_name = agent_data.get(cdr_response.agent, {}).get("name", "")
            cdr_response.action_performed_by = agent_name
            logger.debug(
                "Attached agent name {} to TalkoCDR with agent id {}".format(
                    agent_name, cdr_response.agent
                )
            )

    @staticmethod
    def attach_display_names(
        cdr_responses: list, display_name_map: dict, logger: TalkoServiceLogger
    ) -> None:
        """
        Attach display_name to TalkoCDR responses using a did_number -> display_name
        lookup. The map is keyed by normalized did_number (no '+'), so the TalkoCDR's
        did_number is normalized the same way before lookup — TalkoCDR documents may
        store did_number with a leading '+' while phone_number_management does
        not.

        Falls back to the TalkoCDR's original (un-normalized) did_number when the
        DID has no display_name set or is missing from the map entirely. If
        did_number itself is missing/empty on the TalkoCDR, display_name is "".
        """
        logger.info("Attaching display names to TalkoCDR responses in common cdr helper.")
        for cdr_response in cdr_responses:
            raw_did_number = getattr(cdr_response, "did_number", None) or ""
            normalized_did_number = (
                normalize_phone_number(raw_did_number, with_plus=False)
                if raw_did_number
                else ""
            )
            display_name = display_name_map.get(normalized_did_number) or raw_did_number
            cdr_response.display_name = display_name
            logger.debug(
                "Attached display_name {} to TalkoCDR with did_number {} (normalized: {})".format(
                    display_name, raw_did_number, normalized_did_number
                )
            )


class TalkoGetCDRsHelper:
    """
    Helper class for processing CDRs in get_cdrs service method.
    """

    @staticmethod
    def process_cdrs(
        cdrs: list[dict], logger: TalkoServiceLogger
    ) -> list[TalkoContract.CDRResponse]:
        """
        Transform raw CDRs into CDRResponse objects for get_cdrs.
        """
        logger.info("Processing CDRs for get_cdrs helper")
        logger.debug("Input CDRs in get cdr helper: {}".format(cdrs))

        cdr_responses = []
        for cdr in cdrs:
            cdr["id"] = str(cdr["_id"])
            del cdr["_id"]

            if "customer" in cdr and not isinstance(cdr["customer"], str):
                logger.debug(
                    "Converting non-string customer field in get cdr helper: {}".format(
                        cdr["customer"]
                    )
                )
                cdr["customer"] = str(cdr["customer"])

            try:
                cdr_response = TalkoContract.CDRResponse(**cdr)
                cdr_responses.append(cdr_response)
                logger.debug(
                    "Created CDRResponse in get cdr helper: {}".format(cdr_response)
                )
            except Exception as e:
                logger.error(
                    "Failed to create CDRResponse in get cdr helper: {}".format(str(e))
                )
                raise

        logger.info("Successfully processed CDRs for get_cdrs helper")
        return cdr_responses


class TalkoGetAgentCallLogsHelper:
    """
    Helper class for processing CDRs in get_agent_call_logs service method.
    """

    @staticmethod
    def process_cdrs(
        cdrs: list[dict],
        is_masking_enabled: bool,
        logger: TalkoServiceLogger,
    ) -> tuple[list[int], list[TalkoContract.CallLogResponse]]:
        """
        Clean and transform raw CDRs into CallLogResponse objects.
        """
        logger.info("Processing CDRs for get_agent_call_logs helper")
        logger.debug(
            "Input CDRs: {}, is_masking_enabled: {} in get agent call logs helper".format(
                cdrs, is_masking_enabled
            )
        )

        agent_ids = []
        responses = []

        for cdr in cdrs:
            cdr["id"] = str(cdr.pop("_id", ""))
            cdr.pop("call_flow", None)
            cdr["action_performed_by"] = ""
            cdr["event_type"] = "call"

            if "agent_name" in cdr:
                cdr.pop("agent_name")

            agent_id = cdr.get("agent")
            if agent_id is not None:
                agent_ids.append(agent_id)
                logger.debug(
                    "Collected agent id in get agent call logs helper: {}".format(
                        agent_id
                    )
                )

            if "customer" in cdr and not isinstance(cdr["customer"], str):
                logger.debug(
                    "Converting non-string customer field in get agent call logs helper: {}".format(
                        cdr["customer"]
                    )
                )
                cdr["customer"] = str(cdr["customer"])

            if is_masking_enabled:
                TalkoCommonCDRHelper.mask_sensitive_data(cdr, logger)

            if "hangup_cause" in cdr:
                cdr["hangup_cause"] = TalkoGetAgentCallLogsHelper.handle_hangup_cause(
                    cdr, logger
                )

            if "reason_key" in cdr:
                cdr["reason_key"] = TalkoGetAgentCallLogsHelper.handle_reason_key(
                    cdr, logger
                )

            logger.debug("cdr data in get agent call logs helper: {}".format(cdr))
            try:
                response = TalkoContract.CallLogResponse(**cdr)
                responses.append(response)
                logger.debug(
                    "Created CallLogResponse in get agent call logs helper: {}".format(
                        response
                    )
                )
            except Exception as e:
                logger.error(
                    "Failed to create CallLogResponse in get agent call logs helper: {}".format(
                        str(e)
                    )
                )
                raise

        logger.info("Successfully processed CDRs for get_agent_call_logs helper")
        return agent_ids, responses

    @staticmethod
    def handle_hangup_cause(cdr: dict, logger: TalkoServiceLogger) -> Optional[str]:
        """
        Convert hangup_cause field to its enum value.
        """
        logger.info("Handling hangup_cause in get agent call logs helper")
        try:
            hangup_cause = TalkoHangupCause.from_raw(cdr["hangup_cause"]).value
            logger.debug(
                "Converted hangup_cause in get agent call logs helper: {}".format(
                    hangup_cause
                )
            )
            return hangup_cause
        except Exception as e:
            logger.error(
                "Failed to convert hangup_cause in get agent call logs helper: {}".format(
                    str(e)
                )
            )
            cdr["hangup_cause"] = TalkoCallStatus.UNKNOWN.value
            return TalkoCallStatus.UNKNOWN.value

    @staticmethod
    def handle_reason_key(cdr: dict, logger: TalkoServiceLogger) -> Optional[str]:
        """
        Convert reason_key field to its enum value.
        """
        logger.info("Handling reason_key in get agent call logs helper")
        try:
            reason_key = TalkoReasonKey.from_raw(cdr["reason_key"]).value
            logger.debug(
                "Converted reason_key in get agent call logs helper: {}".format(
                    reason_key
                )
            )
            return reason_key
        except Exception as e:
            logger.error(
                "Failed to convert reason_key in get agent call logs helper: {}".format(
                    str(e)
                )
            )
            cdr["reason_key"] = TalkoCallStatus.UNKNOWN.value
            return TalkoCallStatus.UNKNOWN.value

    @staticmethod
    def agent_call_log_response(
        cdr_responses: list[TalkoContract.CallLogResponse],
        total_count: int,
        logger: TalkoServiceLogger,
    ) -> dict:
        """
        Return a single response object for agent call logs.
        """
        logger.info(
            "Formatting agent call log response in get agent call logs response helper"
        )
        logger.debug(
            "TalkoCDR responses: {}, total_count: {} in get agent call logs response helper".format(
                cdr_responses, total_count
            )
        )

        response = {
            "call_histories": sorted(
                cdr_responses, key=lambda x: x.created_at, reverse=True
            ),
            "total_count": total_count,
        }

        try:
            formatted_response = TalkoTitleCaseUtil.convert_values_to_title_case(
                response,
                exclude_keys=[
                    "call_recording",
                    "event_type",
                    "do_recording_url",
                    "call_id",
                    "call_uuid",
                ],
            )
            logger.debug(
                "Formatted response in get agent call logs response helper: {}".format(
                    formatted_response
                )
            )
            return formatted_response
        except Exception as e:
            logger.error(
                "Failed to format agent call log response in get agent call logs response helper: {}".format(
                    str(e)
                )
            )
            raise


class TalkoGetCallRecordHistoryHelper:
    """
    Helper class for processing CDRs in get_call_record_history service method.
    """

    @staticmethod
    def validate_call_status(
        call_status: Optional[Any], logger: TalkoServiceLogger
    ) -> None:
        """
        Validate call_status field.
        """
        logger.info("Validating call_status in get call record history helper")
        logger.debug(
            "Call status in get call record history helper: {}".format(call_status)
        )

        if call_status:
            if not isinstance(call_status, list):
                logger.error(
                    "Invalid type for call_status in get call record history helper: {}".format(
                        type(call_status).__name__
                    )
                )
                raise ValueError(
                    "Invalid type for call_status. Expected a list, got {}.".format(
                        type(call_status).__name__
                    )
                )

            invalid_statuses = [s for s in call_status if s not in VALID_CALL_STATUSES]
            if invalid_statuses:
                logger.error(
                    "Invalid call_status values in get call record history helper: {}".format(
                        invalid_statuses
                    )
                )
                raise ValueError(
                    "Invalid call_status values: {}. Allowed values are: {}.".format(
                        invalid_statuses, VALID_CALL_STATUSES
                    )
                )

        logger.debug(
            "Call status validated successfully in get call record history helper"
        )

    @staticmethod
    def build_status_match(
        call_status: Optional[list[str]],
        logger: TalkoServiceLogger,
    ) -> Optional[dict]:
        """
        Build a Mongo $match condition for derived agent/lead connection
        statuses (lead_connected, lead_not_connected, agent_connected,
        agent_not_connected).

        Returns None if call_status contains none of these derived
        values — "answered"/"missed" continue to be handled separately
        by add_call_status_filter, since those map directly to a real
        stored field (call_status) and don't need an $addFields stage.

        IMPORTANT: uses TalkoConnectionStatus enum values directly (note that
        TalkoConnectionStatus.NOT_CONNECTED == "not connected", with a space,
        not "not_connected") rather than deriving the expected value by
        string-splitting the status key, which was the source of a prior
        bug where *_not_connected filters never matched anything.
        """
        logger.info("Building derived status match in get call record history helper")
        logger.debug("call_status received: {}".format(call_status))

        if not call_status:
            logger.debug("No call_status provided, skipping status match")
            return None

        status_field_mapping = {
            "lead_connected": ("lead_call_status", TalkoConnectionStatus.CONNECTED.value),
            "lead_not_connected": (
                "lead_call_status",
                TalkoConnectionStatus.NOT_CONNECTED.value,
            ),
            "agent_connected": ("agent_call_status", TalkoConnectionStatus.CONNECTED.value),
            "agent_not_connected": (
                "agent_call_status",
                TalkoConnectionStatus.NOT_CONNECTED.value,
            ),
        }

        or_conditions = []
        for status in call_status:
            mapped = status_field_mapping.get(status)
            if mapped:
                key, value = mapped
                or_conditions.append({key: value})

        if not or_conditions:
            logger.debug(
                "No derived-status values present in call_status, skipping status match"
            )
            return None

        status_match = (
            {"$or": or_conditions} if len(or_conditions) > 1 else or_conditions[0]
        )
        logger.debug(
            "Built derived status match in get call record history helper: {}".format(
                status_match
            )
        )
        return status_match

    @staticmethod
    def get_call_record_history_projection() -> Dict[str, int]:
        """
        Return the default projection for call record history.
        """
        return {
            "partner_id": 1,
            "agent": 1,
            "lead_id": 1,
            "entity_type": 1,
            "entity_id": 1,
            "service_board_id": 1,
            "calling_mode": 1,
            "call_status": 1,
            "call_recording": 1,
            "call_connected": 1,
            "customer": 1,
            "total_call_duration": 1,
            "talk_time": 1,
            "did_number": 1,
            "agent_number": 1,
            "reason": 1,
            "hangup_cause": 1,
            "reason_key": 1,
            "hangup_by": 1,
            "created_at": 1,
            "lead_name": 1,
            "path_for_recording": 1,
            "call_uuid": 1,
            "call_id": 1,
            "vendor_id": 1,
            "vendor_config_id": 1,
            "custom_fields": 1,
            "_id": 1,
        }

    @staticmethod
    def get_agent_status(cdr_data: dict, mode: str, logger: TalkoServiceLogger) -> str:
        """
        Determine agent status based on TalkoCDR data and calling mode.
        """
        logger.debug(
            "Determining agent status for mode {}, TalkoCDR data in get call record history agent status helper: {}".format(
                mode, cdr_data
            )
        )
        if mode == CLICK_TO_CALL:
            status = (
                TalkoConnectionStatus.CONNECTED.value
                if cdr_data.get("total_call_duration", 0) > 0
                else TalkoConnectionStatus.NOT_CONNECTED.value
            )
        else:
            status = (
                TalkoConnectionStatus.CONNECTED.value
                if cdr_data.get("call_connected") == 1
                or cdr_data.get("talk_time", 0) > 0
                else TalkoConnectionStatus.NOT_CONNECTED.value
            )

        logger.debug(
            "Agent status in get call record history agent status helper: {}".format(
                status
            )
        )
        return status

    @staticmethod
    def get_lead_status(cdr_data: dict, mode: str, logger: TalkoServiceLogger) -> str:
        """
        Determine lead status based on TalkoCDR data and calling mode.
        """
        logger.debug(
            "Determining lead status for mode {}, TalkoCDR data in get call record history lead status helper: {}".format(
                mode, cdr_data
            )
        )
        if mode == CLICK_TO_CALL:
            status = (
                TalkoConnectionStatus.CONNECTED.value
                if cdr_data.get("talk_time", 0) > 0
                else TalkoConnectionStatus.NOT_CONNECTED.value
            )
        else:
            status = (
                TalkoConnectionStatus.CONNECTED.value
                if cdr_data.get("total_call_duration", 0) > 0
                else TalkoConnectionStatus.NOT_CONNECTED.value
            )

        logger.debug(
            "Lead status in get call record history lead status helper: {}".format(
                status
            )
        )
        return status

    @staticmethod
    def handle_call_record_history_data(
        cdr: dict,
        call_status: list[str],
        is_masking_enabled: bool,
        logger: TalkoServiceLogger,
    ) -> Optional[dict]:
        """
        Process TalkoCDR data for call record history.

        NOTE: derived-status filtering (lead_connected, lead_not_connected,
        agent_connected, agent_not_connected) is now applied at the DB
        level via build_status_match() + the repository's aggregation
        pipeline, BEFORE this function ever runs on a given record. This
        function therefore only computes agent_call_status/lead_call_status
        for the response payload and no longer drops records based on
        call_status. Do not re-add per-record filtering here — doing so
        risks the two implementations drifting out of sync.
        """
        logger.info(
            "Processing TalkoCDR for call record history in get call record history data helper"
        )
        logger.debug(
            "Input TalkoCDR: {}, call_status: {}, is_masking_enabled: {} in get call record history data helper".format(
                cdr, call_status, is_masking_enabled
            )
        )

        phone_number_data = {"phone_number": cdr.get("customer")}

        if is_masking_enabled:
            TalkoCommonCDRHelper.mask_sensitive_data(cdr, logger)

        filtered_cdr = TalkoCommonCDRHelper.create_filtered_cdr(cdr, logger)

        calling_mode = cdr.get("calling_mode", CLICK_TO_CALL)
        filtered_cdr["agent_call_status"] = TalkoGetCallRecordHistoryHelper.get_agent_status(
            filtered_cdr, calling_mode, logger
        )
        filtered_cdr["lead_call_status"] = TalkoGetCallRecordHistoryHelper.get_lead_status(
            filtered_cdr, calling_mode, logger
        )

        try:
            public_key: rsa.RSAPublicKey = TalkoRSAKeyHandler.load_public_key()
            filtered_cdr["number_type"] = TalkoNumberType.PRIMARY_NUMBER.value
            filtered_cdr["lead_secret"] = TalkoRSAKeyHandler.encrypt_with_public_key(
                phone_number_data, public_key
            )
            logger.debug(
                "Encrypted phone number data in get call record history data helper: {}".format(
                    filtered_cdr["lead_secret"]
                )
            )
        except Exception as e:
            logger.error(
                "Failed to encrypt phone number data in get call record history data helper: {}".format(
                    str(e)
                )
            )
            raise

        logger.debug(
            "Processed TalkoCDR in get call record history data helper: {}".format(
                filtered_cdr
            )
        )
        return filtered_cdr

    @staticmethod
    def build_call_record_history_query(
        lead_id: Optional[int],
        service_board_id: int,
        call_status: Optional[list[str]] = None,
        board_agent_ids: Optional[list[int]] = None,
        phone_number: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        partner_id: Optional[int] = None,
        talk_time_range: Optional[list[str]] = None,
        call_type: Optional[str] = None,
        did_number: Optional[str] = None,
        logger: TalkoServiceLogger = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """
        Build MongoDB query for call record history with various filters.
        """
        logger.info("Building call record history query")
        query: dict = {"partner_id": partner_id}

        TalkoGetCallRecordHistoryHelper.add_basic_filters(
            query=query,
            lead_id=lead_id,
            service_board_id=service_board_id,
            start_time=start_time,
            end_time=end_time,
            board_agent_ids=board_agent_ids,
            logger=logger,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        TalkoGetCallRecordHistoryHelper.add_call_status_filter(query, call_status, logger)
        TalkoGetCallRecordHistoryHelper.add_number_filter(
            query, phone_number, did_number, logger
        )
        TalkoGetCallRecordHistoryHelper.add_talk_time_filter(query, talk_time_range, logger)
        TalkoGetCallRecordHistoryHelper.add_call_type_filter(query, call_type, logger)
        TalkoGetCallRecordHistoryHelper.add_custom_fields_filter(
            query, custom_fields, logger
        )

        logger.debug(
            "Constructed query in get call record history query helper: {}".format(
                query
            )
        )
        return query

    @staticmethod
    def add_custom_fields_filter(
        query: dict,
        custom_fields: Optional[Dict[str, Any]],
        logger: TalkoServiceLogger,
    ) -> None:
        """
        Add exact-match filters on custom field values, e.g.
        {"lead_source": "Referral", "lead_score": 87} becomes
        {"custom_fields.lead_source": "Referral", "custom_fields.lead_score": 87}.
        """
        logger.info("Adding custom fields filter to query")
        if not custom_fields:
            return

        for slug, value in custom_fields.items():
            query["custom_fields.{}".format(slug)] = value
        logger.debug(
            "Added custom fields filter in get call record history query helper: {}".format(
                custom_fields
            )
        )

    @staticmethod
    def _append_and_condition(
        query: dict, condition: dict, logger: Optional[TalkoServiceLogger] = None
    ) -> None:
        """
        Append a condition safely using $and without overwriting existing query pieces.
        """
        if not condition:
            return

        existing_and = query.get("$and")
        if existing_and is None:
            query["$and"] = [condition]
        else:
            existing_and.append(condition)

        if logger:
            logger.debug(
                "Appended $and condition in query helper: {}".format(condition)
            )

    @staticmethod
    def _normalize_entity_type(
        entity_type: Optional[str],
    ) -> Optional[str]:
        if entity_type is None:
            return None

        normalized = (
            entity_type.value if isinstance(entity_type, TalkoEntityType) else entity_type
        )
        normalized = str(normalized).strip().lower()

        mapping = {
            "lead": TalkoEntityType.LEAD.value,
            "contact": TalkoEntityType.CONTACT.value,
        }
        return mapping.get(normalized)

    @staticmethod
    def _to_query_value(value: Union[int, List[int]]) -> Union[int, dict]:
        """
        Convert a scalar or list of IDs into the appropriate Mongo query value.

        A single-element list is unwrapped to a plain scalar so the resulting
        query shape is identical to the pre-existing single-ID behavior.
        """
        if isinstance(value, (list, tuple, set)):
            ids = list(value)
            return ids[0] if len(ids) == 1 else {"$in": ids}
        return value

    @staticmethod
    def _build_entity_filter(
        normalized_entity_type: Optional[str],
        entity_id: Optional[Union[int, List[int]]],
        lead_id: Optional[Union[int, List[int]]],
        logger: Optional[TalkoServiceLogger] = None,
    ) -> Optional[dict]:
        """
        Build entity-aware query filter.

        Rules:
        - entity_type only => filter strictly by entity_type
        - entity_type + entity_id => filter by both
        - deprecated lead_id => treated as lead
        - legacy lead rows without entity_type support can still be matched only when lead_id path is used
        - entity_id/lead_id may each be a single ID or a list of IDs (matched via $in)
        """
        effective_entity_type = TalkoGetCallRecordHistoryHelper._normalize_entity_type(
            normalized_entity_type
        )
        effective_entity_id = entity_id

        if (
            effective_entity_type is None
            and effective_entity_id is None
            and lead_id is not None
        ):
            effective_entity_type = TalkoEntityType.LEAD.value
            effective_entity_id = lead_id

        if effective_entity_type == TalkoEntityType.LEAD.value:
            if effective_entity_id is not None:
                query_value = TalkoGetCallRecordHistoryHelper._to_query_value(
                    effective_entity_id
                )
                condition = {
                    "$or": [
                        {
                            "entity_type": TalkoEntityType.LEAD.value,
                            "entity_id": query_value,
                        },
                        {
                            "lead_id": query_value,
                            "entity_type": {"$in": [None, ""]},  # ✅ FIXED
                        },
                    ]
                }
            else:
                condition = {"entity_type": TalkoEntityType.LEAD.value}

            if logger:
                logger.debug("Built lead entity filter: {}".format(condition))
            return condition

        if effective_entity_type == TalkoEntityType.CONTACT.value:
            condition = {"entity_type": TalkoEntityType.CONTACT.value}
            if effective_entity_id is not None:
                condition["entity_id"] = TalkoGetCallRecordHistoryHelper._to_query_value(
                    effective_entity_id
                )
            return condition

        return None

    @staticmethod
    def add_basic_filters(
        query: dict,
        lead_id: Optional[int],
        service_board_id: int,
        start_time: Optional[int],
        end_time: Optional[int],
        board_agent_ids: Optional[list[int]] = None,
        logger: TalkoServiceLogger = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
    ) -> None:
        """
        Add basic filters to the query.
        """
        logger.info("Adding basic filters to query")

        query["is_dialer_call"] = False
        logger.debug("Added is_dialer_call=False filter")

        normalized_entity_type = TalkoGetCallRecordHistoryHelper._normalize_entity_type(
            entity_type
        )

        entity_filter = TalkoGetCallRecordHistoryHelper._build_entity_filter(
            normalized_entity_type=normalized_entity_type,
            entity_id=entity_id,
            lead_id=lead_id,
            logger=logger,
        )
        if entity_filter:
            if "$or" in entity_filter or "$and" in entity_filter:
                TalkoGetCallRecordHistoryHelper._append_and_condition(
                    query, entity_filter, logger
                )
            else:
                query.update(entity_filter)

        if service_board_id is not None:
            query["service_board_id"] = service_board_id
            logger.debug(
                "Added service_board_id filter in get call record history query helper: {}".format(
                    service_board_id
                )
            )

        if board_agent_ids:
            query["agent"] = {"$in": board_agent_ids}
            logger.debug(
                "Added board_agent_ids filter in get call record history query helper: {}".format(
                    board_agent_ids
                )
            )

        if start_time and end_time:
            query["created_at"] = {"$gte": start_time, "$lte": end_time}
            logger.debug(
                "Added time range filter in get call record history query helper: {}, {}".format(
                    start_time, end_time
                )
            )
        elif start_time:
            query["created_at"] = {"$gte": start_time}
            logger.debug(
                "Added start_time filter in get call record history query helper: {}".format(
                    start_time
                )
            )
        elif end_time:
            query["created_at"] = {"$lte": end_time}
            logger.debug(
                "Added end_time filter in get call record history query helper: {}".format(
                    end_time
                )
            )

    @staticmethod
    def add_call_status_filter(
        query: dict,
        call_status: Optional[list[str]],
        logger: TalkoServiceLogger,
    ) -> None:
        """
        Add call status filter to the query.
        """
        logger.info("Adding call status filter to query")
        if call_status and isinstance(call_status, list):
            normal_statuses = [s for s in call_status if s in ["answered", "missed"]]
            if normal_statuses:
                query["call_status"] = {"$in": normal_statuses}
                logger.debug(
                    "Added call_status filter in get call record history query helper: {}".format(
                        normal_statuses
                    )
                )

    @staticmethod
    def add_number_filter(
        query: dict,
        phone_number: Optional[str],
        did_number: Optional[str],
        logger: TalkoServiceLogger,
    ) -> None:
        """
        Add phone number and DID number filters to the query.
        """
        logger.info("Adding number filters to query")

        if phone_number:
            phone_safe_number = re.escape(phone_number.strip())
            query["customer"] = {"$regex": phone_safe_number, "$options": "i"}
            logger.debug(
                "Added phone_number filter in get call record history query helper: {}".format(
                    phone_safe_number
                )
            )

        if did_number:
            did_safe_number = re.escape(did_number.strip())
            query["did_number"] = {"$regex": did_safe_number, "$options": "i"}
            logger.debug(
                "Added did_number filter in get call record history query helper: {}".format(
                    did_safe_number
                )
            )

    @staticmethod
    def add_talk_time_filter(
        query: dict,
        talk_time_range: Optional[list[str]],
        logger: TalkoServiceLogger,
    ) -> None:
        """
        Add talk time range filter to the query.
        Uses $and append so existing entity conditions are preserved.
        """
        logger.info("Adding talk time filter to query")

        if not talk_time_range:
            logger.debug(
                "No talk_time_range provided in get call record history query helper"
            )
            return

        if not isinstance(talk_time_range, list):
            logger.error(
                "talk_time_range must be a list of valid ranges in get call record history query helper"
            )
            raise ValueError("talk_time_range must be a list of valid ranges")

        or_conditions = []
        for trange in talk_time_range:
            if trange not in TALK_TIME_RANGES:
                logger.error(
                    "Invalid talk_time_range in get call record history query helper: {}".format(
                        trange
                    )
                )
                raise ValueError(
                    "Invalid talk_time_range: {}. Allowed values are: {}".format(
                        trange, list(TALK_TIME_RANGES.keys())
                    )
                )

            min_val, max_val = TALK_TIME_RANGES[TalkoTalkTimeRange(trange)]
            if max_val is None:
                or_conditions.append({"talk_time": {"$gte": min_val}})
                logger.debug(
                    "Added talk_time filter in get call record history query helper: >= {}".format(
                        min_val
                    )
                )
            else:
                or_conditions.append({"talk_time": {"$gte": min_val, "$lte": max_val}})
                logger.debug(
                    "Added talk_time filter in get call record history query helper: {}, {}".format(
                        min_val, max_val
                    )
                )

        if or_conditions:
            TalkoGetCallRecordHistoryHelper._append_and_condition(
                query, {"$or": or_conditions}, logger
            )
            logger.debug(
                "Added talk_time $or conditions through $and in get call record history query helper: {}".format(
                    or_conditions
                )
            )

    @staticmethod
    def add_call_type_filter(
        query: dict,
        call_type: Optional[str],
        logger: TalkoServiceLogger,
    ) -> None:
        """
        Add call type filter to the query.
        """
        logger.info("Adding call type filter to query")

        if call_type and call_type in ["incoming", "outgoing"]:
            query["calling_mode"] = (
                CLICK_TO_CALL if call_type == "outgoing" else INBOUND
            )
            logger.debug(
                "Added call_type filter in get call record history query helper: {} -> {}".format(
                    call_type, query["calling_mode"]
                )
            )
        elif call_type:
            logger.error(
                "Invalid call_type in get call record history query helper: {}".format(
                    call_type
                )
            )
            raise ValueError(
                "Invalid call_type: {}. Allowed values are incoming, outgoing".format(
                    call_type
                )
            )

    @staticmethod
    def agent_call_record_history_response(
        cdr_responses: list[TalkoContract.AgentCallRecordHistoryResponse],
        total_count: int,
        logger: TalkoServiceLogger,
    ) -> dict:
        """
        Return a single response object for agent call logs.
        """
        logger.info(
            "Formatting agent call record history response in get call record history response helper"
        )
        logger.debug(
            "TalkoCDR responses: {}, total_count: {} in get call record history response helper".format(
                cdr_responses, total_count
            )
        )

        def normalize_ts(ts: int) -> int:
            if ts is None:
                logger.debug("Timestamp is None, returning 0")
                return 0
            ts = int(ts)
            normalized = ts * 1000 if ts < 1e12 else ts
            logger.debug("Normalized timestamp {} -> {}".format(ts, normalized))
            return normalized

        valid_records = [cdr for cdr in cdr_responses if cdr.created_at is not None]
        logger.debug(
            "Valid records after filtering in get call record history response helper: {}".format(
                len(valid_records)
            )
        )

        sorted_records = sorted(
            valid_records,
            key=lambda cdr: normalize_ts(cdr.created_at),
            reverse=True,
        )
        logger.debug(
            "Sorted records by created_at in get call record history response helper"
        )

        response = {
            "call_record": sorted_records,
            "total_count": total_count,
        }

        try:
            formatted_response = TalkoTitleCaseUtil.convert_values_to_title_case(
                response,
                exclude_keys=[
                    "call_recording",
                    "event_type",
                    "number_type",
                    "lead_secret",
                    "do_recording_url",
                    "call_id",
                    "call_uuid",
                ],
            )
            logger.debug(
                "Formatted response in get call record history response helper: {}".format(
                    formatted_response
                )
            )
            return formatted_response
        except Exception as e:
            logger.error(
                "Failed to format agent call record history response in get call record history response helper: {}".format(
                    str(e)
                )
            )
            raise


class TalkoCallLogQueryHelper:
    """
    Utility class for constructing call log queries.
    """

    @staticmethod
    def get_time_filter_query(
        filter_by: Optional[TalkoTimeFilter],
        logger: TalkoServiceLogger,
    ) -> Optional[dict]:
        """
        Generate time filter query for Today, Last week, or Last month in UTC.
        """
        logger.info(
            "Generating time filter query for filter_by in call log query helper: {}".format(
                filter_by
            )
        )

        if filter_by is None:
            logger.debug("No filter_by provided, returning None")
            return None

        now = datetime.now(timezone.utc)
        ist_now = now.astimezone(IST)
        start_of_day_ist = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_day_utc = start_of_day_ist.astimezone(timezone.utc)
        start_timestamp = int(start_of_day_utc.timestamp() * 1000)

        logger.debug(
            "Time filter: {}, UTC now: {}, IST now: {}, Start of day IST: {}, Start timestamp: {}".format(
                filter_by, now, ist_now, start_of_day_ist, start_timestamp
            )
        )

        if filter_by == TalkoTimeFilter.TODAY:
            logger.debug(
                "Returning TODAY filter in call log query helper: {}".format(
                    start_timestamp
                )
            )
            return {"$gte": start_timestamp}

        if filter_by == TalkoTimeFilter.LAST_WEEK:
            start_time = start_of_day_utc - timedelta(days=7)
            timestamp = int(start_time.timestamp() * 1000)
            logger.debug(
                "Returning LAST_WEEK filter in call log query helper: {}".format(
                    timestamp
                )
            )
            return {"$gte": timestamp}

        if filter_by == TalkoTimeFilter.LAST_MONTH:
            start_time = start_of_day_utc - timedelta(days=30)
            timestamp = int(start_time.timestamp() * 1000)
            logger.debug(
                "Returning LAST_MONTH filter in call log query helper: {}".format(
                    timestamp
                )
            )
            return {"$gte": timestamp}

        logger.debug("Invalid filter_by, returning None in call log query helper")
        return None

    @staticmethod
    def build_call_log_query(
        lead_id: Optional[Union[int, List[int]]],
        created_at: Optional[int] = None,
        filter_by: Optional[TalkoTimeFilter] = None,
        logger: TalkoServiceLogger = None,
        partner_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[Union[int, List[int]]] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """
        Build MongoDB query for call logs with strict entity filtering.
        """
        logger.info("Building call log query in call log query helper")

        normalized_entity_type = TalkoGetCallRecordHistoryHelper._normalize_entity_type(
            entity_type
        )

        query = {}
        if partner_id is not None:
            query["partner_id"] = partner_id

        entity_filter = TalkoGetCallRecordHistoryHelper._build_entity_filter(
            normalized_entity_type=normalized_entity_type,
            entity_id=entity_id,
            lead_id=lead_id,
            logger=logger,
        )
        if entity_filter:
            if "$or" in entity_filter or "$and" in entity_filter:
                query["$and"] = [entity_filter]
            else:
                query.update(entity_filter)

        time_filter = TalkoCallLogQueryHelper.get_time_filter_query(filter_by, logger)
        time_query = {}

        if created_at is not None:
            time_query["$gt"] = created_at
            logger.debug(
                "Added created_at filter in call log query helper: {}".format(
                    created_at
                )
            )

        if time_filter is not None:
            if created_at is not None:
                effective_timestamp = max(created_at, time_filter["$gte"])
                time_query = {"$gte": effective_timestamp}
                logger.debug(
                    "Combined created_at and filter_by in call log query helper: {}".format(
                        effective_timestamp
                    )
                )
            else:
                time_query = time_filter
                logger.debug(
                    "Applied time_filter in call log query helper: {}".format(
                        time_filter
                    )
                )

        if time_query:
            query["created_at"] = time_query
            logger.debug(
                "Added time_query to query in call log query helper: {}".format(
                    time_query
                )
            )

        # Reuses the same dot-notation builder as call-record-history — safe
        # here specifically because entity_id/lead_id above is mandatory
        # upstream (controller-enforced), so this always narrows an
        # already-tiny per-entity candidate set rather than scanning the
        # full collection.
        TalkoGetCallRecordHistoryHelper.add_custom_fields_filter(
            query, custom_fields, logger
        )

        logger.debug("Constructed query in call log query helper: {}".format(query))
        return query
