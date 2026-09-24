import re
from typing import Any

from src.components.call_management.constant import DIALER_FIELD_MAPPING
from src.components.call_management.handlers.webhook_base_handler import TalkoWebhookHandler
from src.components.call_management.repository import TalkoCallRepository
from src.components.cdr.constants import TalkoEntityType
from src.components.cdr.entity_fields import derive_entity_fields
from src.components.cdr.models import TalkoCDR
from src.components.did_management.services import TalkoDidManagementService
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil
from src.utils.phone_number_utils import normalize_phone_number

# Matches Tata Tele unresolved template placeholders like "$hangupcause_key" or "_number"
_UNRESOLVED_PLACEHOLDER = re.compile(r"^\$[a-zA-Z_]+$|^_[a-zA-Z_]+$")


class TalkoDialerWebhookHandler(TalkoWebhookHandler):
    """
    Handler for outbound DIALER campaign webhooks.
    Creates TalkoCDR if missing, updates otherwise.
    """

    def __init__(
        self,
        logger: TalkoServiceLogger,
        call_repository: TalkoCallRepository,
        did_management_service: TalkoDidManagementService,
        vendor_type: str = "tata_tele",
    ):
        super().__init__(logger, call_repository, vendor_type)
        self.datetime_util: TalkoDateTimeUtil = TalkoDateTimeUtil()
        self.did_management_service: TalkoDidManagementService = did_management_service
        self.logger: TalkoServiceLogger = logger

    async def process_webhook(self, payload: dict[str, Any]) -> dict[str, str]:
        """
        Main webhook processing: lookup, lead upsert, field mapping, TalkoCDR create/update.
        """
        self.logger.info(f"Received dialer webhook, payload: {payload}")

        # Sanitize unresolved Tata Tele template placeholders before any processing
        payload = self._sanitize_payload(payload)

        call_id: str | None = payload.get("call_id")
        uuid_val: str | None = payload.get("uuid")

        self.logger.info(f"Processing dialer webhook: call_id={call_id}, uuid={uuid_val}")

        # 1. Extract & validate core identifiers
        did_number: str | None = self._extract_did_number(payload)
        if not did_number:
            self.logger.error("DID number extraction failed, cannot process webhook")
            return {"status": "error", "reason": "missing_did"}

        self.logger.info(f"Extracted DID number: {did_number}")

        customer_norm: str = self._normalize_customer_number(payload)

        self.logger.info(f"Normalized customer number: {customer_norm}")

        # 2. Lookup DID info
        did_info: dict[str, Any] | None = await self._get_did_info(did_number)
        if not did_info:
            self.logger.error(f"DID info lookup failed for {did_number}, cannot process webhook")
            return {"status": "error", "reason": "did_not_assigned"}

        self.logger.debug(f"DID info retrieved: {did_info}")
        partner_id: int = did_info["partner_id"]
        workspace_id: int | None = did_info.get("workspace_id")
        vendor_id: str | None = did_info.get("vendor_id")
        vendor_config_id: str | None = did_info.get("vendor_config_id")

        self.logger.debug(f"Partner ID: {partner_id}, Workspace ID: {workspace_id}")

        # 3. Upsert IVR lead (only if customer number exists)
        upsert_res: tuple[Any, str, int | None] | None = await self._upsert_ivr_lead_if_needed(
            customer_norm, partner_id, workspace_id
        )

        lead_id: Any | None = None
        lead_name: str | None = None
        assigned_agent_id: int | None = None

        if upsert_res:
            lead_id, lead_name, assigned_agent_id = upsert_res

        self.logger.debug(
            f"IVR lead upsert completed, lead_id: {lead_id}, lead_name: {lead_name}, assigned_agent_id: {assigned_agent_id}"
        )

        # 4. Check for existing TalkoCDR
        existing_cdr: dict[str, Any] | None = await self.call_repository.get_cdr_by_call_id_or_uuid(call_id, uuid_val)

        self.logger.debug(f"Existing TalkoCDR lookup: found={existing_cdr is not None}")

        entity_fields = self._derive_entity_fields(
            existing_cdr=existing_cdr,
            lead_id=lead_id,
            lead_name=lead_name,
            payload=payload,
        )

        base_fields: dict[str, Any] = self._build_base_fields(
            partner_id,
            workspace_id,
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

        self.logger.debug(f"Base fields prepared: {base_fields}")
        mapped_updates: dict[str, Any] = self._map_payload_fields(payload)

        self.logger.debug(f"Mapped fields from payload: {mapped_updates}")

        # 6. Apply special/computed fields — now includes detailed agent logic + softphone check
        await self._apply_special_fields(mapped_updates, payload, partner_id)

        self.logger.info(f"Applied special fields, updates now: {mapped_updates}")

        # 7. Combine and timestamp
        final_data: dict[str, Any] = {**base_fields, **mapped_updates}

        self.logger.debug(f"Final data before timestamps: {final_data}")
        self._apply_timestamps(final_data)

        # 8. Persist
        action: str = await self._persist_cdr(existing_cdr, final_data, payload)

        self.logger.info(f"TalkoCDR persistence action: {action}, final data: {final_data}")

        # 9. Relay to makun-ai (Section 16.4 live path) — best-effort, never
        # lets a relay failure surface as a failure of this webhook, since
        # our own TalkoCDR write above already succeeded.
        await self._relay_to_makunai(partner_id, payload)

        return {
            "status": action,
            "call_id": call_id or uuid_val or "unknown",
            "event_type": self._try_detect_event(payload) or "unknown",
        }

    def _sanitize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Replace unresolved Tata Tele template placeholders with None.
        Handles both "$variable_name" and "_variable_name" patterns.
        """
        sanitized: dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(v, str) and _UNRESOLVED_PLACEHOLDER.match(v.strip()):
                self.logger.debug(f"Sanitizing unresolved placeholder for key '{k}': '{v}'")
                sanitized[k] = None
            else:
                sanitized[k] = v
        return sanitized

    def _extract_did_number(self, payload: dict[str, Any]) -> str | None:
        self.logger.debug("Extracting DID number from payload")
        did: str | None = payload.get("caller_id_number")
        if not did:
            self.logger.error("Missing caller_id_number (expected DID)")
            return None

        # Normalize for DB lookup — no + prefix, matches stored format
        normalized: str = normalize_phone_number(did, with_plus=False)
        self.logger.debug(f"Extracted DID number: {did} → normalized: {normalized}")
        return normalized

    def _normalize_customer_number(self, payload: dict[str, Any]) -> str:
        self.logger.debug("Normalizing customer number from payload")
        raw: str = payload.get("call_to_number", "") or ""

        # Tata Tele doesn't populate call_to_number for dialer campaigns
        if not raw:
            raw = (payload.get("broadcast_lead_fields") or {}).get("Phone_Number", "") or ""
            self.logger.warning(f"call_to_number empty, falling back to broadcast_lead_fields.Phone_Number: {raw}")

        self.logger.debug(f"Raw customer number: {raw}")
        return normalize_phone_number(raw) if raw else ""

    async def _get_did_info(self, did_number: str) -> dict[str, Any] | None:
        try:
            self.logger.debug(f"Looking up DID info for number: {did_number}")
            record: dict[str, Any] | None = await self.did_management_service.get_dids_by_number(did_number)
            if not record:
                self.logger.warning(f"DID {did_number} not found")
                return None

            partner_id: int | None = record.get("partner_id")
            if partner_id is None or partner_id == 0:
                self.logger.warning(f"DID {did_number} has invalid partner_id")
                return None

            self.logger.debug(
                "DID info found: partner_id={}, workspace_id={}".format(partner_id, record.get("workspace_id"))
            )

            vendor_id: str | None = str(record.get("vendor_id")) if record.get("vendor_id") else None
            vendor_config_id: str | None = (
                str(record.get("vendor_config_id")) if record.get("vendor_config_id") else None
            )

            self.logger.debug(f"DID vendor info: vendor_id={vendor_id}, vendor_config_id={vendor_config_id}")

            return {
                "partner_id": partner_id,
                "workspace_id": record.get("workspace_id"),
                "vendor_id": vendor_id,
                "vendor_config_id": vendor_config_id,
            }

        except Exception as e:
            self.logger.error(f"DID lookup failed for {did_number}: {str(e)}")
            return None

    async def _upsert_ivr_lead_if_needed(
        self,
        customer_number: str,
        partner_id: int,
        workspace_id: int | None,
    ) -> tuple[Any, str, int | None] | None:
        # External CRM integration removed — no lead store to upsert into.
        # Callers already treat None as "no lead resolved".
        self.logger.debug(f"Skipping IVR lead upsert for customer: {customer_number} (Maglo removed)")
        if not customer_number:
            return None
        return None

    def _derive_entity_fields(
        self,
        existing_cdr: dict[str, Any] | None,
        lead_id: Any | None,
        lead_name: str | None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any | None]:
        entity_type: str | TalkoEntityType | None = None
        entity_id: Any | None = None
        entity_name: str | None = None

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
        workspace_id: int | None,
        did_number: str,
        customer_norm: str,
        lead_id: int | None,
        lead_name: str | None,
        assigned_agent_id: int | None,
        payload: dict[str, Any],
        vendor_id: str | None,
        vendor_config_id: str | None,
        entity_type: str | None,
        entity_id: Any | None,
        entity_name: str | None,
    ) -> dict[str, Any]:
        self.logger.debug("Building base TalkoCDR fields for dialer webhook")

        timestamp: int = self.datetime_util.get_current_time()
        call_uuid: str | None = payload.get("uuid")
        call_id: str | None = payload.get("call_id")

        base_cdr = TalkoCDR(
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
            workspace_id=workspace_id,
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

    def _map_payload_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.logger.debug("Mapping payload fields using DIALER_FIELD_MAPPING")
        updates: dict[str, Any] = {}
        for src, dst in DIALER_FIELD_MAPPING.items():
            self.logger.debug(f"Mapping field: {src} -> {dst}")
            if src in payload and payload[src] is not None:
                self.logger.debug(f"Mapping value for {src}: {payload[src]}")
                updates[dst] = payload[src]
        self.logger.debug(f"Completed field mapping, updates: {updates}")
        return updates

    async def _apply_special_fields(self, updates: dict[str, Any], payload: dict[str, Any], partner_id: int) -> None:
        self.logger.debug("Applying special/computed fields based on payload content")

        self._apply_talk_time(updates, payload)
        self._apply_missed_agents(updates, payload)
        await self._apply_agent_numbers_and_type(updates, payload, partner_id)

    def _apply_talk_time(self, updates: dict[str, Any], payload: dict[str, Any]) -> None:
        if "billsec" in payload or "outbound_sec" in payload:
            self.logger.debug("Calculating talk_time from billsec/outbound_sec")
            raw_val = payload.get("outbound_sec") or payload.get("billsec") or 0
            try:
                talk_time: int = int(raw_val)
            except (ValueError, TypeError):
                self.logger.warning(f"Could not parse talk_time from value: {raw_val}")
                talk_time = 0
            updates["talk_time"] = talk_time
            self.logger.debug(f"Calculated talk_time: {talk_time}")

    def _apply_missed_agents(self, updates: dict[str, Any], payload: dict[str, Any]) -> None:
        if "missed_agent" not in payload:
            return

        self.logger.debug("Processing missed_agent field for missed_agents list")
        missed: Any = payload["missed_agent"]
        self.logger.debug(f"Raw missed_agent value: {missed}")

        if isinstance(missed, list):
            updates["missed_agents"] = missed
        else:
            updates["missed_agents"] = [missed]

        self.logger.debug("Processed missed_agents list: {}".format(updates["missed_agents"]))

    async def _apply_agent_numbers_and_type(
        self, updates: dict[str, Any], payload: dict[str, Any], partner_id: int
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
            self.logger.info(f"Softphone detected via cloud_agent_number: {cloud_agent_number}")
        else:
            updates["outbound_type"] = "phone_number"
            self.logger.debug("No cloud_agent_number → outbound_type = phone_number")

        # Agent resolution - use answered first, then cloud (if it's a full number)
        phone_to_lookup: str = answered_agent_number or cloud_agent_number

        resolved_agent_id: int | None = None
        if phone_to_lookup and partner_id:
            resolved_agent_id = await self._resolve_agent_from_ivr_phone(
                partner_id=partner_id,
                raw_phone=phone_to_lookup,
            )

        if resolved_agent_id:
            updates["agent"] = resolved_agent_id
            self.logger.info(f"Resolved agent_id={resolved_agent_id} from IVR phone for partner {partner_id}")
        else:
            self.logger.info(
                f"Could not resolve agent_id from IVR phone for partner {partner_id} "
                + "(phone: {})".format(phone_to_lookup[-6:] if phone_to_lookup else "none")
            )

    def _extract_answered_agent_number(self, payload: dict[str, Any]) -> str:
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

    def _get_from_answered_agent_field(self, payload: dict[str, Any]) -> str:
        value: Any | None = payload.get("answered_agent_number")
        if value:
            self.logger.debug(f"Found answered_agent_number: {value}")
            return str(value)
        return ""

    def _get_from_agent_number_field(self, payload: dict[str, Any]) -> str:
        value: Any | None = payload.get("agent_number")
        if value:
            self.logger.debug(f"Found agent_number: {value}")
            return str(value)
        return ""

    def _get_from_missed_agents(self, payload: dict[str, Any]) -> str:
        missed: list | dict | None = payload.get("missed_agent")
        if not missed:
            return ""

        if isinstance(missed, list) and missed:
            first: Any = missed[0]
            if isinstance(first, dict):
                number: Any | None = first.get("agent_number") or first.get("number")
                if number:
                    self.logger.debug(f"Found number in missed_agents[0]: {number}")
                    return str(number)
            else:
                self.logger.warning(f"missed_agents[0] is not dict: {type(first)}")

        elif isinstance(missed, dict):
            number_dict: Any | None = missed.get("agent_number") or missed.get("number")
            if number_dict:
                self.logger.debug(f"Found number in missed_agents dict: {number_dict}")
                return str(number_dict)

        self.logger.warning(f"Unexpected missed_agent type: {type(missed)}")
        return ""

    def _slice_last_10(self, value: str) -> str:
        cleaned: str = str(value)[-10:]
        self.logger.info(f"Agent number after slicing last 10: {cleaned}")
        return cleaned

    def _apply_timestamps(self, data: dict[str, Any]) -> None:
        self.logger.debug("Applying timestamp conversions to fields: start_stamp, answer_stamp, end_stamp")
        for field in ["start_stamp", "answer_stamp", "end_stamp"]:
            val = data.get(field)
            if not val:
                data[field] = 0
                continue
            try:
                self.logger.debug(f"Converting timestamp for field {field}: {val}")
                converted = self.datetime_util.convert_date_time(val)
                if isinstance(converted, (int, float)):
                    data[field] = int(converted)
                else:
                    self.logger.warning(
                        f"Timestamp conversion for {field} returned non-numeric: {converted}; defaulting to 0"
                    )
                    data[field] = 0
                self.logger.debug(f"Converted timestamp for field {field}: {data[field]}")
            except Exception as e:
                self.logger.warning(f"Failed to parse timestamp {field}: {str(e)}; defaulting to 0")
                data[field] = 0

        data["updated_at"] = self.datetime_util.get_current_time()

    async def _persist_cdr(
        self,
        existing: dict[str, Any] | None,
        final_data: dict[str, Any],
        payload: dict[str, Any],
    ) -> str:
        self.logger.debug(f"Persisting TalkoCDR, existing record: {existing}, final data: {final_data}")
        event_type: str = self._try_detect_event(payload) or "unknown"
        self.logger.debug(f"Determined event type for persistence: {event_type}")

        if existing:
            self.logger.debug("Existing TalkoCDR found, updating record with ID: {}".format(existing["_id"]))
            success: bool = await self.call_repository.update_cdr(existing["_id"], final_data)
            self.logger.debug("TalkoCDR update result for ID {}: {}".format(existing["_id"], success))
            return "updated" if success else "update_failed"

        self.logger.debug("No existing TalkoCDR found, creating new record")
        final_data["created_at"] = self.datetime_util.get_current_time()
        self.logger.debug(f"Final data with timestamps for new TalkoCDR: {final_data}")
        final_data["action"] = f"dialer_{event_type}" if event_type != "unknown" else "dialer_event"
        self.logger.debug(f"Final data with action field for new TalkoCDR: {final_data}")
        await self.call_repository.insert_cdr(final_data)
        self.logger.info(
            "New TalkoCDR created for call_id: {}, event_type: {}".format(final_data.get("call_id"), event_type)
        )
        return "created"

    def _try_detect_event(self, payload: dict[str, Any]) -> str | None:
        """Optional used only for logging and action field"""
        if payload.get("llm_analysis") or payload.get("stt"):
            return "pca"
        if payload.get("disposition") is not None or payload.get("schedule_timestamp") is not None:
            return "disposition"
        if "call_connected" in payload:
            return "connected"
        if "dialed_on_customer" in str(payload.get("call_status", "")).lower():
            return "dialed"
        # Only trigger hangup when the key is present AND has a truthy value
        if payload.get("uuid") and (payload.get("billsec") is not None or payload.get("hangup_cause_key")):
            return "hangup"
        return None

    async def _resolve_agent_from_ivr_phone(
        self,
        partner_id: int,
        raw_phone: str,
    ) -> int | None:
        """
        External console lookup removed — always returns None so callers
        fall back to Talko-side agent resolution.
        """
        if not raw_phone:
            self.logger.debug("No raw phone provided → skipping agent lookup")
            return None

        normalized: str = normalize_phone_number(raw_phone)

        if not normalized:
            self.logger.warning(f"Normalization returned empty string for raw phone: '{raw_phone}'")
            return None

        self.logger.debug(f"Skipping console agent lookup for {normalized[-6:]} (Maglo removed)")
        return None

    async def process_cdr_api_payload(
        self,
        payload: dict[str, Any],
        call_id: str | None = None,
        uuid: str | None = None,
    ) -> dict[str, str]:
        self.logger.warning("TalkoCDR API payload not supported for dialer")
        return {"status": "not_supported"}
