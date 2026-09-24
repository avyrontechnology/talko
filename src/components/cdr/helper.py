import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any

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
    def parse_mongo_timestamp(value: Any, logger: TalkoServiceLogger) -> int | None:
        """
        Convert MongoDB extended JSON timestamp to int.
        """
        logger.debug(f"Parsing MongoDB timestamp in common cdr helper: {value}")
        if isinstance(value, dict) and "$numberLong" in value:
            try:
                timestamp = int(value["$numberLong"])
                logger.debug(f"Parsed $numberLong to timestamp in common cdr helper: {timestamp}")
                return timestamp
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to parse $numberLong timestamp in common cdr helper: {str(e)}")
                return None
        elif isinstance(value, (int, float)):
            timestamp = int(value)
            logger.debug(f"Parsed numeric timestamp in common cdr helper: {timestamp}")
            return timestamp

        logger.debug("Timestamp is None or invalid in common cdr helper")
        return None

    @staticmethod
    def create_filtered_cdr(cdr: dict[str, Any], logger: TalkoServiceLogger) -> dict[str, Any]:
        """
        Create a filtered TalkoCDR dictionary with default values for missing fields.
        """
        logger.info("Creating filtered TalkoCDR in common cdr helper")
        logger.debug(f"Input TalkoCDR in common cdr helper: {cdr}")

        created_at_raw = cdr.get("created_at")
        created_at_parsed = TalkoCommonCDRHelper.parse_mongo_timestamp(created_at_raw, logger)

        call_type_value = "outgoing" if cdr.get("calling_mode") == CLICK_TO_CALL else "incoming"

        filtered_cdr = {
            "partner_id": cdr.get("partner_id"),
            "agent": cdr.get("agent") or 0,
            "lead_id": cdr.get("lead_id"),
            "entity_type": cdr.get("entity_type"),
            "entity_id": cdr.get("entity_id"),
            "workspace_id": cdr.get("workspace_id"),
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
            # DTO declares call_connected as str — normalize ints (0/1) too,
            # otherwise CDRResponse validation 500s on falsy values.
            "call_connected": str(cdr.get("call_connected") or 0),
            "lead_name": cdr.get("lead_name") or "",
            "call_type": call_type_value,
            "do_recording_url": cdr.get("do_recording_url") or "",
            "call_uuid": cdr.get("call_uuid") or "",
            "call_id": cdr.get("call_id") or "",
            "vendor_id": cdr.get("vendor_id") or "",
            "vendor_config_id": cdr.get("vendor_config_id") or "",
            "custom_fields": cdr.get("custom_fields"),
        }
        logger.debug(f"Filtered TalkoCDR in common cdr helper: {filtered_cdr}")
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
    def attach_agent_names(cdr_responses: list, agent_data: dict, logger: TalkoServiceLogger) -> None:
        """
        Attach agent names to TalkoCDR responses using agent data lookup.
        """
        logger.info("Attaching agent names to TalkoCDR responses in common cdr helper.")
        logger.debug(f"Agent data in common cdr helper: {agent_data}")
        for cdr_response in cdr_responses:
            agent_name = agent_data.get(cdr_response.agent, {}).get("name", "")
            cdr_response.action_performed_by = agent_name
            logger.debug(f"Attached agent name {agent_name} to TalkoCDR with agent id {cdr_response.agent}")

    @staticmethod
    def attach_display_names(cdr_responses: list, display_name_map: dict, logger: TalkoServiceLogger) -> None:
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
            normalized_did_number = normalize_phone_number(raw_did_number, with_plus=False) if raw_did_number else ""
            display_name = display_name_map.get(normalized_did_number) or raw_did_number
            cdr_response.display_name = display_name
            logger.debug(
                f"Attached display_name {display_name} to TalkoCDR with did_number {raw_did_number} (normalized: {normalized_did_number})"
            )


class TalkoGetCDRsHelper:
    """
    Helper class for processing CDRs in get_cdrs service method.
    """

    @staticmethod
    def process_cdrs(cdrs: list[dict], logger: TalkoServiceLogger) -> list[TalkoContract.CDRResponse]:
        """
        Transform raw CDRs into CDRResponse objects for get_cdrs.
        """
        logger.info("Processing CDRs for get_cdrs helper")
        logger.debug(f"Input CDRs in get cdr helper: {cdrs}")

        cdr_responses = []
        for cdr in cdrs:
            cdr["id"] = str(cdr["_id"])
            del cdr["_id"]

            if "customer" in cdr and not isinstance(cdr["customer"], str):
                logger.debug("Converting non-string customer field in get cdr helper: {}".format(cdr["customer"]))
                cdr["customer"] = str(cdr["customer"])

            try:
                cdr_response = TalkoContract.CDRResponse(**cdr)
                cdr_responses.append(cdr_response)
                logger.debug(f"Created CDRResponse in get cdr helper: {cdr_response}")
            except Exception as e:
                logger.error(f"Failed to create CDRResponse in get cdr helper: {str(e)}")
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
        logger.debug(f"Input CDRs: {cdrs}, is_masking_enabled: {is_masking_enabled} in get agent call logs helper")

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
                logger.debug(f"Collected agent id in get agent call logs helper: {agent_id}")

            if "customer" in cdr and not isinstance(cdr["customer"], str):
                logger.debug(
                    "Converting non-string customer field in get agent call logs helper: {}".format(cdr["customer"])
                )
                cdr["customer"] = str(cdr["customer"])

            if is_masking_enabled:
                TalkoCommonCDRHelper.mask_sensitive_data(cdr, logger)

            if "hangup_cause" in cdr:
                cdr["hangup_cause"] = TalkoGetAgentCallLogsHelper.handle_hangup_cause(cdr, logger)

            if "reason_key" in cdr:
                cdr["reason_key"] = TalkoGetAgentCallLogsHelper.handle_reason_key(cdr, logger)

            logger.debug(f"cdr data in get agent call logs helper: {cdr}")
            try:
                response = TalkoContract.CallLogResponse(**cdr)
                responses.append(response)
                logger.debug(f"Created CallLogResponse in get agent call logs helper: {response}")
            except Exception as e:
                logger.error(f"Failed to create CallLogResponse in get agent call logs helper: {str(e)}")
                raise

        logger.info("Successfully processed CDRs for get_agent_call_logs helper")
        return agent_ids, responses

    @staticmethod
    def handle_hangup_cause(cdr: dict, logger: TalkoServiceLogger) -> str | None:
        """
        Convert hangup_cause field to its enum value.
        """
        logger.info("Handling hangup_cause in get agent call logs helper")
        try:
            hangup_cause = TalkoHangupCause.from_raw(cdr["hangup_cause"]).value
            logger.debug(f"Converted hangup_cause in get agent call logs helper: {hangup_cause}")
            return hangup_cause
        except Exception as e:
            logger.error(f"Failed to convert hangup_cause in get agent call logs helper: {str(e)}")
            cdr["hangup_cause"] = TalkoCallStatus.UNKNOWN.value
            return TalkoCallStatus.UNKNOWN.value

    @staticmethod
    def handle_reason_key(cdr: dict, logger: TalkoServiceLogger) -> str | None:
        """
        Convert reason_key field to its enum value.
        """
        logger.info("Handling reason_key in get agent call logs helper")
        try:
            reason_key = TalkoReasonKey.from_raw(cdr["reason_key"]).value
            logger.debug(f"Converted reason_key in get agent call logs helper: {reason_key}")
            return reason_key
        except Exception as e:
            logger.error(f"Failed to convert reason_key in get agent call logs helper: {str(e)}")
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
        logger.info("Formatting agent call log response in get agent call logs response helper")
        logger.debug(
            f"TalkoCDR responses: {cdr_responses}, total_count: {total_count} in get agent call logs response helper"
        )

        response = {
            "call_histories": sorted(cdr_responses, key=lambda x: x.created_at, reverse=True),
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
            logger.debug(f"Formatted response in get agent call logs response helper: {formatted_response}")
            return formatted_response
        except Exception as e:
            logger.error(f"Failed to format agent call log response in get agent call logs response helper: {str(e)}")
            raise


class TalkoGetCallRecordHistoryHelper:
    """
    Helper class for processing CDRs in get_call_record_history service method.
    """

    @staticmethod
    def validate_call_status(call_status: Any | None, logger: TalkoServiceLogger) -> None:
        """
        Validate call_status field.
        """
        logger.info("Validating call_status in get call record history helper")
        logger.debug(f"Call status in get call record history helper: {call_status}")

        if call_status:
            if not isinstance(call_status, list):
                logger.error(
                    f"Invalid type for call_status in get call record history helper: {type(call_status).__name__}"
                )
                raise ValueError(f"Invalid type for call_status. Expected a list, got {type(call_status).__name__}.")

            invalid_statuses = [s for s in call_status if s not in VALID_CALL_STATUSES]
            if invalid_statuses:
                logger.error(f"Invalid call_status values in get call record history helper: {invalid_statuses}")
                raise ValueError(
                    f"Invalid call_status values: {invalid_statuses}. Allowed values are: {VALID_CALL_STATUSES}."
                )

        logger.debug("Call status validated successfully in get call record history helper")

    @staticmethod
    def build_status_match(
        call_status: list[str] | None,
        logger: TalkoServiceLogger,
    ) -> dict | None:
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
        logger.debug(f"call_status received: {call_status}")

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
            logger.debug("No derived-status values present in call_status, skipping status match")
            return None

        status_match = {"$or": or_conditions} if len(or_conditions) > 1 else or_conditions[0]
        logger.debug(f"Built derived status match in get call record history helper: {status_match}")
        return status_match

    @staticmethod
    def get_call_record_history_projection() -> dict[str, int]:
        """
        Return the default projection for call record history.
        """
        return {
            "partner_id": 1,
            "agent": 1,
            "lead_id": 1,
            "entity_type": 1,
            "entity_id": 1,
            "workspace_id": 1,
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
            f"Determining agent status for mode {mode}, TalkoCDR data in get call record history agent status helper: {cdr_data}"
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
                if str(cdr_data.get("call_connected") or 0) == "1" or cdr_data.get("talk_time", 0) > 0
                else TalkoConnectionStatus.NOT_CONNECTED.value
            )

        logger.debug(f"Agent status in get call record history agent status helper: {status}")
        return status

    @staticmethod
    def get_lead_status(cdr_data: dict, mode: str, logger: TalkoServiceLogger) -> str:
        """
        Determine lead status based on TalkoCDR data and calling mode.
        """
        logger.debug(
            f"Determining lead status for mode {mode}, TalkoCDR data in get call record history lead status helper: {cdr_data}"
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

        logger.debug(f"Lead status in get call record history lead status helper: {status}")
        return status

    @staticmethod
    def handle_call_record_history_data(
        cdr: dict,
        call_status: list[str],
        is_masking_enabled: bool,
        logger: TalkoServiceLogger,
    ) -> dict | None:
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
        logger.info("Processing TalkoCDR for call record history in get call record history data helper")
        logger.debug(
            f"Input TalkoCDR: {cdr}, call_status: {call_status}, is_masking_enabled: {is_masking_enabled} in get call record history data helper"
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
            filtered_cdr["lead_secret"] = TalkoRSAKeyHandler.encrypt_with_public_key(phone_number_data, public_key)
            logger.debug(
                "Encrypted phone number data in get call record history data helper: {}".format(
                    filtered_cdr["lead_secret"]
                )
            )
        except Exception as e:
            logger.error(f"Failed to encrypt phone number data in get call record history data helper: {str(e)}")
            raise

        logger.debug(f"Processed TalkoCDR in get call record history data helper: {filtered_cdr}")
        return filtered_cdr

    @staticmethod
    def build_call_record_history_query(
        lead_id: int | None,
        workspace_id: int,
        call_status: list[str] | None = None,
        workspace_agent_ids: list[int] | None = None,
        phone_number: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        partner_id: int | None = None,
        talk_time_range: list[str] | None = None,
        call_type: str | None = None,
        did_number: str | None = None,
        logger: TalkoServiceLogger = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> dict:
        """
        Build MongoDB query for call record history with various filters.
        """
        logger.info("Building call record history query")
        query: dict = {"partner_id": partner_id}

        TalkoGetCallRecordHistoryHelper.add_basic_filters(
            query=query,
            lead_id=lead_id,
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            workspace_agent_ids=workspace_agent_ids,
            logger=logger,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        TalkoGetCallRecordHistoryHelper.add_call_status_filter(query, call_status, logger)
        TalkoGetCallRecordHistoryHelper.add_number_filter(query, phone_number, did_number, logger)
        TalkoGetCallRecordHistoryHelper.add_talk_time_filter(query, talk_time_range, logger)
        TalkoGetCallRecordHistoryHelper.add_call_type_filter(query, call_type, logger)
        TalkoGetCallRecordHistoryHelper.add_custom_fields_filter(query, custom_fields, logger)

        logger.debug(f"Constructed query in get call record history query helper: {query}")
        return query

    @staticmethod
    def add_custom_fields_filter(
        query: dict,
        custom_fields: dict[str, Any] | None,
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
            query[f"custom_fields.{slug}"] = value
        logger.debug(f"Added custom fields filter in get call record history query helper: {custom_fields}")

    @staticmethod
    def _append_and_condition(query: dict, condition: dict, logger: TalkoServiceLogger | None = None) -> None:
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
            logger.debug(f"Appended $and condition in query helper: {condition}")

    @staticmethod
    def _normalize_entity_type(
        entity_type: str | None,
    ) -> str | None:
        if entity_type is None:
            return None

        normalized = entity_type.value if isinstance(entity_type, TalkoEntityType) else entity_type
        normalized = str(normalized).strip().lower()

        mapping = {
            "lead": TalkoEntityType.LEAD.value,
            "contact": TalkoEntityType.CONTACT.value,
        }
        return mapping.get(normalized)

    @staticmethod
    def _to_query_value(value: int | list[int]) -> int | dict:
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
        normalized_entity_type: str | None,
        entity_id: int | list[int] | None,
        lead_id: int | list[int] | None,
        logger: TalkoServiceLogger | None = None,
    ) -> dict | None:
        """
        Build entity-aware query filter.

        Rules:
        - entity_type only => filter strictly by entity_type
        - entity_type + entity_id => filter by both
        - deprecated lead_id => treated as lead
        - legacy lead rows without entity_type support can still be matched only when lead_id path is used
        - entity_id/lead_id may each be a single ID or a list of IDs (matched via $in)
        """
        effective_entity_type = TalkoGetCallRecordHistoryHelper._normalize_entity_type(normalized_entity_type)
        effective_entity_id = entity_id

        if effective_entity_type is None and effective_entity_id is None and lead_id is not None:
            effective_entity_type = TalkoEntityType.LEAD.value
            effective_entity_id = lead_id

        if effective_entity_type == TalkoEntityType.LEAD.value:
            if effective_entity_id is not None:
                query_value = TalkoGetCallRecordHistoryHelper._to_query_value(effective_entity_id)
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
                logger.debug(f"Built lead entity filter: {condition}")
            return condition

        if effective_entity_type == TalkoEntityType.CONTACT.value:
            condition = {"entity_type": TalkoEntityType.CONTACT.value}
            if effective_entity_id is not None:
                condition["entity_id"] = TalkoGetCallRecordHistoryHelper._to_query_value(effective_entity_id)
            return condition

        return None

    @staticmethod
    def add_basic_filters(
        query: dict,
        lead_id: int | None,
        workspace_id: int,
        start_time: int | None,
        end_time: int | None,
        workspace_agent_ids: list[int] | None = None,
        logger: TalkoServiceLogger = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
    ) -> None:
        """
        Add basic filters to the query.
        """
        logger.info("Adding basic filters to query")

        query["is_dialer_call"] = False
        logger.debug("Added is_dialer_call=False filter")

        normalized_entity_type = TalkoGetCallRecordHistoryHelper._normalize_entity_type(entity_type)

        entity_filter = TalkoGetCallRecordHistoryHelper._build_entity_filter(
            normalized_entity_type=normalized_entity_type,
            entity_id=entity_id,
            lead_id=lead_id,
            logger=logger,
        )
        if entity_filter:
            if "$or" in entity_filter or "$and" in entity_filter:
                TalkoGetCallRecordHistoryHelper._append_and_condition(query, entity_filter, logger)
            else:
                query.update(entity_filter)

        if workspace_id is not None:
            query["workspace_id"] = workspace_id
            logger.debug(f"Added workspace_id filter in get call record history query helper: {workspace_id}")

        if workspace_agent_ids:
            query["agent"] = {"$in": workspace_agent_ids}
            logger.debug(
                f"Added workspace_agent_ids filter in get call record history query helper: {workspace_agent_ids}"
            )

        if start_time and end_time:
            query["created_at"] = {"$gte": start_time, "$lte": end_time}
            logger.debug(f"Added time range filter in get call record history query helper: {start_time}, {end_time}")
        elif start_time:
            query["created_at"] = {"$gte": start_time}
            logger.debug(f"Added start_time filter in get call record history query helper: {start_time}")
        elif end_time:
            query["created_at"] = {"$lte": end_time}
            logger.debug(f"Added end_time filter in get call record history query helper: {end_time}")

    @staticmethod
    def add_call_status_filter(
        query: dict,
        call_status: list[str] | None,
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
                logger.debug(f"Added call_status filter in get call record history query helper: {normal_statuses}")

    @staticmethod
    def add_number_filter(
        query: dict,
        phone_number: str | None,
        did_number: str | None,
        logger: TalkoServiceLogger,
    ) -> None:
        """
        Add phone number and DID number filters to the query.
        """
        logger.info("Adding number filters to query")

        if phone_number:
            phone_safe_number = re.escape(phone_number.strip())
            query["customer"] = {"$regex": phone_safe_number, "$options": "i"}
            logger.debug(f"Added phone_number filter in get call record history query helper: {phone_safe_number}")

        if did_number:
            did_safe_number = re.escape(did_number.strip())
            query["did_number"] = {"$regex": did_safe_number, "$options": "i"}
            logger.debug(f"Added did_number filter in get call record history query helper: {did_safe_number}")

    @staticmethod
    def add_talk_time_filter(
        query: dict,
        talk_time_range: list[str] | None,
        logger: TalkoServiceLogger,
    ) -> None:
        """
        Add talk time range filter to the query.
        Uses $and append so existing entity conditions are preserved.
        """
        logger.info("Adding talk time filter to query")

        if not talk_time_range:
            logger.debug("No talk_time_range provided in get call record history query helper")
            return

        if not isinstance(talk_time_range, list):
            logger.error("talk_time_range must be a list of valid ranges in get call record history query helper")
            raise ValueError("talk_time_range must be a list of valid ranges")

        or_conditions = []
        for trange in talk_time_range:
            if trange not in TALK_TIME_RANGES:
                logger.error(f"Invalid talk_time_range in get call record history query helper: {trange}")
                raise ValueError(
                    f"Invalid talk_time_range: {trange}. Allowed values are: {list(TALK_TIME_RANGES.keys())}"
                )

            min_val, max_val = TALK_TIME_RANGES[TalkoTalkTimeRange(trange)]
            if max_val is None:
                or_conditions.append({"talk_time": {"$gte": min_val}})
                logger.debug(f"Added talk_time filter in get call record history query helper: >= {min_val}")
            else:
                or_conditions.append({"talk_time": {"$gte": min_val, "$lte": max_val}})
                logger.debug(f"Added talk_time filter in get call record history query helper: {min_val}, {max_val}")

        if or_conditions:
            TalkoGetCallRecordHistoryHelper._append_and_condition(query, {"$or": or_conditions}, logger)
            logger.debug(
                f"Added talk_time $or conditions through $and in get call record history query helper: {or_conditions}"
            )

    @staticmethod
    def add_call_type_filter(
        query: dict,
        call_type: str | None,
        logger: TalkoServiceLogger,
    ) -> None:
        """
        Add call type filter to the query.
        """
        logger.info("Adding call type filter to query")

        if call_type and call_type in ["incoming", "outgoing"]:
            query["calling_mode"] = CLICK_TO_CALL if call_type == "outgoing" else INBOUND
            logger.debug(
                "Added call_type filter in get call record history query helper: {} -> {}".format(
                    call_type, query["calling_mode"]
                )
            )
        elif call_type:
            logger.error(f"Invalid call_type in get call record history query helper: {call_type}")
            raise ValueError(f"Invalid call_type: {call_type}. Allowed values are incoming, outgoing")

    @staticmethod
    def agent_call_record_history_response(
        cdr_responses: list[TalkoContract.AgentCallRecordHistoryResponse],
        total_count: int,
        logger: TalkoServiceLogger,
    ) -> dict:
        """
        Return a single response object for agent call logs.
        """
        logger.info("Formatting agent call record history response in get call record history response helper")
        logger.debug(
            f"TalkoCDR responses: {cdr_responses}, total_count: {total_count} in get call record history response helper"
        )

        def normalize_ts(ts: int) -> int:
            if ts is None:
                logger.debug("Timestamp is None, returning 0")
                return 0
            ts = int(ts)
            normalized = ts * 1000 if ts < 1e12 else ts
            logger.debug(f"Normalized timestamp {ts} -> {normalized}")
            return normalized

        valid_records = [cdr for cdr in cdr_responses if cdr.created_at is not None]
        logger.debug(f"Valid records after filtering in get call record history response helper: {len(valid_records)}")

        sorted_records = sorted(
            valid_records,
            key=lambda cdr: normalize_ts(cdr.created_at),
            reverse=True,
        )
        logger.debug("Sorted records by created_at in get call record history response helper")

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
            logger.debug(f"Formatted response in get call record history response helper: {formatted_response}")
            return formatted_response
        except Exception as e:
            logger.error(
                f"Failed to format agent call record history response in get call record history response helper: {str(e)}"
            )
            raise


class TalkoCallLogQueryHelper:
    """
    Utility class for constructing call log queries.
    """

    @staticmethod
    def get_time_filter_query(
        filter_by: TalkoTimeFilter | None,
        logger: TalkoServiceLogger,
    ) -> dict | None:
        """
        Generate time filter query for Today, Last week, or Last month in UTC.
        """
        logger.info(f"Generating time filter query for filter_by in call log query helper: {filter_by}")

        if filter_by is None:
            logger.debug("No filter_by provided, returning None")
            return None

        now = datetime.now(UTC)
        ist_now = now.astimezone(IST)
        start_of_day_ist = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_day_utc = start_of_day_ist.astimezone(UTC)
        start_timestamp = int(start_of_day_utc.timestamp() * 1000)

        logger.debug(
            f"Time filter: {filter_by}, UTC now: {now}, IST now: {ist_now}, Start of day IST: {start_of_day_ist}, Start timestamp: {start_timestamp}"
        )

        if filter_by == TalkoTimeFilter.TODAY:
            logger.debug(f"Returning TODAY filter in call log query helper: {start_timestamp}")
            return {"$gte": start_timestamp}

        if filter_by == TalkoTimeFilter.LAST_WEEK:
            start_time = start_of_day_utc - timedelta(days=7)
            timestamp = int(start_time.timestamp() * 1000)
            logger.debug(f"Returning LAST_WEEK filter in call log query helper: {timestamp}")
            return {"$gte": timestamp}

        if filter_by == TalkoTimeFilter.LAST_MONTH:
            start_time = start_of_day_utc - timedelta(days=30)
            timestamp = int(start_time.timestamp() * 1000)
            logger.debug(f"Returning LAST_MONTH filter in call log query helper: {timestamp}")
            return {"$gte": timestamp}

        logger.debug("Invalid filter_by, returning None in call log query helper")
        return None

    @staticmethod
    def build_call_log_query(
        lead_id: int | list[int] | None,
        created_at: int | None = None,
        filter_by: TalkoTimeFilter | None = None,
        logger: TalkoServiceLogger = None,
        partner_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | list[int] | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> dict:
        """
        Build MongoDB query for call logs with strict entity filtering.
        """
        logger.info("Building call log query in call log query helper")

        normalized_entity_type = TalkoGetCallRecordHistoryHelper._normalize_entity_type(entity_type)

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
            logger.debug(f"Added created_at filter in call log query helper: {created_at}")

        if time_filter is not None:
            if created_at is not None:
                effective_timestamp = max(created_at, time_filter["$gte"])
                time_query = {"$gte": effective_timestamp}
                logger.debug(f"Combined created_at and filter_by in call log query helper: {effective_timestamp}")
            else:
                time_query = time_filter
                logger.debug(f"Applied time_filter in call log query helper: {time_filter}")

        if time_query:
            query["created_at"] = time_query
            logger.debug(f"Added time_query to query in call log query helper: {time_query}")

        # Reuses the same dot-notation builder as call-record-history — safe
        # here specifically because entity_id/lead_id above is mandatory
        # upstream (controller-enforced), so this always narrows an
        # already-tiny per-entity candidate set rather than scanning the
        # full collection.
        TalkoGetCallRecordHistoryHelper.add_custom_fields_filter(query, custom_fields, logger)

        logger.debug(f"Constructed query in call log query helper: {query}")
        return query
