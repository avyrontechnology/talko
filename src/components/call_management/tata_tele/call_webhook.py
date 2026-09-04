import re
from typing import Any, Dict, Optional
from uuid import uuid4

from src.components.analytics.constants import INBOUND
from src.components.call_management.constant import (
    API,
    TATA_CDR_FIELD_MAPPING,
    TATA_WEBHOOK_FIELD_MAPPINGS,
    WEBHOOK,
)
from src.components.call_management.handlers.webhook_base_handler import TalkoWebhookHandler
from src.components.call_management.messages import (
    CALL_ID_MUST_BE_PROVIDED,
    CDR_NOT_FOUND,
    FAILED_TO_UPDATE,
    WEBHOOK_PAYLOAD_MISSING,
)
from src.components.call_management.repository import TalkoCallRepository
from src.components.cdr.entity_fields import derive_entity_fields
from src.components.cdr.helper import TalkoCommonCDRHelper
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil


class TalkoTataTeleWebhookHandler(TalkoWebhookHandler):
    """
    Handles webhook and API-fetched TalkoCDR data for Tata Tele, updating TalkoCDR records.
    """

    def __init__(
        self,
        logger: Any,
        call_repository: Any,
        vendor_type: str,
        call_redis_helper: Any = None,
    ) -> None:
        """
        Initialize the webhook handler.

        Args:
            logger: Logger instance for logging events.
            call_repository: Repository for accessing and updating call data.
            vendor_type: Name of the call vendor.
            call_redis_helper: Used only to dedupe missed-inbound-call
                callback scheduling (see _maybe_schedule_missed_call_callback).
                Optional — callers that never process live webhooks (e.g. the
                TalkoCDR-API polling reconciler) can omit it.
        """
        self.logger: TalkoServiceLogger = logger
        self.call_repository: TalkoCallRepository = call_repository
        self.datetime_util: TalkoDateTimeUtil = TalkoDateTimeUtil()
        self.vendor_type: str = vendor_type
        self.call_redis_helper: Any = call_redis_helper

    def _is_real_mobile_number(self, number: str) -> bool:
        """
        Returns True only if the number is a real mobile/landline number.

        Tata Tele cloud extensions (e.g. '0607182380010') are 13-digit numbers
        starting with '060' and must NOT be treated as valid agent phone numbers.
        Real Indian mobile numbers are 10 digits or +91-prefixed 12-digit numbers.

        Args:
            number: The phone number string to validate.

        Returns:
            bool: True if real mobile, False if cloud extension or invalid.
        """
        cleaned = re.sub(r"\D", "", number or "")
        # Reject Tata Tele cloud extension pattern: starts with "060", 12+ digits
        if cleaned.startswith("060") and len(cleaned) >= 12:
            return False
        return len(cleaned) >= 10

    def _preserve_entity_fields(
        self, cdr: Dict[str, Any], updates: Dict[str, Any]
    ) -> None:
        """
        Preserve entity fields from existing TalkoCDR when webhook/API payload
        does not explicitly provide them. Also backfills entity_type/entity_id/
        entity_name from a legacy lead_id/lead_name on the existing TalkoCDR when
        those were never derived (e.g. CDRs created before entity fields existed).
        """

        def _first_set(field: str) -> Any:
            value = updates.get(field)
            return value if value is not None else cdr.get(field)

        entity_fields = derive_entity_fields(
            entity_type=_first_set("entity_type"),
            entity_id=_first_set("entity_id"),
            entity_name=_first_set("entity_name"),
            lead_id=_first_set("lead_id"),
            lead_name=_first_set("lead_name"),
        )

        for field, value in entity_fields.items():
            if value is not None:
                updates[field] = value

    async def _maybe_schedule_missed_call_callback(self, cdr: Dict[str, Any]) -> None:
        """
        Hands a missed inbound call to the beat sweeper
        (missed_callback_sweeper_task, every minute), which is the normal —
        and only — scheduling flow for auto-callbacks.

        Deliberately no direct apply_async(countdown=...) here: countdown
        tasks are held in the publishing worker's in-memory timer and were
        repeatedly lost on QA (published fine, never even "received" — idle
        worker, no restart), while sweeper-dispatched immediate tasks always
        land. All partner-opt-in / agent-availability / already-connected
        decisions are still made later by the task itself (TalkoCallService.
        initiate_missed_call_callback); duplicate Tata deliveries are
        harmless — every execution converges on the deterministic task id
        plus the already-handled / exec-lock guards and at most one ever
        places a call.
        """
        call_uuid = cdr.get("call_uuid")
        if not call_uuid:
            return

        from src.components.call_management.tasks import missed_callback_task_id

        self.logger.info(
            "Missed inbound observed for call_uuid={} — leaving pickup to "
            "sweeper task_id={}".format(call_uuid, missed_callback_task_id(call_uuid))
        )

    async def process_webhook(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """
        Process Tata Tele webhook payload and update TalkoCDR.

        Args:
            payload: Webhook data from Tata Tele.

        Returns:
            Dict[str, str]: Status response.
        """
        return await self._process_payload(payload, source=WEBHOOK)

    async def process_cdr_api_payload(
        self,
        payload: Dict[str, Any],
        call_id: Optional[str] = None,
        uuid: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Process Tata Tele TalkoCDR API payload and update TalkoCDR.

        Args:
            payload: API response data.
            call_id: Call ID for the TalkoCDR (optional).
            uuid: UUID for the TalkoCDR (optional).

        Returns:
            Dict[str, str]: Status response.
        """
        return await self._process_payload(
            payload, source=API, call_id=call_id, uuid=uuid
        )

    async def _process_payload(
        self,
        payload: Dict[str, Any],
        source: str,
        call_id: Optional[str] = None,
        uuid: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Common logic to process payload (webhook or API) and update TalkoCDR.

        Args:
            payload: Data from webhook or API.
            source: Source of the payload ('webhook' or 'api').
            call_id: Call ID for API processing (optional).
            uuid: UUID for API processing (optional).

        Returns:
            Dict[str, str]: Status response.
        """
        try:
            self.logger.info(
                "Processing {} {} payload: {}".format(self.vendor_type, source, payload)
            )
            # Captured before any reassignment below (the "results" unwrap
            # is API-payload-only) — this is what gets relayed to makun-ai,
            # matching exactly what Tata sent for this webhook delivery.
            raw_payload: Dict[str, Any] = payload

            # Determine identifier
            if source == API:
                if not call_id and not uuid:
                    self.logger.error("Missing call_id or uuid in API payload")
                    raise TalkoBadRequestError(CALL_ID_MUST_BE_PROVIDED)
                identifier: str = call_id or uuid  # type: ignore
            else:
                call_id = payload.get("call_id")
                uuid = payload.get("uuid")
                if not call_id and not uuid:
                    self.logger.error(WEBHOOK_PAYLOAD_MISSING)
                    raise TalkoBadRequestError(CALL_ID_MUST_BE_PROVIDED)
                identifier = call_id or uuid  # type: ignore

            # Fetch TalkoCDR
            cdr: dict = await self.call_repository.get_cdr_by_call_id_or_uuid(
                str(call_id), uuid
            )
            if not cdr:
                self.logger.error("No TalkoCDR found for {}".format(identifier))
                raise TalkoResourceNotFound(CDR_NOT_FOUND)

            self.logger.debug("Webhook process payload cdr data: {}".format(cdr))

            # Unwrap results wrapper if present (API response format)
            if "results" in payload and len(payload["results"]) > 0:
                payload = payload["results"][0]

            self.logger.debug("Actual payload data in webhook: {}".format(payload))

            field_mappings = (
                TATA_WEBHOOK_FIELD_MAPPINGS
                if source == WEBHOOK
                else TATA_CDR_FIELD_MAPPING
            )
            self.logger.debug(
                "Process payload field mapping: {}".format(field_mappings)
            )

            # Map payload fields to TalkoCDR fields
            updates: Dict[str, Any] = {
                db_field: payload.get(payload_key)
                for payload_key, db_field in field_mappings.items()
                if payload.get(payload_key) is not None
            }

            if "answered_agent_number" in updates:
                val = updates["answered_agent_number"]
                if isinstance(val, dict):
                    # Prefer the actual phone number field if present
                    preferred = (
                        val.get("follow_me_number")
                        or val.get("number")
                        or val.get("id")
                        or val.get("name")
                        or None
                    )
                    normalized = str(preferred) if preferred else None
                    self.logger.info(
                        "Normalized answered_agent_number from dict → '{}' ".format(
                            normalized
                        )
                        + "(original keys: {}, call_id: {})".format(
                            list(val.keys()),
                            payload.get("call_id") or payload.get("uuid"),
                        )
                    )
                    updates["answered_agent_number"] = normalized

            self._preserve_entity_fields(cdr, updates)

            self.logger.debug("Map payload fields to TalkoCDR fields: {}".format(updates))

            # FIX: use `or []` to safely handle None agent_ids from DB
            agent_ids = cdr.get("agent_ids") or []
            self.logger.info("Webhook agentIds: {}".format(agent_ids))

            existing_agent_number = cdr.get("agent_number")
            self.logger.info(
                "Existing agent_number in DB: {}".format(existing_agent_number)
            )

            # FIX: Only treat existing_agent_number as valid if it is a real mobile
            # number. Cloud extensions like "0607182380010" must not block resolution.
            is_valid_existing = bool(
                existing_agent_number
                and self._is_real_mobile_number(existing_agent_number)
            )

            if not is_valid_existing:
                answered_agent_number = ""
                cloud_agent_number = ""

                # 1. Direct agent_number field from payload
                if payload.get("agent_number"):
                    self.logger.debug(
                        "Resolving answered_agent_number from payload.agent_number: {}".format(
                            payload.get("agent_number")
                        )
                    )
                    answered_agent_number = str(payload.get("agent_number"))[-10:]

                # 2. answered_agent_number field (answered calls)
                if payload.get("answered_agent_number"):
                    self.logger.debug(
                        "Resolving answered_agent_number from payload.answered_agent_number: {}".format(
                            payload.get("answered_agent_number")
                        )
                    )
                    answered_agent_number = str(payload.get("answered_agent_number"))[
                        -10:
                    ]

                # 3. missed_agent — webhook format (list of dicts with agent_number/number)
                missed_agent = payload.get("missed_agent")
                if missed_agent:
                    if isinstance(missed_agent, list) and missed_agent:
                        first_missed = missed_agent[0]
                        if isinstance(first_missed, dict):
                            # Prefer agent_number (real mobile) over number (may be extension)
                            number = first_missed.get(
                                "agent_number"
                            ) or first_missed.get("number")
                            if number:
                                answered_agent_number = str(number)[-10:]
                                self.logger.info(
                                    "Resolved answered_agent_number from missed_agent list: {}".format(
                                        answered_agent_number
                                    )
                                )
                        else:
                            self.logger.warning(
                                "missed_agent[0] is not a dict: {}".format(
                                    type(first_missed)
                                )
                            )
                    elif isinstance(missed_agent, dict):
                        number = missed_agent.get("agent_number") or missed_agent.get(
                            "number"
                        )
                        if number:
                            answered_agent_number = str(number)[-10:]
                            self.logger.info(
                                "Resolved answered_agent_number from missed_agent dict: {}".format(
                                    answered_agent_number
                                )
                            )
                    else:
                        self.logger.warning(
                            "Unexpected missed_agent type: {} → {}".format(
                                type(missed_agent), missed_agent
                            )
                        )

                self.logger.info(
                    "answered_agent_number after resolution: {}".format(
                        answered_agent_number
                    )
                )

                # FIX: strip whitespace and guard against empty string
                cloud_agent_number = str(payload.get("extension_c2c") or "").strip()

                # SOFTPHONE FLOW: agent_ids present → match agent from list
                if agent_ids:
                    for agent in agent_ids:
                        if not isinstance(agent, dict):
                            continue

                        agent_number_from_list = str(agent.get("agent_number", ""))[
                            -10:
                        ]
                        cloud_agent_number_list = str(
                            agent.get("cloud_agent_number", "")
                        ).strip()

                        self.logger.info(
                            "Comparing agent_ids entry — agent_number_sliced: {}, cloud_agent_number: {}".format(
                                agent_number_from_list, cloud_agent_number_list
                            )
                        )

                        # Primary match: real mobile number comparison
                        if (
                            answered_agent_number
                            and agent_number_from_list == answered_agent_number
                        ):
                            updates["agent"] = agent.get("agent_id")
                            updates["agent_number"] = agent.get("agent_number")
                            updates["cloud_agent_number"] = agent.get(
                                "cloud_agent_number"
                            )
                            self.logger.info(
                                "Mapped agent via agent_number match from agent_ids (softphone flow)"
                            )
                            break

                        # Secondary match: cloud extension comparison
                        # FIX: guard against empty string false-match
                        if (
                            cloud_agent_number
                            and cloud_agent_number_list
                            and cloud_agent_number_list == cloud_agent_number
                        ):
                            updates["agent"] = agent.get("agent_id")
                            updates["agent_number"] = agent.get("agent_number")
                            updates["cloud_agent_number"] = agent.get(
                                "cloud_agent_number"
                            )
                            self.logger.info(
                                "Mapped agent via cloud_agent_number match from agent_ids (softphone flow)"
                            )
                            break

                else:
                    # NORMAL PHONE NUMBER FLOW: no agent_ids → use direct fallback
                    if cdr.get("calling_mode") == INBOUND:
                        # FIX: only write if non-empty to avoid storing blank agent_number
                        if answered_agent_number:
                            updates["agent_number"] = answered_agent_number
                            self.logger.info(
                                "Using fallback agent_number for inbound call (phone_number flow): {}".format(
                                    answered_agent_number
                                )
                            )
                        else:
                            self.logger.warning(
                                "No answered_agent_number resolved for inbound call without agent_ids"
                            )

            else:
                self.logger.info(
                    "Valid real mobile agent_number exists in DB ({}); skipping agent resolution".format(
                        existing_agent_number
                    )
                )
                if "agent_number" in updates:
                    updates["agent_number"] = existing_agent_number

                if "agent" in updates:
                    updates["agent"] = cdr.get("agent")

            self.logger.info("Field conversion started: {}".format(updates))

            for ts_field in ["start_stamp", "end_stamp", "answer_stamp"]:
                if updates.get(ts_field):
                    self.logger.info("Converting {} to datetime".format(ts_field))
                    updates[ts_field] = self.datetime_util.convert_date_time(
                        updates[ts_field]
                    )

            for ts_field in ["total_call_duration", "talk_time"]:
                if updates.get(ts_field):
                    self.logger.info("Converting {} to int".format(ts_field))
                    updates[ts_field] = int(updates[ts_field])

            updates["updated_at"] = self.datetime_util.get_current_time()

            # Update TalkoCDR
            result: bool = await self.call_repository.update_cdr(cdr["_id"], updates)
            if not result:
                self.logger.error("Failed to update TalkoCDR for {}".format(identifier))
                raise TalkoBadRequestError(FAILED_TO_UPDATE)

            self.logger.info("Successfully updated TalkoCDR for {}".format(identifier))

            # AI-bridge/campaign calls complete via THIS path (Tata's
            # standard call webhook, calling_mode=clicktocall) — not
            # TalkoDialerWebhookHandler, which is a different Tata Tele product
            # we don't use for campaigns. Relay best-effort, source=WEBHOOK
            # only (never for API-polled TalkoCDR fetches, which aren't a live
            # delivery makun-ai needs to react to); our own TalkoCDR write above
            # already succeeded, so a relay failure must never surface as a
            # failure of this webhook.
            if source == WEBHOOK:
                partner_id = cdr.get("partner_id")
                if partner_id:
                    await self._relay_to_makunai(partner_id, raw_payload)

                # Push a signed webhook to the partner's configured URL, if
                # any (see src/components/partner_webhook/). Fire-and-forget
                # via Celery, same best-effort philosophy as the makun-ai
                # relay above — our TalkoCDR write already succeeded, so a
                # delivery failure must never surface as a failure of this
                # webhook. Local import avoids pulling the Celery task
                # module into every import of this handler.
                call_status = updates.get("call_status")
                if partner_id and call_status in ("answered", "missed"):
                    from src.components.partner_webhook.tasks import (
                        deliver_webhook_event,
                    )

                    deliver_webhook_event.apply_async(
                        kwargs={
                            "partner_id": partner_id,
                            "event_type": "call.completed",
                            "event_id": str(uuid4()),
                            "payload": TalkoCommonCDRHelper.create_filtered_cdr(
                                {**cdr, **updates}, self.logger
                            ),
                        }
                    )

                if (
                    updates.get("call_status") == "missed"
                    and cdr.get("action") == "inbound"
                ):
                    await self._maybe_schedule_missed_call_callback(cdr)

            return {"status": "success", "call_id": str(identifier)}

        except Exception as e:
            self.logger.error(
                "Exception occurred while updating TalkoCDR: {}".format(str(e))
            )
            raise
