import re
from typing import Any, Dict, List, Optional, Tuple, Union

from src.components.call_management.constant import DIALER_FIELD_MAPPING
from src.components.call_management.handlers.webhook_base_handler import WebhookHandler
from src.components.call_management.repository import CallRepository
from src.components.cdr.constants import EntityType
from src.components.cdr.entity_fields import derive_entity_fields
from src.components.cdr.models import CDR
from src.components.did_management.services import DidManagementService
from src.components.integrations.console.console_constants import ConsoleApiConstants
from src.components.integrations.console.maglo_client import MagloClient
from src.components.integrations.console.maglo_constants import MagloApiConstants
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.datetime_util import DateTimeUtil
from src.utils.phone_number_utils import normalize_phone_number

# Matches Tata Tele unresolved template placeholders like "$hangupcause_key" or "_number"
_UNRESOLVED_PLACEHOLDER = re.compile(r"^\$[a-zA-Z_]+$|^_[a-zA-Z_]+$")


class DialerWebhookHandler(WebhookHandler):
    """
    Handler for outbound DIALER campaign webhooks.
    Creates CDR if missing, updates otherwise.
    """

    def __init__(
        self,
        logger: HollerServiceLogger,
        call_repository: CallRepository,
        did_management_service: DidManagementService,
        vendor_type: str = "tata_tele",
    ):
        super().__init__(logger, call_repository, vendor_type)
        self.maglo_client: MagloClient = MagloClient(logger)
        self.datetime_util: DateTimeUtil = DateTimeUtil()
        self.did_management_service: DidManagementService = did_management_service
        self.logger: HollerServiceLogger = logger

    async def process_webhook(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """
        Main webhook processing: lookup, lead upsert, field mapping, CDR create/update.
        """
        self.logger.info("Received dialer webhook, payload: {}".format(payload))

        # Sanitize unresolved Tata Tele template placeholders before any processing
        payload = self._sanitize_payload(payload)

        call_id: Optional[str] = payload.get("call_id")
        uuid_val: Optional[str] = payload.get("uuid")

        self.logger.info(
            "Processing dialer webhook: call_id={}, uuid={}".format(call_id, uuid_val)
        )

        # 1. Extract & validate core identifiers
        did_number: Optional[str] = self._extract_did_number(payload)
        if not did_number:
            self.logger.error("DID number extraction failed, cannot process webhook")
            return {"status": "error", "reason": "missing_did"}

        self.logger.info("Extracted DID number: {}".format(did_number))

        customer_norm: str = self._normalize_customer_number(payload)

        self.logger.info("Normalized customer number: {}".format(customer_norm))

        # 2. Lookup DID info
        did_info: Optional[Dict[str, Any]] = await self._get_did_info(did_number)
        if not did_info:
            self.logger.error(
                "DID info lookup failed for {}, cannot process webhook".format(
                    did_number
                )
            )
            return {"status": "error", "reason": "did_not_assigned"}

        self.logger.debug("DID info retrieved: {}".format(did_info))
        partner_id: int = did_info["partner_id"]
        service_board_id: Optional[int] = did_info.get("service_board_id")
        vendor_id: Optional[str] = did_info.get("vendor_id")
        vendor_config_id: Optional[str] = did_info.get("vendor_config_id")

        self.logger.debug(
            "Partner ID: {}, Service Board ID: {}".format(partner_id, service_board_id)
        )

        # 3. Upsert IVR lead (only if customer number exists)
        upsert_res: Optional[Tuple[Any, str, Optional[int]]] = (
            await self._upsert_ivr_lead_if_needed(
                customer_norm, partner_id, service_board_id
            )
        )

        lead_id: Optional[Any] = None
        lead_name: Optional[str] = None
        assigned_agent_id: Optional[int] = None

        if upsert_res:
            lead_id, lead_name, assigned_agent_id = upsert_res

        self.logger.debug(
            "IVR lead upsert completed, lead_id: {}, lead_name: {}, assigned_agent_id: {}".format(
                lead_id, lead_name, assigned_agent_id
            )
        )

        # 4. Check for existing CDR
        existing_cdr: Optional[Dict[str, Any]] = (
            await self.call_repository.get_cdr_by_call_id_or_uuid(call_id, uuid_val)
        )

        self.logger.debug(
            "Existing CDR lookup: found={}".format(existing_cdr is not None)
        )

        entity_fields = self._derive_entity_fields(
            existing_cdr=existing_cdr,
            lead_id=lead_id,
            lead_name=lead_name,
            payload=payload,
        )

        base_fields: Dict[str, Any] = self._build_base_fields(
            partner_id,
            service_board_id,
            did_number,
            customer_norm,
            lead_id,
            lead_name,
            assigned_agent_id,
            payload,
            vendor_id,
            vendor_config_id,
            entity_fields["entity_type"],
            entity_fields["entity_id"],
            entity_fields["entity_name"],
        )

        self.logger.debug("Base fields prepared: {}".format(base_fields))
        mapped_updates: Dict[str, Any] = self._map_payload_fields(payload)

        self.logger.debug("Mapped fields from payload: {}".format(mapped_updates))

        # 6. Apply special/computed fields — now includes detailed agent logic + softphone check
        await self._apply_special_fields(mapped_updates, payload, partner_id)

        self.logger.info(
            "Applied special fields, updates now: {}".format(mapped_updates)
        )

        # 7. Combine and timestamp
        final_data: Dict[str, Any] = {**base_fields, **mapped_updates}

        self.logger.debug("Final data before timestamps: {}".format(final_data))
        self._apply_timestamps(final_data)

        # 8. Persist
        action: str = await self._persist_cdr(existing_cdr, final_data, payload)

        self.logger.info(
            "CDR persistence action: {}, final data: {}".format(action, final_data)
        )

        # 9. Relay to makun-ai (Section 16.4 live path) — best-effort, never
        # lets a relay failure surface as a failure of this webhook, since
        # our own CDR write above already succeeded.
        await self._relay_to_makunai(partner_id, payload)

        return {
            "status": action,
            "call_id": call_id or uuid_val or "unknown",
            "event_type": self._try_detect_event(payload) or "unknown",
        }

    def _sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Replace unresolved Tata Tele template placeholders with None.
        Handles both "$variable_name" and "_variable_name" patterns.
        """
        sanitized: Dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(v, str) and _UNRESOLVED_PLACEHOLDER.match(v.strip()):
                self.logger.debug(
                    "Sanitizing unresolved placeholder for key '{}': '{}'".format(k, v)
                )
                sanitized[k] = None
            else:
                sanitized[k] = v
        return sanitized

    def _extract_did_number(self, payload: Dict[str, Any]) -> Optional[str]:
        self.logger.debug("Extracting DID number from payload")
        did: Optional[str] = payload.get("caller_id_number")
        if not did:
            self.logger.error("Missing caller_id_number (expected DID)")
            return None

        # Normalize for DB lookup — no + prefix, matches stored format
        normalized: str = normalize_phone_number(did, with_plus=False)
        self.logger.debug(
            "Extracted DID number: {} → normalized: {}".format(did, normalized)
        )
        return normalized

    def _normalize_customer_number(self, payload: Dict[str, Any]) -> str:
        self.logger.debug("Normalizing customer number from payload")
        raw: str = payload.get("call_to_number", "") or ""

        # Tata Tele doesn't populate call_to_number for dialer campaigns
        if not raw:
            raw = (payload.get("broadcast_lead_fields") or {}).get(
                "Phone_Number", ""
            ) or ""
            self.logger.warning(
                "call_to_number empty, falling back to broadcast_lead_fields.Phone_Number: {}".format(
                    raw
                )
            )

        self.logger.debug("Raw customer number: {}".format(raw))
        return normalize_phone_number(raw) if raw else ""

    async def _get_did_info(self, did_number: str) -> Optional[Dict[str, Any]]:
        try:
            self.logger.debug("Looking up DID info for number: {}".format(did_number))
            record: Optional[Dict[str, Any]] = (
                await self.did_management_service.get_dids_by_number(did_number)
            )
            if not record:
                self.logger.warning("DID {} not found".format(did_number))
                return None

            partner_id: Optional[int] = record.get("partner_id")
            if partner_id is None or partner_id == 0:
                self.logger.warning("DID {} has invalid partner_id".format(did_number))
                return None

            self.logger.debug(
                "DID info found: partner_id={}, service_board_id={}".format(
                    partner_id, record.get("service_board_id")
                )
            )

            vendor_id: Optional[str] = (
                str(record.get("vendor_id")) if record.get("vendor_id") else None
            )
            vendor_config_id: Optional[str] = (
                str(record.get("vendor_config_id"))
                if record.get("vendor_config_id")
                else None
            )

            self.logger.debug(
                "DID vendor info: vendor_id={}, vendor_config_id={}".format(
                    vendor_id, vendor_config_id
                )
            )

            return {
                "partner_id": partner_id,
                "service_board_id": record.get("service_board_id"),
                "vendor_id": vendor_id,
                "vendor_config_id": vendor_config_id,
            }

        except Exception as e:
            self.logger.error("DID lookup failed for {}: {}".format(did_number, str(e)))
            return None

    async def _upsert_ivr_lead_if_needed(
        self,
        customer_number: str,
        partner_id: int,
        service_board_id: Optional[int],
    ) -> Optional[Tuple[Any, str, Optional[int]]]:
        self.logger.debug(
            "Upserting IVR lead if needed for customer: {}".format(customer_number)
        )
        if not customer_number:
            return None

        self.logger.debug("Customer number exists, proceeding with IVR lead upsert")

        try:
            response: Dict[str, Any] = await self.maglo_client.upsert_ivr_lead(
                partner_id=partner_id,
                service_board_id=service_board_id,
                phone_number=customer_number,
            )

            self.logger.debug("Maglo upsert response: {}".format(response))

            lead_id: Optional[int] = (
                response.get(MagloApiConstants.FIELD_LEAD_ID) or None
            )
            if lead_id:
                self.logger.info(
                    "IVR lead upserted/verified: lead_id={}".format(lead_id)
                )
            else:
                self.logger.warning("No lead_id returned from Maglo upsert")

            lead_name: str = response.get(MagloApiConstants.FIELD_AGENT_NAME) or ""
            lead_request_id: Optional[int] = (
                response.get(MagloApiConstants.FIELD_LEAD_REQUEST_ID) or None
            )
            assigned_agent_id: Optional[int] = response.get(
                MagloApiConstants.LEAD_RESPONSE_ASSIGNED_TO
            )

            id_data: Any = lead_request_id if lead_request_id is not None else lead_id

            self.logger.debug(
                "IVR lead upsert details - lead_id: {}, lead_name: {}, assigned_agent_id: {}, id_data: {}".format(
                    lead_id, lead_name, assigned_agent_id, id_data
                )
            )

            return id_data, lead_name, assigned_agent_id

        except Exception as e:
            self.logger.error(
                "IVR lead upsert failed for {}: {}".format(customer_number, str(e))
            )
            return None

    def _derive_entity_fields(
        self,
        existing_cdr: Optional[Dict[str, Any]],
        lead_id: Optional[Any],
        lead_name: Optional[str],
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Optional[Any]]:
        entity_type: Optional[Union[str, EntityType]] = None
        entity_id: Optional[Any] = None
        entity_name: Optional[str] = None

        if existing_cdr:
            entity_type = existing_cdr.get("entity_type")
            entity_id = existing_cdr.get("entity_id")
            entity_name = existing_cdr.get("entity_name")

        if payload:
            if entity_type is None:
                entity_type = payload.get("entity_type")
            if entity_id is None:
                entity_id = payload.get("entity_id")
            if entity_name is None:
                entity_name = payload.get("entity_name")

        return derive_entity_fields(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            lead_id=lead_id,
            lead_name=lead_name,
        )

    def _build_base_fields(
        self,
        partner_id: int,
        service_board_id: Optional[int],
        did_number: str,
        customer_norm: str,
        lead_id: Optional[int],
        lead_name: Optional[str],
        assigned_agent_id: Optional[int],
        payload: Dict[str, Any],
        vendor_id: Optional[str],
        vendor_config_id: Optional[str],
        entity_type: Optional[str],
        entity_id: Optional[Any],
        entity_name: Optional[str],
    ) -> Dict[str, Any]:
        self.logger.debug("Building base CDR fields for dialer webhook")

        timestamp: int = self.datetime_util.get_current_time()
        call_uuid: Optional[str] = payload.get("uuid")
        call_id: Optional[str] = payload.get("call_id")

        base_cdr = CDR(
            action="outbound",
            calling_mode="dialer",
            call_status=payload.get("call_status", "initiated"),
            date_time=timestamp,
            call_id=call_id,
            call_uuid=call_uuid,
            solution="sales",
            sr_number=f"SR_{call_uuid[:8]}" if call_uuid else "SR_unknown",
            customer_status="unknown",
            agent_status="unknown",
            call_actions=[],
            hangup_by="none",
            is_dialer_call=True,
            outbound_type="phone_number",
            inbound_type=None,
            partner_id=partner_id,
            service_board_id=service_board_id,
            lead_id=lead_id,
            lead_name=lead_name,
            agent=assigned_agent_id,
            vendor_id=vendor_id,
            vendor_config_id=vendor_config_id,
            did_number=did_number,
            customer=customer_norm,
            customer_no_with_prefix=payload.get("customer_no_with_prefix"),
            campaign_id=payload.get("campaign_id"),
            campaign_name=payload.get("campaign_name"),
            start_stamp=0,
            answer_stamp=0,
            end_stamp=0,
            total_call_duration=0,
            talk_time=0,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
        )

        return base_cdr.model_dump()

    def _map_payload_fields(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.debug("Mapping payload fields using DIALER_FIELD_MAPPING")
        updates: Dict[str, Any] = {}
        for src, dst in DIALER_FIELD_MAPPING.items():
            self.logger.debug("Mapping field: {} -> {}".format(src, dst))
            if src in payload and payload[src] is not None:
                self.logger.debug("Mapping value for {}: {}".format(src, payload[src]))
                updates[dst] = payload[src]
        self.logger.debug("Completed field mapping, updates: {}".format(updates))
        return updates

    async def _apply_special_fields(
        self, updates: Dict[str, Any], payload: Dict[str, Any], partner_id: int
    ) -> None:
        self.logger.debug("Applying special/computed fields based on payload content")

        self._apply_talk_time(updates, payload)
        self._apply_missed_agents(updates, payload)
        await self._apply_agent_numbers_and_type(updates, payload, partner_id)

    def _apply_talk_time(
        self, updates: Dict[str, Any], payload: Dict[str, Any]
    ) -> None:
        if "billsec" in payload or "outbound_sec" in payload:
            self.logger.debug("Calculating talk_time from billsec/outbound_sec")
            raw_val = payload.get("outbound_sec") or payload.get("billsec") or 0
            try:
                talk_time: int = int(raw_val)
            except (ValueError, TypeError):
                self.logger.warning(
                    "Could not parse talk_time from value: {}".format(raw_val)
                )
                talk_time = 0
            updates["talk_time"] = talk_time
            self.logger.debug("Calculated talk_time: {}".format(talk_time))

    def _apply_missed_agents(
        self, updates: Dict[str, Any], payload: Dict[str, Any]
    ) -> None:
        if "missed_agent" not in payload:
            return

        self.logger.debug("Processing missed_agent field for missed_agents list")
        missed: Any = payload["missed_agent"]
        self.logger.debug("Raw missed_agent value: {}".format(missed))

        if isinstance(missed, list):
            updates["missed_agents"] = missed
        else:
            updates["missed_agents"] = [missed]

        self.logger.debug(
            "Processed missed_agents list: {}".format(updates["missed_agents"])
        )

    async def _apply_agent_numbers_and_type(
        self, updates: Dict[str, Any], payload: Dict[str, Any], partner_id: int
    ) -> None:
        answered_agent_number: str = self._extract_answered_agent_number(payload)
        cloud_agent_number: str = str(payload.get("extension_c2c", "") or "")

        # Store results
        if answered_agent_number:
            updates["answered_agent_number"] = answered_agent_number
            updates["agent_number"] = answered_agent_number

        if cloud_agent_number:
            updates["cloud_agent_number"] = cloud_agent_number

        # Softphone detection
        if cloud_agent_number.strip():
            updates["outbound_type"] = "soft_phone"
            self.logger.info(
                "Softphone detected via cloud_agent_number: {}".format(
                    cloud_agent_number
                )
            )
        else:
            updates["outbound_type"] = "phone_number"
            self.logger.debug("No cloud_agent_number → outbound_type = phone_number")

        # Agent resolution - use answered first, then cloud (if it's a full number)
        phone_to_lookup: str = answered_agent_number or cloud_agent_number

        resolved_agent_id: Optional[int] = None
        if phone_to_lookup and partner_id:
            resolved_agent_id = await self._resolve_agent_from_ivr_phone(
                partner_id=partner_id,
                raw_phone=phone_to_lookup,
            )

        if resolved_agent_id:
            updates["agent"] = resolved_agent_id
            self.logger.info(
                "Resolved agent_id={} from IVR phone for partner {}".format(
                    resolved_agent_id, partner_id
                )
            )
        else:
            self.logger.info(
                "Could not resolve agent_id from IVR phone for partner {} ".format(
                    partner_id
                )
                + "(phone: {})".format(
                    phone_to_lookup[-6:] if phone_to_lookup else "none"
                )
            )

    def _extract_answered_agent_number(self, payload: Dict[str, Any]) -> str:
        """Extracts the most relevant answered agent number with priority order."""

        # Priority 1: direct answered_agent_number
        answered = self._get_from_answered_agent_field(payload)
        if answered:
            return self._slice_last_10(answered)

        # Priority 2: agent_number
        answered = self._get_from_agent_number_field(payload)
        if answered:
            return self._slice_last_10(answered)

        # Priority 3: missed_agent (first entry)
        answered = self._get_from_missed_agents(payload)
        if answered:
            return self._slice_last_10(answered)

        self.logger.info("No valid answered agent number found")
        return ""

    def _get_from_answered_agent_field(self, payload: Dict[str, Any]) -> str:
        value: Optional[Any] = payload.get("answered_agent_number")
        if value:
            self.logger.debug("Found answered_agent_number: {}".format(value))
            return str(value)
        return ""

    def _get_from_agent_number_field(self, payload: Dict[str, Any]) -> str:
        value: Optional[Any] = payload.get("agent_number")
        if value:
            self.logger.debug("Found agent_number: {}".format(value))
            return str(value)
        return ""

    def _get_from_missed_agents(self, payload: Dict[str, Any]) -> str:
        missed: Optional[Union[List, Dict]] = payload.get("missed_agent")
        if not missed:
            return ""

        if isinstance(missed, list) and missed:
            first: Any = missed[0]
            if isinstance(first, dict):
                number: Optional[Any] = first.get("agent_number") or first.get("number")
                if number:
                    self.logger.debug(
                        "Found number in missed_agents[0]: {}".format(number)
                    )
                    return str(number)
            else:
                self.logger.warning(
                    "missed_agents[0] is not dict: {}".format(type(first))
                )

        elif isinstance(missed, dict):
            number_dict: Optional[Any] = missed.get("agent_number") or missed.get(
                "number"
            )
            if number_dict:
                self.logger.debug(
                    "Found number in missed_agents dict: {}".format(number_dict)
                )
                return str(number_dict)

        self.logger.warning("Unexpected missed_agent type: {}".format(type(missed)))
        return ""

    def _slice_last_10(self, value: str) -> str:
        cleaned: str = str(value)[-10:]
        self.logger.info("Agent number after slicing last 10: {}".format(cleaned))
        return cleaned

    def _apply_timestamps(self, data: Dict[str, Any]) -> None:
        self.logger.debug(
            "Applying timestamp conversions to fields: start_stamp, answer_stamp, end_stamp"
        )
        for field in ["start_stamp", "answer_stamp", "end_stamp"]:
            val = data.get(field)
            if not val:
                data[field] = 0
                continue
            try:
                self.logger.debug(
                    "Converting timestamp for field {}: {}".format(field, val)
                )
                converted = self.datetime_util.convert_date_time(val)
                if isinstance(converted, (int, float)):
                    data[field] = int(converted)
                else:
                    self.logger.warning(
                        "Timestamp conversion for {} returned non-numeric: {}; defaulting to 0".format(
                            field, converted
                        )
                    )
                    data[field] = 0
                self.logger.debug(
                    "Converted timestamp for field {}: {}".format(field, data[field])
                )
            except Exception as e:
                self.logger.warning(
                    "Failed to parse timestamp {}: {}; defaulting to 0".format(
                        field, str(e)
                    )
                )
                data[field] = 0

        data["updated_at"] = self.datetime_util.get_current_time()

    async def _persist_cdr(
        self,
        existing: Optional[Dict[str, Any]],
        final_data: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> str:
        self.logger.debug(
            "Persisting CDR, existing record: {}, final data: {}".format(
                existing, final_data
            )
        )
        event_type: str = self._try_detect_event(payload) or "unknown"
        self.logger.debug(
            "Determined event type for persistence: {}".format(event_type)
        )

        if existing:
            self.logger.debug(
                "Existing CDR found, updating record with ID: {}".format(
                    existing["_id"]
                )
            )
            success: bool = await self.call_repository.update_cdr(
                existing["_id"], final_data
            )
            self.logger.debug(
                "CDR update result for ID {}: {}".format(existing["_id"], success)
            )
            return "updated" if success else "update_failed"

        self.logger.debug("No existing CDR found, creating new record")
        final_data["created_at"] = self.datetime_util.get_current_time()
        self.logger.debug(
            "Final data with timestamps for new CDR: {}".format(final_data)
        )
        final_data["action"] = (
            f"dialer_{event_type}" if event_type != "unknown" else "dialer_event"
        )
        self.logger.debug(
            "Final data with action field for new CDR: {}".format(final_data)
        )
        await self.call_repository.insert_cdr(final_data)
        self.logger.info(
            "New CDR created for call_id: {}, event_type: {}".format(
                final_data.get("call_id"), event_type
            )
        )
        return "created"

    def _try_detect_event(self, payload: Dict[str, Any]) -> Optional[str]:
        """Optional used only for logging and action field"""
        if payload.get("llm_analysis") or payload.get("stt"):
            return "pca"
        if (
            payload.get("disposition") is not None
            or payload.get("schedule_timestamp") is not None
        ):
            return "disposition"
        if "call_connected" in payload:
            return "connected"
        if "dialed_on_customer" in str(payload.get("call_status", "")).lower():
            return "dialed"
        # Only trigger hangup when the key is present AND has a truthy value
        if payload.get("uuid") and (
            payload.get("billsec") is not None or payload.get("hangup_cause_key")
        ):
            return "hangup"
        return None

    async def _resolve_agent_from_ivr_phone(
        self,
        partner_id: int,
        raw_phone: str,
    ) -> Optional[int]:
        """
        Normalize phone using existing utility → call console API → return agent id or None.
        """
        if not raw_phone:
            self.logger.debug("No raw phone provided → skipping agent lookup")
            return None

        normalized: str = normalize_phone_number(raw_phone)

        if not normalized:
            self.logger.warning(
                "Normalization returned empty string for raw phone: '{}'".format(
                    raw_phone
                )
            )
            return None

        if not normalized.startswith("+"):
            self.logger.warning(
                "Normalized phone does not start with + → '{}'".format(normalized)
            )

        self.logger.debug(
            "Normalized IVR phone: {} (original: {})".format(normalized, raw_phone)
        )

        try:
            agent_data: Dict[str, Any] = await self.maglo_client.get_agent_by_ivr_phone(
                partner_id=partner_id,
                ivr_phone=normalized,
            )

            agent_id: Optional[Any] = agent_data.get(ConsoleApiConstants.FIELD_AGENT_ID)
            if agent_id is not None:
                self.logger.info(
                    "Resolved agent id={} from normalized phone ending {}".format(
                        agent_id, normalized[-6:]
                    )
                )
                return int(agent_id)

            self.logger.info(
                "No agent found in console response for phone ending {}".format(
                    normalized[-6:]
                )
            )
            return None

        except Exception as e:
            self.logger.exception(
                "Failed to resolve agent from phone {} (partner {}), exception: {}".format(
                    normalized[-6:], partner_id, str(e)
                )
            )
            return None

    async def process_cdr_api_payload(
        self,
        payload: Dict[str, Any],
        call_id: Optional[str] = None,
        uuid: Optional[str] = None,
    ) -> Dict[str, str]:
        self.logger.warning("CDR API payload not supported for dialer")
        return {"status": "not_supported"}
