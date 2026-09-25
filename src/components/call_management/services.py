import asyncio
import time
import traceback
import uuid
from typing import Any

import httpx
from bson import ObjectId
from bson.errors import InvalidId

from src.components.call_agent_map.repository import TalkoAgentMappingRepository
from src.components.call_agent_map.services import TalkoAgentMappingService
from src.components.call_management.agent_dialplan_resolver import (
    TalkoAgentDialPlanResolver,
    TalkoDialplanResponseBuilder,
)
from src.components.call_management.constant import AI_BRIDGE_VENDOR_CONFIG_ID
from src.components.call_management.dto import TalkoContract as call_contract
from src.components.call_management.handlers.webhook_base_handler import TalkoWebhookHandler
from src.components.call_management.helper import TalkoCallProcessorHelper
from src.components.call_management.messages import (
    CALL_HANGUP_INITIATED,
    CALL_PLACED_SUCCESSFULLY,
    NO_VENDOR_ID_ASSIGNED_TO_PARTNER,
)
from src.components.call_management.redis_helper import TalkoCallRedisHelper
from src.components.call_management.repository import TalkoCallRepository
from src.components.call_management.tata_tele.call_dialer import TalkoDialerWebhookHandler
from src.components.call_management.tata_tele.call_webhook import TalkoTataTeleWebhookHandler
from src.components.call_operation.cdr_update import TalkoCDRUpdateTask
from src.components.call_operation.vendor_cdr_gateway import TalkoVendorCDRGateway
from src.components.cdr.constants import TalkoEntityType
from src.components.cdr.dto import TalkoContract as cdr_contract
from src.components.cdr.entity_fields import derive_entity_fields
from src.components.cdr.repository import TalkoCDRRepository
from src.components.did_management.constants import TalkoDIDType
from src.components.did_management.repositories import TalkoDidRepository
from src.components.did_management.services import TalkoDidManagementService
from src.components.inbound_call_events.publisher import TalkoInboundCallEventPublisher
from src.components.partner_config.repository import TalkoPartnerConfigRepository
from src.components.pstn.voiceai_relay import VOICEAI_AGENT_ID_KEY
from src.components.vendor_config.repository import TalkoVendorConfigRepository
from src.core.environment import TalkoENV
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.assignment_strategy import TalkoRoundRobinAssignment
from src.utils.datetime_util import TalkoDateTimeUtil
from src.utils.enums import TalkoVendorType
from src.utils.phone_number_utils import normalize_phone_number
from src.utils.title_case_util import TalkoTitleCaseUtil


class TalkoCallService:
    """
    Service responsible for initiating partner calls via vendor APIs, managing
    partner configurations, DID assignments, and call logging (TalkoCDR).
    """

    def __init__(
        self,
        repository: TalkoCallRepository,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
        partner_config_repository: TalkoPartnerConfigRepository,
        vendor_config_repository: TalkoVendorConfigRepository,
        agent_mapping_service: TalkoAgentMappingService,
        agent_mapping_repository: TalkoAgentMappingRepository,
        did_management_service: TalkoDidManagementService,
        cdr_update_task: TalkoCDRUpdateTask,
        vendor_cdr_gateway: TalkoVendorCDRGateway,
        cdr_repository: TalkoCDRRepository,
        call_redis_helper: TalkoCallRedisHelper,
        did_repository: TalkoDidRepository,  # same as TalkoPSTNBridgeService — for agent_id resolution
        inbound_call_event_publisher: TalkoInboundCallEventPublisher,
        channel_pool_service: Any = None,
        telephony_client: Any = None,
        telephony_bridge: Any = None,
        billing_service: Any = None,
    ):
        """
        Initializes the TalkoCallService with necessary repositories and utilities.

        Args:
            repository (TalkoCallRepository): Repository for TalkoCDR and related DB operations.
            logger (TalkoServiceLogger): Logger for logging.
            datetime_util (TalkoDateTimeUtil): Utility for datetime operations.
            partner_config_repository (TalkoPartnerConfigRepository): Repo for partner configs.
            vendor_config_repository (TalkoVendorConfigRepository): Repo for vendor configs.
            agent_mapping_service (TalkoAgentMappingService): Service for agent DID mapping.
        """
        self.__repository: TalkoCallRepository = repository
        self.__logger: TalkoServiceLogger = logger
        self.__datetime_util: TalkoDateTimeUtil = datetime_util
        self.__round_robin: TalkoRoundRobinAssignment = TalkoRoundRobinAssignment()
        self.__partner_config_repo: TalkoPartnerConfigRepository = partner_config_repository
        self.__vendor_config_repository: TalkoVendorConfigRepository = vendor_config_repository
        self.__agent_mapping_service: TalkoAgentMappingService = agent_mapping_service
        self.__agent_mapping_repository: TalkoAgentMappingRepository = agent_mapping_repository
        self.__did_management_service: TalkoDidManagementService = did_management_service
        self.__helper: TalkoCallProcessorHelper = TalkoCallProcessorHelper(
            repository=self.__repository,
            logger=self.__logger,
            datetime_util=self.__datetime_util,
            partner_config_repo=self.__partner_config_repo,
            vendor_config_repo=self.__vendor_config_repository,
            agent_mapping_service=self.__agent_mapping_service,
            agent_mapping_repository=self.__agent_mapping_repository,
            did_management_service=self.__did_management_service,
        )
        # gRPC disabled for now — resolver tolerates None (skips availability).
        # user_service_client=TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.USER),
        try:
            _user_service_client: Any = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.USER)
        except Exception:
            _user_service_client = None
        self.__dialplan_resolver = TalkoAgentDialPlanResolver(
            agent_mapping_repo=self.__agent_mapping_repository,
            logger=self.__logger,
            user_service_client=_user_service_client,
        )
        self.__response_builder = TalkoDialplanResponseBuilder()
        self.__vendor_cdr_gateway: TalkoVendorCDRGateway = vendor_cdr_gateway
        self.__cdr_update_task: TalkoCDRUpdateTask = cdr_update_task
        self.__cdr_repository = cdr_repository
        self.__redis_helper = call_redis_helper
        self.__did_repository: TalkoDidRepository = did_repository  # for agent_id resolution in _pre_create_session
        self.__inbound_call_event_publisher: TalkoInboundCallEventPublisher = inbound_call_event_publisher
        self.__channel_pool_service: Any = channel_pool_service
        self.__telephony_client: Any = telephony_client
        self.__telephony_bridge: Any = telephony_bridge
        self.__billing_service: Any = billing_service

    def _derive_inbound_entity_fields(
        self,
        entity_type: str | None = None,
        entity_id: int | None = None,
        entity_name: str | None = None,
        lead_id: int | None = None,
        lead_name: str | None = None,
    ) -> tuple[str | None, int | None, str | None]:
        """
        Normalize inbound entity fields for compatibility.
        """
        if entity_type is not None and not isinstance(entity_type, TalkoEntityType):
            try:
                entity_type = TalkoEntityType(entity_type)
            except ValueError:
                self.__logger.warning(f"Invalid entity_type '{entity_type}' received in inbound flow. Ignoring.")
                entity_type = None

        entity_fields = derive_entity_fields(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            lead_id=lead_id,
            lead_name=lead_name,
        )

        return (
            entity_fields["entity_type"],
            entity_fields["entity_id"],
            entity_fields["entity_name"],
        )

    async def initiate_call(
        self,
        call_data: call_contract.CallCreate,
        user_id: int,
        partner_id: int,
        notify_outbound_event: bool = False,
    ) -> call_contract.CallResponse:
        """
        Initiates an outbound call through the assigned vendor, logs a Call Detail Record (TalkoCDR),
        and returns call details.

        When enable_ai_bridge=True, fires a background task (_pre_create_session)
        immediately after getting call_id from Tata. This pre-creates a makun-ai
        session while Tata dials the customer (ringing window = 2-5 seconds), so
        the LiveKit room and worker are warm before the customer answers.

        The existing pending_context flow is kept unchanged for non-AI-bridge calls,
        and as a fallback if pre-session creation fails.

        Args:
            call_data (call_contract.CallCreate): Call request data.
            user_id (int): User initiating the call.
            partner_id (int): Partner associated with the call.
            notify_outbound_event (bool): Only True for scheduler-driven
                missed-call callbacks (see initiate_missed_call_callback).
                Manual outbound API calls leave this False so no
                outbound_call websocket popup is emitted for them.

        Returns:
            call_contract.CallResponse: Call details including IDs, numbers, status, and timestamps.

        Raises:
            TalkoResourceNotFound: If no vendor is assigned to the partner.
            Exception: For vendor errors or unexpected failures.
        """
        try:
            self.__logger.info("Initial call service for partner started.")
            self.__logger.debug(f"Call data received: {call_data}")

            if call_data.encryption_enabled or call_data.lead_secret:
                decrypted_lead_data: dict = self.__helper.decrypt_lead_data(call_data)

                self.__logger.debug(f"Decrypted lead data: {decrypted_lead_data}")

                # Select number from decrypted data based on number_type
                to_number: str = self.__helper.extract_to_number(call_data, decrypted_lead_data)
            else:
                if not call_data.to_number:
                    raise ValueError("to_number must be provided if encryption is disabled")
                to_number = call_data.to_number

            # partner changes
            partner_config: dict[str, Any] = await self.__helper.get_partner_config(partner_id)

            vendor_id: str | None = partner_config.get("vendor_id")
            if not vendor_id:
                raise TalkoResourceNotFound(NO_VENDOR_ID_ASSIGNED_TO_PARTNER)

            vendor_config_id: str | None = (
                partner_config.get("ai_vendor_config_id") if call_data.enable_ai_bridge else None
            ) or partner_config.get("vendor_config_id")
            if not vendor_config_id:
                raise TalkoResourceNotFound("No vendor_config_id assigned to partner.")
            if self.__billing_service is not None:
                try:
                    ledger = await self.__billing_service.get_ledger(partner_id)
                    self.__billing_service.check_balance(
                        ledger.model_dump() if hasattr(ledger, "model_dump") else ledger
                    )
                except TalkoResourceNotFound:
                    pass  # no ledger = unlimited (fail-open for legacy partners)
                except TalkoBadRequestError:
                    raise
                except Exception as bill_e:
                    self.__logger.error(f"Billing guard failed open: {str(bill_e)}")
            pool_acquired = False
            if self.__channel_pool_service is not None:
                try:
                    await self.__channel_pool_service.acquire(vendor_config_id)
                    pool_acquired = True
                except Exception as pool_e:
                    from src.components.call_management.channel_pool import (
                        TalkoChannelPoolExhausted,
                    )

                    if isinstance(pool_e, TalkoChannelPoolExhausted):
                        raise TalkoBadRequestError(str(pool_e))
                    self.__logger.error(f"Channel pool acquire failed (fail-open): {str(pool_e)}")
            if call_data.dedicated_did and not call_data.enable_ai_bridge:
                await self.__helper.validate_given_did(call_data.dedicated_did, partner_id, call_data.workspace_id)
                from_number = call_data.dedicated_did
                self.__logger.info(f"Using provided dedicated DID: {from_number} for call initiation")
            elif not call_data.enable_ai_bridge:
                from_number: str = await self.__helper.select_did(
                    partner_config, partner_id, user_id, call_data.workspace_id
                )
                self.__logger.info(f"Selected DID: {from_number} for call initiation using round-robin")
            else:
                await self.__helper.validate_given_did(call_data.dedicated_did, partner_id, call_data.workspace_id)
                from_number = call_data.dedicated_did
                self.__logger.info(f"AI Bridge enabled, using dedicated DID: {from_number} for call initiation")

            vendor_handler: Any = await self.__helper.get_vendor_handler(vendor_id, vendor_config_id)

            self.__logger.debug(f"Vendor handler obtained: {vendor_handler} for vendor_id: {vendor_id}")

            agent_number: str | None = (
                call_data.cloud_agent_number if call_data.cloud_agent_number else call_data.agent_number
            )

            call_id: str = ""
            try:
                vendor_response: dict[str, Any] = await vendor_handler.make_call(
                    to_number,
                    from_number,
                    call_data.call_url,
                    agent_number,
                    enable_ai_bridge=call_data.enable_ai_bridge or False,
                )
                call_status: str = vendor_response.get("status", "initiated")
                call_id: str = str(vendor_response.get("call_id", ""))
            except ValueError as e:
                if pool_acquired and self.__channel_pool_service is not None:
                    try:
                        await self.__channel_pool_service.release(vendor_config_id)
                    except Exception:
                        pass
                self.__logger.error(f"Vendor call failed: {str(e)}")
                raise

            self.__logger.debug(f"Vendor response received: {vendor_response} for call_id: {call_id}")

            call_uuid: str = str(uuid.uuid4())
            timestamp: int = self.__datetime_util.get_current_time()

            cdr_dict: dict[str, Any] = self.__helper.prepare_cdr(
                call_data,
                call_id,
                call_uuid,
                call_status,
                timestamp,
                partner_id,
                user_id,
                from_number,
                to_number,
                vendor_id,
                vendor_config_id,
            )

            self.__logger.debug(f"Prepared TalkoCDR for call initiation: {cdr_dict}")
            cdr_id: str = await self.__repository.insert_cdr(cdr_dict)

            self.__logger.debug(f"TalkoCDR inserted with ID: {cdr_id}")

            response: dict[str, Any] = {
                "id": cdr_id,
                "call_uuid": call_uuid,
                "to_number": to_number,
                "from_number": from_number,
                "partner_id": partner_id,
                "vendor_id": str(vendor_id),
                "call_status": call_status,
                "created_at": timestamp,
                "updated_at": timestamp,
            }

            if to_number:
                # call_id is routinely empty here — Tata's live click-to-call
                # API only returns a ref_id synchronously and assigns the real
                # call_id later (see _backfill_real_vendor_call_id's docstring
                # in pstn/services.py). store_key already falls back to
                # normalized_to for that case, so pending-context storage and
                # AI-bridge pre-warm must key off to_number being present, not
                # call_id — gating on call_id made this whole block silently
                # unreachable for every live outbound call.
                #
                # Must match the normalization handle_call() applies to Tata's
                # start-event "to" field (pstn/services.py) when looking up
                # outbound_room:<to_number> — plain .lstrip("+") let a leading
                # zero / missing country code / spaces desync the two keys.
                normalized_to = normalize_phone_number(to_number, with_plus=False)
                store_key = call_id if (call_id and call_id != "None") else normalized_to

                # cdr_id (this TalkoCDR row's own _id, NOT Tata's call_id — that's
                # routinely empty here for AI-bridge calls, see above) rides
                # along in context_data all the way to the voice worker and
                # back over the LiveKit data channel (pstn/services.py
                # _backfill_real_vendor_call_id), so that once the real
                # vendor call_id is resolved, THIS row's call_id can be
                # updated in place. Without it, get_cdr_by_call_id_or_uuid
                # can never match this row when Tata's webhook later arrives
                # (it has neither the empty call_id nor Talko's own
                # self-generated call_uuid) — the webhook creates an orphan
                # duplicate TalkoCDR instead of enriching the original one.
                context_data_with_cdr_id: dict[str, Any] = {
                    **(getattr(call_data, "context_data", None) or {}),
                    "cdr_id": cdr_id,
                }

                pending_context_payload: dict[str, Any] = {
                    "call_id": call_id,
                    "partner_id": partner_id,
                    "user_id": user_id,
                    "from_number": from_number,
                    "to_number": to_number,
                    "agent_number": agent_number,
                    "dedicated_did": from_number,
                    "vendor_id": str(vendor_id),
                    "vendor_config_id": str(vendor_config_id),
                    "entity_type": None,
                    "entity_id": None,
                    "entity_name": None,
                    "context_data": context_data_with_cdr_id,
                    "enable_ai_bridge": bool(call_data.enable_ai_bridge),
                    "created_at": timestamp,
                }

                # ── NEW: AI bridge — pre-create session during ringing ────────
                #
                # When enable_ai_bridge=True we fire a background task that POSTs
                # to makun-ai /voice/sessions while Tata is dialing the customer
                # (ringing typically takes 2-5 seconds). By the time the customer
                # answers, the LiveKit room and makun-ai worker are already warm,
                # so talko-service can join the existing room immediately instead
                # of waiting for a cold session to spin up.
                #
                # The background task stores the room details in Redis under
                # outbound_room:<to_number>. TalkoPSTNBridgeService.handle_call() reads
                # and deletes this key on the WebSocket start event.
                #
                # The existing pending_context store below is kept as a fallback:
                # if _pre_create_session fails (timeout / makun-ai down), handle_call
                # falls back to the normal on-demand _create_session path using the
                # context stored here.
                # ─────────────────────────────────────────────────────────────
                if call_data.enable_ai_bridge:
                    self.__logger.info(
                        f"[PreSession] Firing background pre-session to_number={normalized_to} caller_did={from_number}"
                    )
                    asyncio.create_task(
                        self._pre_create_session(
                            to_number=normalized_to,  # ← customer number = unique Redis key
                            vendor_config_id=str(vendor_config_id),
                            context_data=context_data_with_cdr_id,
                            caller_did=from_number,  # ← DID used to resolve agent_id
                            caller_phone=to_number,
                            fallback_payload=pending_context_payload,
                            fallback_store_key=store_key,
                            call_id=call_id,
                        ),
                        name=f"pre_session_{normalized_to}",
                    )
                    # NOTE: pending_context is stored inside _pre_create_session
                    # as a fallback — do NOT store it here to avoid double writes.
                else:
                    # ── Original flow for non-AI-bridge calls (unchanged) ─────
                    self.__logger.info(f"Storing pending call context store_key={store_key} to_number={normalized_to}")
                    await self.__redis_helper.store_pending_call_context(
                        call_id=store_key,
                        payload=pending_context_payload,
                    )
                    await self.__redis_helper.store_to_number_index(
                        to_number=normalized_to,
                        store_key=store_key,
                        created_at=timestamp,
                    )
                # ─────────────────────────────────────────────────────────────

            else:
                self.__logger.warning("Skipping pending call context redis write because to_number is empty")

            # Outbound websocket popup — scheduler (missed-call callback)
            # only. Manual outbound API calls pass notify_outbound_event=False
            # so they stay silent. Same event shape/broker as inbound calls
            # (see generate_dialplan_response).
            #
            # Awaited (not create_task): publish() is only a fast Redis
            # PUBLISH — the actual websocket fanout happens in each pod's
            # broker listener — and awaiting is required for the Celery
            # path: missed_call_callback_task runs via asyncio.run(), whose
            # loop closes as soon as _run() returns, cancelling any
            # fire-and-forget task before it ever publishes.
            if notify_outbound_event:
                try:
                    did_record = await self.__did_management_service.get_dids_by_number(from_number)
                    await self.__inbound_call_event_publisher.publish_outbound_call(
                        partner_id=partner_id,
                        workspace_id=call_data.workspace_id,
                        dedicated_did=from_number,
                        agent_id=user_id,
                        display_name=(did_record or {}).get("display_name"),
                        customer_number=to_number,
                    )
                except Exception as notify_error:
                    # Notification must never fail call placement — TalkoCDR is
                    # already inserted and vendor call already placed.
                    self.__logger.error(f"Outbound call event notify failed (non-fatal): {str(notify_error)}")

            self.__logger.info(f"Call initiated: {response}")
            return call_contract.CallResponse(id=response["id"], message=CALL_PLACED_SUCCESSFULLY)

        except Exception as e:
            self.__logger.error(f"Unexpected error in initiate_call: {str(e)}")
            raise

    async def initiate_missed_call_callback(self, cdr: dict[str, Any]) -> None:
        """
        Best-effort auto-callback for a missed inbound call. Invoked from
        missed_call_callback_task, which the every-minute beat sweeper
        dispatches ~2-3 min after the miss (see
        src/components/call_management/tasks.py). Re-resolves an active agent
        (may differ from whoever was originally rung, via the same
        reassign-to-active-agent logic used for live inbound routing),
        confirms the customer hasn't already connected on another call in the
        meantime, then places one outbound callback leg. Never raises — all
        failures are logged and swallowed since this runs unattended with no
        Celery retry.
        """
        call_uuid = cdr.get("call_uuid")
        partner_id = cdr.get("partner_id")
        workspace_id = cdr.get("workspace_id")
        customer_number = cdr.get("customer")
        did_number = cdr.get("did_number")
        agent_id = cdr.get("agent")

        try:
            if not (partner_id and workspace_id and customer_number and did_number):
                self.__logger.warning(
                    f"Missed-call callback skipped for call_uuid={call_uuid}: missing "
                    "partner_id/workspace_id/customer/did_number on TalkoCDR"
                )
                return

            if not agent_id:
                self.__logger.info(
                    f"Missed-call callback skipped for call_uuid={call_uuid}: no single "
                    "assigned agent on the missed TalkoCDR"
                )
                return

            partner_config = await self.__partner_config_repo.find_partner_config_by_partner_id(partner_id)
            if not (partner_config or {}).get("enable_missed_call_callback"):
                self.__logger.debug(f"Missed-call callback disabled for partner_id={partner_id}")
                return

            customer_number = str(customer_number)
            did_number = str(did_number)

            # Human-agent callback only — an AI-agent DID's "missed" call has
            # no human to re-ring, and cdr["agent"] on such a call may hold
            # the bot's agent_bot_id rather than a real user_id (see
            # _handle_existing_cdr_flow), which resolve_for_single_agent
            # below would otherwise try to treat as a human agent.
            did_record = await self.__did_management_service.get_dids_by_number(did_number)
            if did_record and did_record.get("did_type") == TalkoDIDType.AI_AGENT.value:
                self.__logger.info(
                    f"Missed-call callback skipped for call_uuid={call_uuid}: DID {did_number} is an AI-agent DID"
                )
                return

            latest_cdr = await self.__repository.find_cdr_by_numbers(customer_number, did_number)
            if latest_cdr and latest_cdr.get("call_status") == "answered":
                self.__logger.info(
                    f"Missed-call callback skipped for call_uuid={call_uuid}: customer {customer_number} "
                    "already connected on a later call"
                )
                return

            target = await self.__dialplan_resolver.resolve_for_single_agent(
                partner_id=partner_id,
                workspace_id=workspace_id,
                agent_id=agent_id,
                fallback_agent_number=cdr.get("agent_number"),
                reassign_inactive_agent=True,
                customer_number=customer_number,
            )

            if not target or not target.data:
                self.__logger.warning(
                    f"Missed-call callback skipped for call_uuid={call_uuid}: no active agent target resolved"
                )
                return

            resolved_agent_id = target.resolved_agent_id or agent_id
            cloud_agent_number = target.data[0] if target.type == "agent" else None
            agent_number = target.data[0] if target.type == "number" else cdr.get("agent_number")

            if not agent_number:
                self.__logger.warning(
                    f"Missed-call callback skipped for call_uuid={call_uuid}: no plain "
                    "agent_number available to satisfy the call contract "
                    "(cloud-only target with no fallback number)"
                )
                return

            call_data = call_contract.CallCreate(
                workspace_id=workspace_id,
                partner_id=partner_id,
                agent_number=agent_number,
                cloud_agent_number=cloud_agent_number,
                to_number=customer_number,
                dedicated_did=did_number,
                encryption_enabled=False,
            )

            self.__logger.info(
                f"Placing missed-call callback for call_uuid={call_uuid} customer={customer_number} "
                f"agent_id={resolved_agent_id} via did={did_number}"
            )

            call_response = await self.initiate_call(
                call_data,
                user_id=resolved_agent_id,
                partner_id=partner_id,
                notify_outbound_event=True,
            )

            # initiate_call has no notion of "this is a callback" — context_data
            # only ever reaches the AI-bridge/makun-ai session path (see
            # _pre_create_session above), never the plain TalkoCDR document, so the
            # link back to the missed call has to be stamped on afterwards.
            if call_response and call_response.id:
                await self.__repository.update_cdr(call_response.id, {"callback_for_call_uuid": call_uuid})

        except Exception as e:
            self.__logger.error(f"Missed-call callback failed for call_uuid={call_uuid}: {str(e)}")

    def _resolve_vendor_config_id(self, partner_config: dict[str, Any], enable_ai_bridge: bool, partner_id: int) -> str:
        """Resolve vendor_config_id the same way initiate_call does.

        AI-bridge calls prefer the partner's ai_vendor_config_id and fall back
        to the legacy AI_BRIDGE_VENDOR_CONFIG_ID only when the partner has
        none configured (logged loudly so missing config gets fixed instead
        of silently working by accident).
        """
        vendor_config_id: str | None = (
            partner_config.get("ai_vendor_config_id") if enable_ai_bridge else None
        ) or partner_config.get("vendor_config_id")
        if not vendor_config_id and enable_ai_bridge:
            self.__logger.warning(
                f"Partner {partner_id} has no ai_vendor_config_id — falling back to legacy "
                "AI_BRIDGE_VENDOR_CONFIG_ID. Set ai_vendor_config_id on the "
                "partner config."
            )
            vendor_config_id = AI_BRIDGE_VENDOR_CONFIG_ID
        if not vendor_config_id:
            raise TalkoResourceNotFound("No vendor_config_id assigned to partner.")
        return vendor_config_id

    async def transfer_call(
        self,
        call_id: str,
        destination_number: str,
        partner_id: int,
        enable_ai_bridge: bool = False,
    ) -> dict[str, Any]:
        """
        Transfer an in-progress call to another number via the partner's vendor.

        The vendor's call_id is passed directly by the caller (not resolved from
        an internal call record). vendor_id is resolved from the authenticated
        partner, same as initiate_call. enable_ai_bridge must be supplied by the
        caller (mirroring initiate_call) since this call intentionally avoids
        looking up any stored call state. vendor_config_id resolves from the
        partner config (ai_vendor_config_id for AI-bridge calls).

        Args:
            call_id (str): Vendor's identifier for the in-progress call.
            destination_number (str): Number to transfer the call to.
            partner_id (int): Authenticated partner initiating the transfer.
            enable_ai_bridge (bool): Whether the in-progress call was placed via
                the AI bridge, so the hardcoded AI vendor_config is used instead
                of the partner's default vendor_config.

        Returns:
            Dict[str, Any]: Vendor API response.

        Raises:
            TalkoResourceNotFound: If no vendor is assigned to the partner.
            ValueError: For vendor errors.
        """
        try:
            self.__logger.info(f"Transfer call service started for partner_id {partner_id} call_id {call_id}")

            partner_config: dict[str, Any] = await self.__helper.get_partner_config(partner_id)

            vendor_id: str | None = partner_config.get("vendor_id")
            if not vendor_id:
                raise TalkoResourceNotFound(NO_VENDOR_ID_ASSIGNED_TO_PARTNER)

            vendor_config_id = self._resolve_vendor_config_id(partner_config, enable_ai_bridge, partner_id)

            vendor_handler: Any = await self.__helper.get_vendor_handler(vendor_id, vendor_config_id)

            vendor_response: dict[str, Any] = await vendor_handler.transfer_call(call_id, destination_number)

            self.__logger.info(f"Call transfer completed for call_id {call_id}: {vendor_response}")
            return vendor_response

        except Exception as e:
            self.__logger.error(f"Unexpected error in transfer_call: {str(e)}")
            raise

    # ── NEW: background pre-session creation ─────────────────────────────────

    async def _pre_create_session(
        self,
        to_number: str,
        vendor_config_id: str,
        context_data: dict[str, Any],
        caller_did: str,
        caller_phone: str,
        fallback_payload: dict[str, Any],
        fallback_store_key: str,
        call_id: str | None = None,
    ) -> None:
        """
        Background task: POST to makun-ai /voice/sessions while Tata dials
        the customer, then store the pre-created room in Redis so handle_call()
        can consume it instantly when the customer answers.

        Uses to_number (customer number, digits only) as the Redis key —
        same key handle_call reads from Tata start event. Matches the
        previous pending_context pattern exactly.

        On any failure falls back to storing pending_context so handle_call()
        can use the normal on-demand _create_session path. Call is never lost.

        Args:
            to_number:          Digits-only customer number — unique Redis key.
            vendor_config_id:   Stored in fallback payload.
            context_data:       Passed to makun-ai session.
            caller_did:         DID (from_number) — used to resolve agent_id,
                                same way TalkoPSTNBridgeService._resolve_did() does.
            caller_phone:       Customer phone number with + prefix.
            fallback_payload:   Full pending_context dict to store on failure.
            fallback_store_key: Redis key for fallback pending_context store.
            call_id:            Vendor call_id from the click-to-call response.
                                For AI-bridge calls Tata hasn't assigned a real
                                one yet at this point (comes back as "None"),
                                so this is normally absent here — the real
                                vendor call_id now gets resolved and injected
                                entirely from the PSTN side (best-effort
                                live_calls poll + LiveKit data-channel backfill
                                in pstn/services.py Step 6, merged into
                                context_data by the makun-ai worker), not here.
        """
        t0 = time.perf_counter()
        try:
            # ── voiceai route: no makun-ai pre-session ────────────────────
            # Calls carrying context_data.voiceai_agent_id are served by the
            # voiceai engine (relayed in pstn/services.py Step 4b), so skip
            # the DID resolve + makun-ai session POST entirely and store the
            # pending context directly — the PSTN side picks it up via the
            # normal on-demand _attach_pending_context path.
            if (context_data or {}).get(VOICEAI_AGENT_ID_KEY):
                self.__logger.info(
                    f"[PreSession] voiceai-routed call to_number={to_number} agent={context_data.get(VOICEAI_AGENT_ID_KEY)} — "
                    "skipping makun-ai pre-session, storing pending context"
                )
                await self._store_fallback_context(fallback_store_key, fallback_payload, to_number)
                return

            # ── Step 1: Resolve agent_id from DID ────────────────────────────
            # Exact same logic as TalkoPSTNBridgeService._resolve_did()
            try:
                did_record = await self.__did_repository.get_did_by_number(call_to_number=caller_did, partner_id=None)
            except Exception as e:
                raise ValueError(f"DID DB fetch failed caller_did={caller_did}: {e}")

            if not did_record or not did_record.get("is_active", True):
                raise ValueError(f"No active DID record for caller_did={caller_did}")

            did_type: str = did_record.get("did_type", TalkoDIDType.NORMAL.value)
            if did_type == TalkoDIDType.AI_AGENT.value:
                agent_id = did_record.get("agent_bot_id")
            else:
                agent_id = did_record.get("agent_id")

            if not agent_id:
                raise ValueError(f"agent_id missing on DID {caller_did} did_type={did_type}")

            # The DID's own assigned partner — NOT necessarily the caller's
            # partner_id. makun-ai scopes agent_id lookups to the DID's
            # owning partner, same as TalkoPSTNBridgeService._resolve_did() does
            # (partner_id = did_record["partner_id"]). Using the caller's
            # partner_id here would 404 whenever a partner is (validly) using
            # a DID assigned to a different partner.
            did_partner_id: int | None = did_record.get("partner_id")
            if not did_partner_id:
                raise ValueError(f"partner_id missing on DID {caller_did}")

            self.__logger.info(
                f"[PreSession] DID resolved caller_did={caller_did} agent_id={agent_id} did_type={did_type} "
                f"did_partner_id={did_partner_id}"
            )

            # ── Step 2: Resolve partner API key (same cache as TalkoPSTNBridgeService) ──
            from redis import asyncio as aioredis

            from src.components.cache.redis_client import get_redis_client
            from src.core.redis_constants import (
                API_KEY_CACHE_KEY,
                API_KEY_CACHE_TTL_SECONDS,
            )
            from src.grpc_client.constants import TalkoGrpcServices
            from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory

            redis: aioredis.Redis = await get_redis_client()
            api_key_cache_key = API_KEY_CACHE_KEY.format(partner_id=did_partner_id)
            raw_key = await redis.get(api_key_cache_key)
            if raw_key:
                api_key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else raw_key
                self.__logger.debug(f"[PreSession] API key cache HIT partner_id={did_partner_id}")
            else:
                self.__logger.debug(f"[PreSession] API key cache MISS fetching via gRPC partner_id={did_partner_id}")
                grpc_client = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.AUTH)
                if grpc_client is None:
                    raise TalkoBadRequestError("Console API key unavailable — gRPC disabled and key not cached")
                api_key = await grpc_client.get_partner_api_key(did_partner_id)
                await redis.set(api_key_cache_key, api_key, ex=API_KEY_CACHE_TTL_SECONDS)

            # Only a genuine passed-in call_id is used here — no live_calls
            # polling in this path anymore. The real vendor call_id is now
            # resolved and injected entirely from the PSTN side (best-effort
            # live_calls poll + LiveKit data-channel backfill in
            # pstn/services.py Step 6, merged into context_data by the
            # makun-ai worker), so this session POST just proceeds without it
            # when absent — no regression, that fallback always still runs.
            resolved_call_id: str | None = call_id if (call_id and call_id != "None") else None

            # ── Step 3: POST to makun-ai /voice/sessions ──────────────────────
            # AI bridge calls have no Tata call_id — use to_number as session_id
            headers = {"API-Key": api_key, "Content-Type": "application/json"}
            # Only inject call_id if it's a genuine passed-in value, so we
            # never poison context_data with the "None" placeholder. If
            # absent, the real vendor call_id gets backfilled over the
            # LiveKit data channel once resolved (pstn/services.py Step 6),
            # which the makun-ai worker merges in at that point.
            session_context_data: dict[str, Any] = dict(context_data or {})
            if resolved_call_id:
                session_context_data["call_id"] = resolved_call_id

            payload = {
                "agent_id": agent_id,  # ← real integer from DID record
                "partner_id": did_partner_id,  # ← DID's owning partner, not the caller
                "session_id": to_number,  # ← customer number as unique id
                "medium": "voice",
                "caller_did": caller_did,
                "external_call_sid": resolved_call_id,
                "caller_phone": caller_phone,
                "context_data": session_context_data,
            }

            self.__logger.info(
                f"[PreSession] POST {TalkoENV.MAKUNAI_SESSION_URL} to_number={to_number} agent_id={agent_id}"
            )

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(TalkoENV.MAKUNAI_SESSION_URL, headers=headers, json=payload)
                resp.raise_for_status()

            data = resp.json().get("data", {})
            room_name = data.get("room_name")
            caller_token = data.get("caller_token")
            livekit_url = data.get("livekit_url")
            greeting_audio = data.get("greeting_audio")

            if not room_name or not caller_token or not livekit_url:
                raise ValueError(f"makun-ai response missing room fields: {data}")

            # ── Step 4: Store room in Redis keyed by to_number ────────────────
            # context_data (carrying cdr_id) was previously dropped here —
            # the pre-warmed/fast path (this one) is the common case for a
            # successful AI-bridge call, so handle_call()'s pre-warmed branch
            # never had a way to populate ctx.context_data at all, only the
            # on-demand fallback path (_attach_pending_context) did. Without
            # it, _backfill_real_vendor_call_id has no cdr_id to update.
            room_payload: dict[str, Any] = {
                "room_name": room_name,
                "caller_token": caller_token,
                "livekit_url": livekit_url,
                "agent_id": agent_id,
                "greeting_audio": greeting_audio,
                "created_at": time.time(),
                "context_data": session_context_data,
            }

            await self.__redis_helper.store_outbound_room(to_number, room_payload)

            elapsed = (time.perf_counter() - t0) * 1000
            self.__logger.info(
                f"[PreSession] ✅ Room stored to_number={to_number} room={room_name} agent_id={agent_id} elapsed={elapsed:.0f}ms"
            )

        except httpx.TimeoutException:
            elapsed = (time.perf_counter() - t0) * 1000
            self.__logger.warning(
                f"[PreSession] ⏱️ Timeout to_number={to_number} elapsed={elapsed:.0f}ms "
                "— falling back to pending_context"
            )
            await self._store_fallback_context(fallback_store_key, fallback_payload, to_number)

        except httpx.HTTPStatusError as e:
            elapsed = (time.perf_counter() - t0) * 1000
            self.__logger.warning(
                f"[PreSession] ❌ HTTP {e.response.status_code} to_number={to_number} elapsed={elapsed:.0f}ms "
                "— falling back to pending_context"
            )
            await self._store_fallback_context(fallback_store_key, fallback_payload, to_number)

        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            self.__logger.error(
                f"[PreSession] ❌ Unexpected error to_number={to_number} "
                f"elapsed={elapsed:.0f}ms error={e} traceback={traceback.format_exc()}"
            )
            await self._store_fallback_context(fallback_store_key, fallback_payload, to_number)

    async def _store_fallback_context(
        self,
        store_key: str,
        payload: dict[str, Any],
        to_number: str,
    ) -> None:
        """
        Store pending_context + index so handle_call() can fall back to the
        normal on-demand _create_session path if pre-session failed.
        """
        try:
            await self.__redis_helper.store_pending_call_context(
                call_id=store_key,
                payload=payload,
            )
            await self.__redis_helper.store_to_number_index(
                to_number=to_number,
                store_key=store_key,
                created_at=payload.get("created_at"),
            )
            self.__logger.info(f"[PreSession] Fallback context stored store_key={store_key} to_number={to_number}")
        except Exception as e:
            self.__logger.error(
                f"[PreSession] ❌ Fallback context store FAILED store_key={store_key} to_number={to_number} error={e}"
            )

    # ─────────────────────────────────────────────────────────────────────────

    def get_webhook_handler(self, vendor: str, type: str = "standard") -> TalkoWebhookHandler:
        """
        Orchestrates a call initiation process by:
        - Validating and fetching partner and vendor configurations.
        - Selecting a DID using round-robin logic.
        - Making the outbound call via the vendor's API.
        - Logging the call in a TalkoCDR.
        - Returning a structured response.

        Args:
            call_data (CallCreate): Data required to initiate the call.

        Returns:
            CallResponse: Response containing call metadata and status.

        Raises:
            TalkoResourceNotFound: If any required config is missing.
            TalkoBadRequestError: For unsupported vendors.
            ValueError: For invalid DID selection.
            Exception: For unexpected failures.
        """
        try:
            if vendor in [TalkoVendorType.TATA_TELE.value, TalkoVendorType.ACEFHONE.value] and type == "standard":
                return TalkoTataTeleWebhookHandler(
                    self.__logger,
                    self.__repository,
                    vendor,
                    call_redis_helper=self.__redis_helper,
                )

            if vendor in [TalkoVendorType.TATA_TELE.value, TalkoVendorType.ACEFHONE.value] and type == "dialer":
                return TalkoDialerWebhookHandler(
                    self.__logger,
                    self.__repository,
                    self.__did_management_service,
                    vendor,
                )

            raise ValueError(f"Unsupported vendor_id: {vendor}")
        except Exception as e:
            self.__logger.error(f"Unexcpected error in get webhook handler: {str(e)}")
            raise

    async def generate_dialplan_response(self, request) -> list:
        try:
            self.__logger.info("Received generate dialplan request")
            request_data = await request.json()
            caller_id_number = request_data.get("caller_id_number")
            call_to_number = request_data.get("call_to_number")

            self.__logger.debug(
                f"Processing dialplan for caller_id_number: {caller_id_number}, call_to_number: {call_to_number}"
            )

            cdr = await self.__repository.find_cdr_by_numbers(caller_id_number, call_to_number)

            if cdr:
                response, event_metadata = await self._handle_existing_cdr_flow(request_data, cdr)
            else:
                response, event_metadata = await self._handle_no_cdr_flow(
                    request_data, caller_id_number, call_to_number
                )

            # This endpoint only ever runs when an inbound call needs redirecting to
            # an agent, so it's the single, reliable place to emit the websocket event
            # — regardless of which flow (existing TalkoCDR vs no TalkoCDR) resolved the agent.
            # Fired as a background task (not awaited) so a slow/stuck dashboard
            # websocket can never delay the dialplan response back to Tata Tele.
            if event_metadata:
                asyncio.create_task(
                    self.__inbound_call_event_publisher.publish_inbound_call(**event_metadata),
                    name="inbound_call_event_publish",
                )

            return response

        except Exception as e:
            self.__logger.error(f"Error in generate_dialplan_response: {str(e)}")
            return self.__response_builder.build_empty_response()

    async def _handle_existing_cdr_flow(self, request_data, cdr) -> tuple[list, dict[str, Any]]:
        """Handle dialplan generation when TalkoCDR exists"""
        self.__logger.debug(f"TalkoCDR found dialplan: {cdr}: request data: {request_data}")

        dedicated_did = request_data.get("call_to_number")
        did_record = await self.__did_management_service.get_dids_by_number(dedicated_did)

        # For AI-agent DIDs, prefer the DID's current bot assignment over the
        # TalkoCDR's, since the number may have been reassigned to a different bot
        # since this TalkoCDR was created. Regular (human-agent) DIDs keep the
        # existing behavior of trusting the TalkoCDR's agent. Only fall back to
        # the TalkoCDR's agent if the DID lookup fails or doesn't yield a usable
        # agent id.
        current_agent_id = cdr.get("agent")
        if did_record and did_record.get("did_type") == TalkoDIDType.AI_AGENT.value:
            live_agent_id = did_record.get("agent_bot_id")
            if live_agent_id:
                current_agent_id = live_agent_id

        partner_config = await self.__partner_config_repo.find_partner_config_by_partner_id(cdr["partner_id"])
        reassign_inactive_agent = self._should_reassign_inactive_agent(partner_config)
        self.__logger.debug(
            "Existing-TalkoCDR flow: inactive-agent reassignment enabled: {} for partner_id: {}, agent_id: {}".format(
                reassign_inactive_agent, cdr.get("partner_id"), current_agent_id
            )
        )

        target = await self.__dialplan_resolver.resolve_for_single_agent(
            partner_id=cdr["partner_id"],
            workspace_id=cdr["workspace_id"],
            agent_id=current_agent_id,
            fallback_agent_number=cdr.get("agent_number"),
            reassign_inactive_agent=reassign_inactive_agent,
            customer_number=request_data.get("caller_id_number"),
        )

        self.__logger.debug(f"Dialplan target resolved: {target}")

        # Reflect a possible reassignment so the TalkoCDR and event metadata
        # record the agent actually being dialed, not the stale owner.
        if target and target.resolved_agent_id:
            current_agent_id = target.resolved_agent_id

        event_metadata = {
            "partner_id": cdr.get("partner_id"),
            "workspace_id": cdr.get("workspace_id"),
            "dedicated_did": dedicated_did,
            "agent_id": current_agent_id,
            "display_name": (did_record or {}).get("display_name"),
            "customer_number": request_data.get("caller_id_number"),
        }

        inbound_type_str, cloud_agent_number = self.__dialplan_resolver.map_transfer_to_inbound_fields(target)

        # Priority 1: whatever lead_id/entity_id the previous TalkoCDR already had
        # on record. Priority 2: if a reassignment happened this call and
        # Maglo confirmed a lead_request_id, that's the freshest data — use
        # it instead. entity_id only gets overridden when the TalkoCDR's entity
        # actually represents a lead (or has none set yet) — if entity_type
        # is something else (e.g. a Contact), entity_id keeps pointing at
        # that other record and only the legacy lead_id field is refreshed.
        old_entity_type = cdr.get("entity_type")
        lead_id = cdr.get("lead_id")
        entity_id_override = cdr.get("entity_id")
        if target and target.reassigned_lead_id:
            lead_id = target.reassigned_lead_id
            if old_entity_type is None or old_entity_type == TalkoEntityType.LEAD.value:
                entity_id_override = target.reassigned_lead_id

        entity_type, entity_id, entity_name = self._derive_inbound_entity_fields(
            entity_type=old_entity_type,
            entity_id=entity_id_override,
            entity_name=cdr.get("entity_name"),
            lead_id=lead_id,
            lead_name=cdr.get("lead_name"),
        )

        await self._create_cdr_if_valid_target(
            target=target,
            request_data=request_data,
            partner_id=cdr.get("partner_id", 0),
            agent_id=current_agent_id or 0,
            workspace_id=cdr.get("workspace_id"),
            agent_number=cdr.get("agent_number"),
            agent_ids=None,
            lead_id=lead_id,
            lead_name=cdr.get("lead_name"),
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            vendor_id=cdr.get("vendor_id"),
            vendor_config_id=cdr.get("vendor_config_id"),
            inbound_type_str=inbound_type_str,
            cloud_agent_number=cloud_agent_number,
        )

        return self.__response_builder.build_transfer_response(target), event_metadata

    async def _handle_no_cdr_flow(
        self, request_data, caller_id_number, call_to_number
    ) -> tuple[list, dict[str, Any] | None]:
        """Handle dialplan generation when no TalkoCDR exists"""
        self.__logger.info("No TalkoCDR found, proceeding with lead handling flow")

        did_record = await self.__did_management_service.get_dids_by_number(call_to_number)

        if not did_record or not did_record.get("workspace_id"):
            self.__logger.warning(f"No DID record or workspace_id found for number: {call_to_number}")
            return self.__response_builder.build_empty_response(), None

        self.__logger.debug(f"DID record found: {did_record}")

        partner_config = await self.__partner_config_repo.find_partner_config_by_partner_id(did_record["partner_id"])

        self.__logger.debug(
            "Partner config loaded for partner_id {}: {}".format(did_record["partner_id"], partner_config)
        )

        create_lead = self._should_create_lead(partner_config)
        reassign_inactive_agent = self._should_reassign_inactive_agent(partner_config)
        enable_inbound_round_robin = self._should_use_inbound_round_robin(partner_config)
        inbound_round_robin_index = (partner_config or {}).get("inbound_round_robin_index", 0) or 0

        self.__logger.debug(
            "Lead creation enabled: {}, inactive-agent reassignment enabled: {}, "
            "inbound round robin enabled: {} (index={}) for partner_id: {}".format(
                create_lead,
                reassign_inactive_agent,
                enable_inbound_round_robin,
                inbound_round_robin_index,
                did_record["partner_id"],
            )
        )

        result = await self.__dialplan_resolver.resolve_inbound_no_cdr(
            customer_number=caller_id_number,
            call_to_number=call_to_number,
            partner_id=did_record["partner_id"],
            workspace_id=did_record["workspace_id"],
            vendor_id=did_record.get("vendor_id"),
            vendor_config_id=did_record.get("vendor_config_id"),
            create_lead=create_lead,
            reassign_inactive_agent=reassign_inactive_agent,
            enable_inbound_round_robin=enable_inbound_round_robin,
            inbound_round_robin_index=inbound_round_robin_index,
        )

        self.__logger.debug(f"Dialplan resolved for no TalkoCDR flow: {result}")

        target = result["target"]

        inbound_round_robin_next_index = result.get("inbound_round_robin_next_index")
        if inbound_round_robin_next_index is not None:
            await self.__repository.update_partner_config_inbound_round_robin_index(
                did_record["partner_id"],
                inbound_round_robin_next_index,
                self.__datetime_util.get_current_time(),
            )

        event_metadata = {
            "partner_id": result.get("partner_id"),
            "workspace_id": result.get("workspace_id"),
            "dedicated_did": call_to_number,
            "agent_id": result.get("agent_id"),
            "agent_ids": [
                agent["agent_id"] for agent in (result.get("agent_ids") or []) if agent.get("agent_id") is not None
            ],
            "display_name": did_record.get("display_name"),
            "customer_number": caller_id_number,
        }

        inbound_type_str, cloud_agent_number = self.__dialplan_resolver.map_transfer_to_inbound_fields(target)

        entity_type, entity_id, entity_name = self._derive_inbound_entity_fields(
            entity_type=result.get("entity_type"),
            entity_id=result.get("entity_id"),
            entity_name=result.get("entity_name"),
            lead_id=result.get("lead_id"),
            lead_name=result.get("lead_name"),
        )

        await self._create_cdr_if_valid_target(
            target=target,
            request_data=request_data,
            partner_id=result["partner_id"],
            agent_id=result.get("agent_id"),
            workspace_id=result["workspace_id"],
            agent_number=result.get("agent_number"),
            agent_ids=result["agent_ids"],
            lead_id=result.get("lead_id"),
            lead_name=result.get("lead_name"),
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            vendor_id=str(result["vendor_id"]) if result.get("vendor_id") else None,
            vendor_config_id=(str(result["vendor_config_id"]) if result.get("vendor_config_id") else None),
            inbound_type_str=inbound_type_str,
            cloud_agent_number=cloud_agent_number,
        )

        return self.__response_builder.build_transfer_response(target), event_metadata

    def _should_create_lead(self, partner_config) -> bool:
        """Determine if lead should be created based on partner config"""
        if partner_config is None:
            return False
        return partner_config.get("enable_inbound_lead_creation", False)

    def _should_reassign_inactive_agent(self, partner_config) -> bool:
        """Determine if an inactive assigned agent should be replaced based on partner config"""
        if partner_config is None:
            return False
        return partner_config.get("enable_agent_reassignment_on_inactive", False)

    def _should_use_inbound_round_robin(self, partner_config) -> bool:
        """Determine if inbound board-wide ringing should rotate agents based on partner config"""
        if partner_config is None:
            return False
        return partner_config.get("enable_inbound_round_robin", False)

    async def _create_cdr_if_valid_target(
        self,
        target,
        request_data,
        partner_id,
        agent_id,
        workspace_id,
        agent_number,
        agent_ids,
        lead_id,
        lead_name,
        entity_type,
        entity_id,
        entity_name,
        vendor_id,
        vendor_config_id,
        inbound_type_str,
        cloud_agent_number,
    ):
        """Create TalkoCDR only if target is valid"""
        self.__logger.debug(f"Evaluating TalkoCDR creation for target: {target}")
        should_create_cdr = bool(target and target.data)

        self.__logger.debug(f"Should create TalkoCDR: {should_create_cdr} for target: {target}")

        if should_create_cdr:
            await self.__helper.create_incoming_cdr(
                request_data=request_data,
                partner_id=partner_id,
                agent_id=agent_id,
                workspace_id=workspace_id,
                agent_number=agent_number,
                agent_ids=agent_ids,
                lead_id=lead_id,
                lead_name=lead_name,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                vendor_id=vendor_id,
                vendor_config_id=vendor_config_id,
                inbound_type=inbound_type_str,
                cloud_agent_number=cloud_agent_number,
            )
        else:
            self.__logger.info("Skipping TalkoCDR creation — no valid transfer targets")

    async def get_call_details(
        self,
        call_id: str | None,
        vendor_config_id: str,
        call_uuid: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetch call details using call_id and vendor_config_id.

        Flow:
        1. Fetch full vendor config using vendor_config_id
        2. Route through TalkoVendorCDRGateway (extensible for future vendors)
        3. Returns raw_payload + processed_result
        """
        try:
            self.__logger.info(
                f"get_call_details called - call_id: {call_id}, call_uuid: {call_uuid}, vendor_config_id: {vendor_config_id}"
            )

            if call_id is None and call_uuid is None:
                raise TalkoBadRequestError("{} is required".format("call_id" if call_uuid is None else "call_uuid"))

            if not vendor_config_id:
                raise TalkoBadRequestError("vendor_config_id is required")

            try:
                config_oid = ObjectId(vendor_config_id)
            except InvalidId:
                raise TalkoBadRequestError(f"Invalid vendor_config_id format: {vendor_config_id}")

            # Fetch vendor config using vendor_config_id
            vendor_config: dict[str, Any] | None = await self.__vendor_config_repository.find_config_by_id(config_oid)

            if not vendor_config:
                self.__logger.error(f"Vendor config not found for id: {vendor_config_id}")
                raise TalkoResourceNotFound(f"Vendor configuration not found for id: {vendor_config_id}")

            self.__logger.debug(f"In get call details - Vendor config fetched: {vendor_config}")

            self.__logger.debug("Vendor config fetched: {}".format(vendor_config.get("vendor_type")))

            # Delegate to TalkoVendorCDRGateway (this makes it extensible)
            result: dict[str, Any] = await self.__vendor_cdr_gateway.fetch_call_details(
                call_id=call_id,
                call_uuid=call_uuid,
                vendor_config=vendor_config,
            )

            self.__logger.debug(f"Call details fetched: {result}")

            self.__logger.info(f"Successfully fetched call details for call_id: {call_id}, call_uuid: {call_uuid}")

            response = await self.__cdr_repository.find_one_cdr_by_identifier(
                call_id=call_id,
                call_uuid=call_uuid,
                vendor_config_id=vendor_config_id,
            )

            if not response:
                raise TalkoResourceNotFound("TalkoCDR not found")

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

            # If do_recording_url is derived from path_for_recording, do:
            # await self.get_url_from_path(cdr)

            return cdr_contract.CallRecordHistoryResponse(**formatted_response).model_dump()

        except TalkoBadRequestError as e:
            self.__logger.error(f"BadRequest in get_call_details: {str(e)}")
            raise
        except TalkoResourceNotFound as e:
            self.__logger.error(f"TalkoResourceNotFound in get_call_details: {str(e)}")
            raise
        except Exception as e:
            self.__logger.error(f"Unexpected error in get_call_details: {str(e)}")
            raise

    async def hangup_call(
        self,
        call_id: str,
        user_id: int | None,
        partner_id: int,
        enable_ai_bridge: bool = False,
    ) -> call_contract.HangupCallResponse:
        """
        Hang up an ongoing call via the partner's assigned vendor.

        Resolves the vendor the same way initiate_call does — from the caller's
        partner_id (already normalized for both token and API-KEY auth by
        get_current_auth_context) — rather than looking up the TalkoCDR, so this
        works even if the TalkoCDR write for the call hasn't landed yet. For the same
        reason, enable_ai_bridge must be supplied by the caller to pick the AI
        vendor_config instead of the partner's default.

        Args:
            call_id: Vendor's identifier for the call to hang up.
            user_id: User initiating the hangup (None when called via API-KEY).
            partner_id: Partner associated with the call.
            enable_ai_bridge: Whether the call was placed via the AI bridge.

        Returns:
            call_contract.HangupCallResponse: Vendor's hangup result.

        Raises:
            TalkoResourceNotFound: If no vendor is assigned to the partner.
            ValueError: For vendor errors (missing config, unexpected response, etc).
        """
        try:
            self.__logger.info(f"Hangup call requested by user {user_id} (partner {partner_id}) for call_id: {call_id}")

            partner_config: dict[str, Any] = await self.__helper.get_partner_config(partner_id)

            vendor_id: str | None = partner_config.get("vendor_id")
            if not vendor_id:
                raise TalkoResourceNotFound(NO_VENDOR_ID_ASSIGNED_TO_PARTNER)

            vendor_config_id = self._resolve_vendor_config_id(partner_config, enable_ai_bridge, partner_id)

            vendor_handler: Any = await self.__helper.get_vendor_handler(vendor_id, vendor_config_id)

            vendor_response: dict[str, Any] = await vendor_handler.hangup_call(call_id)

            self.__logger.info(f"Hangup call response for call_id {call_id}: {vendor_response}")
            if self.__channel_pool_service is not None:
                try:
                    await self.__channel_pool_service.release(vendor_config_id)
                except Exception as pool_e:
                    self.__logger.error(f"Channel pool release failed (non-fatal): {str(pool_e)}")

            return call_contract.HangupCallResponse(
                success=bool(vendor_response.get("Success", vendor_response.get("success", False))),
                message=vendor_response.get("Message", vendor_response.get("message", CALL_HANGUP_INITIATED)),
            )

        except TalkoResourceNotFound as e:
            self.__logger.error(f"TalkoResourceNotFound in hangup_call: {str(e)}")
            raise
        except ValueError as e:
            self.__logger.error(f"Vendor error in hangup_call: {str(e)}")
            raise
        except Exception as e:
            self.__logger.error(f"Unexpected error in hangup_call: {str(e)}")
            raise

    # ── gRPC telephony control plane (Phase 4, dormant) ────────────────────
    # Implemented in grpc_control_service.py; thin delegates below preserve
    # the TalkoCallService API (controllers/tests unchanged).

    def _grpc_control(self):  # lazy to avoid import cycles at module load
        from src.components.call_management.grpc_control_service import TalkoGrpcControlService

        return TalkoGrpcControlService(
            logger=self.__logger,
            telephony_client=self.__telephony_client,
            telephony_bridge=self.__telephony_bridge,
            channel_pool_service=self.__channel_pool_service,
        )

    def _require_telephony(self) -> Any:
        return self._grpc_control()._require_telephony()

    async def grpc_hangup_call(self, call_id: str, vendor_config_id: str) -> call_contract.HangupCallResponse:
        return await self._grpc_control().grpc_hangup_call(call_id, vendor_config_id)

    async def grpc_transfer_call(self, call_id: str, destination_number: str, vendor_config_id: str) -> dict[str, Any]:
        return await self._grpc_control().grpc_transfer_call(call_id, destination_number, vendor_config_id)

    async def grpc_call_status(self, call_id: str, vendor_config_id: str) -> dict[str, Any]:
        return await self._grpc_control().grpc_call_status(call_id, vendor_config_id)
