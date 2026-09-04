import time
import httpx
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from dateutil.relativedelta import relativedelta
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from src.components.call_management import messages as call_messages
from src.components.call_management.agent_dialplan_resolver import AgentDialPlanResolver
from src.components.call_management.dto import Contract
from src.components.call_management.services import CallService
from src.components.cdr.repository import CDRRepository
from src.components.common.auth_context import get_current_auth_context
from src.components.common.constants import CurrentUserMap
from src.components.common.responses import (
    BadRequestResponse,
    InternalServerErrorResponse,
    ResourceNotFoundResponse,
    SuccessResponse,
)
from src.components.integrations.console.maglo_constants import MagloApiConstants
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import BadRequestError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger

WRONG_AGENT_ID = 6
PARTNER_ID = 2
LOOKBACK_MONTHS = 2
LOOKBACK_DAYS = 2
MAGLO_BASE_URL = "https://maglo-service.makunaiglobal.ai"
MAGLO_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc19hY3RpdmUiOnRydWUsInVzZXJfc2Vzc2lvbl9pZCI6IjQxMTBlNzk2LTk0YjctNDY1NC1iMjk5LThiODE2YjI3ZWY1ZiIsInVzZXJfaWQiOjExODYsIm5hbWUiOiJUcnVwdGkgV2FkZWthciIsInBhcnRuZXJfaWQiOjM2MywiaXNfbWFnbG9fZW5hYmxlZCI6dHJ1ZSwiaXNfYmFiYmxlcl9lbmFibGVkIjp0cnVlLCJpc19ob2xsZXJfZW5hYmxlZCI6dHJ1ZSwiaXNfaW50ZXJuYWwiOmZhbHNlLCJpc193YWxsZXRfZW5hYmxlZCI6ZmFsc2UsImlzX21hZ2xvX2FwcF9lbmFibGVkIjp0cnVlLCJzdWJzY3JpcHRpb25fbW9kZSI6InNhbGVzX21hbmFnZWQiLCJleHAiOjE3Nzg0NjE0MzJ9.J5TSBp67uy9fJmoGs0jBOrBBmCg_oELO-gUoAfnorPk"


class CallController:
    """Controller to handle call-related API endpoints."""

    call_router = APIRouter()

    @call_router.post(
        "", response_model=Contract.CallResponse, status_code=status.HTTP_201_CREATED
    )
    @permission_check(PermissionDependency)
    @inject
    async def initiate_call(
        request: Request,
        call_data: Contract.CallCreate,
        call_service: CallService = Depends(Provide[Container.call_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.CallResponse:
        """
        Initiate a new outbound or inbound call.

        Args:
            request (Request): The incoming FastAPI request object.
            call_data (Contract.CallCreate): Data required to initiate the call.
            call_service (CallService): Service class to handle call logic.
            holler_service_logger (HollerServiceLogger): Logger for tracking events.

        Returns:
            Contract.CallResponse: The response containing call initiation details.
        """
        try:
            holler_service_logger.info("Received call request: {}".format(call_data))
            auth_ctx = get_current_auth_context(request)
            user_id: int = auth_ctx.user_id  # None when called via API-KEY
            partner_id: int = auth_ctx.partner_id
            holler_service_logger.info(
                "User: {}, partner: {}, initiated call api.".format(user_id, partner_id)
            )
            call_response: Contract.CallResponse = await call_service.initiate_call(
                call_data, user_id, partner_id
            )
            holler_service_logger.info(
                "Call initiated successfully: {}".format(call_response)
            )
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content={
                    "status": "success",
                    "message": call_messages.CALL_PLACED_SUCCESSFULLY,
                },
            )
        except ValueError as e:
            holler_service_logger.error(
                "Error in initiating call api: {}".format(str(e))
            )
            return BadRequestResponse(detail=call_messages.SOMETHING_WENT_WRONG)
        except ResourceNotFound as e:
            holler_service_logger.error(
                "Error in initiate call api resource: {}".format(str(e))
            )
            return ResourceNotFoundResponse(detail=call_messages.SOMETHING_WENT_WRONG)
        except BadRequestError as e:
            holler_service_logger.error(
                "Error in initiate call api resource: {}".format(str(e))
            )
            return BadRequestResponse(detail=call_messages.CALL_INITIATION_FAILED)
        except Exception as e:
            holler_service_logger.error(f"Unexpected error initiating call: {str(e)}")
            raise InternalServerErrorResponse(
                detail=call_messages.UNEXPECTED_ERROR_INITIATING_CALL
            )

    @call_router.post(
        "/hangup",
        response_model=Contract.HangupCallResponse,
        status_code=status.HTTP_200_OK,
    )
    @permission_check(PermissionDependency)
    @inject
    async def hangup_call(
        request: Request,
        hangup_data: Contract.HangupCallRequest,
        call_service: CallService = Depends(Provide[Container.call_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> JSONResponse:
        """
        Hang up an ongoing call via the partner's assigned vendor.

        Args:
            request (Request): The incoming FastAPI request object.
            hangup_data (Contract.HangupCallRequest): Data required to hang up the call.
            call_service (CallService): Service class to handle call logic.
            holler_service_logger (HollerServiceLogger): Logger for tracking events.

        Returns:
            JSONResponse: The vendor's hangup result.
        """
        try:
            holler_service_logger.info(
                "Received hangup call request: {}".format(hangup_data)
            )
            auth_ctx = get_current_auth_context(request)
            user_id: Optional[int] = auth_ctx.user_id  # None when called via API-KEY
            partner_id: int = auth_ctx.partner_id
            holler_service_logger.info(
                "User: {}, partner: {}, initiated hangup call api.".format(
                    user_id, partner_id
                )
            )
            hangup_response: Contract.HangupCallResponse = (
                await call_service.hangup_call(
                    hangup_data.call_id,
                    user_id,
                    partner_id,
                    hangup_data.enable_ai_bridge or False,
                )
            )
            holler_service_logger.info(
                "Hangup call completed: {}".format(hangup_response)
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "success",
                    "data": hangup_response.model_dump(),
                },
            )
        except ResourceNotFound as e:
            holler_service_logger.error(
                "Error in hangup call api resource: {}".format(str(e))
            )
            return ResourceNotFoundResponse(detail=call_messages.SOMETHING_WENT_WRONG)
        except ValueError as e:
            holler_service_logger.error("Error in hangup call api: {}".format(str(e)))
            return BadRequestResponse(detail=call_messages.CALL_HANGUP_FAILED)
        except Exception as e:
            holler_service_logger.error(f"Unexpected error hanging up call: {str(e)}")
            raise InternalServerErrorResponse(
                detail=call_messages.UNEXPECTED_ERROR_HANGUP_CALL
            )

    @call_router.post(
        "/transfer",
        response_model=Contract.CallTransferResponse,
        status_code=status.HTTP_200_OK,
    )
    @permission_check(PermissionDependency)
    @inject
    async def transfer_call(
        request: Request,
        transfer_data: Contract.CallTransferRequest,
        call_service: CallService = Depends(Provide[Container.call_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.CallTransferResponse:
        """
        Transfer an in-progress call to another number.

        Args:
            request (Request): The incoming FastAPI request object.
            transfer_data (Contract.CallTransferRequest): call_id (vendor's, passed
                directly by the caller) and destination_number to transfer to.
            call_service (CallService): Service class to handle call logic.
            holler_service_logger (HollerServiceLogger): Logger for tracking events.

        Returns:
            Contract.CallTransferResponse: Result of the transfer request.
        """
        try:
            holler_service_logger.info(
                "Received call transfer request: {}".format(transfer_data)
            )
            auth_ctx = get_current_auth_context(request)
            partner_id: int = auth_ctx.partner_id
            holler_service_logger.info(
                "Partner: {}, initiated call transfer api.".format(partner_id)
            )
            await call_service.transfer_call(
                transfer_data.call_id,
                transfer_data.destination_number,
                partner_id,
                transfer_data.enable_ai_bridge or False,
            )
            holler_service_logger.info(
                "Call transferred successfully: call_id={}".format(
                    transfer_data.call_id
                )
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "success",
                    "message": call_messages.CALL_TRANSFERRED_SUCCESSFULLY,
                },
            )
        except ValueError as e:
            holler_service_logger.error(
                "Error in transferring call api: {}".format(str(e))
            )
            return BadRequestResponse(detail=call_messages.SOMETHING_WENT_WRONG)
        except ResourceNotFound as e:
            holler_service_logger.error(
                "Error in transfer call api resource: {}".format(str(e))
            )
            return ResourceNotFoundResponse(detail=call_messages.SOMETHING_WENT_WRONG)
        except BadRequestError as e:
            holler_service_logger.error(
                "Error in transfer call api resource: {}".format(str(e))
            )
            return BadRequestResponse(detail=call_messages.CALL_TRANSFER_FAILED)
        except Exception as e:
            holler_service_logger.error(f"Unexpected error transferring call: {str(e)}")
            raise InternalServerErrorResponse(
                detail=call_messages.UNEXPECTED_ERROR_TRANSFERRING_CALL
            )

    @call_router.post("/webhook")
    @inject
    async def handle_webhook(
        payload: dict,
        vendor: str = "tata_tele",
        type: str = Query("standard", description="standard | dialer"),
        call_service: CallService = Depends(Provide[Container.call_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ):
        """
        Handle incoming webhook events from a call vendor (default: Tata Tele).

        Args:
            payload (dict): The incoming webhook payload.
            vendor (str): Vendor identifier, defaults to "tata_tele".
            call_service (CallService): Service class to handle call logic.
            holler_service_logger (HollerServiceLogger): Logger for tracking events.

        Returns:
            Any: Response returned by the vendor's webhook handler.
        """
        try:
            webhook_handler: dict = call_service.get_webhook_handler(vendor, type)
            return await webhook_handler.process_webhook(payload)
        except Exception as e:
            holler_service_logger.error("Webhook processing failed: {}".format(str(e)))
            raise InternalServerErrorResponse(detail=str(e))

    @call_router.post("/api/dialplan", status_code=status.HTTP_200_OK)
    @inject
    async def generate_dialplan_response(
        request: Request,
        call_service: CallService = Depends(Provide[Container.call_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> JSONResponse:
        """
        Generate a dynamic dialplan response endpoint delegating to service logic.

        Args:
            request (Request): The incoming FastAPI request object.
            call_service (CallService): Service to handle dialplan logic.
            holler_service_logger (HollerServiceLogger): Logger for tracking events.

        Returns:
            JSONResponse: Response from the dialplan service.
        """
        try:
            holler_service_logger.info(
                "Delegating generate dialplan request to service"
            )
            response = await call_service.generate_dialplan_response(request)
            holler_service_logger.info(
                "Generated dialplan response delegated: {}".format(response)
            )
            return JSONResponse(response)
        except Exception as e:
            holler_service_logger.error(
                f"Error in generate_dialplan_response delegation: {str(e)}"
            )
            raise InternalServerErrorResponse(
                detail=call_messages.UNEXPECTED_ERROR_INITIATING_CALL
            )

    @call_router.get("/details", status_code=status.HTTP_200_OK)
    @permission_check(PermissionDependency)
    @inject
    async def get_call_details(
        request: Request,
        call_id: Optional[str] = Query(
            None, description="Call ID from the vendor (e.g. Tata Tele)"
        ),
        call_uuid: Optional[str] = Query(
            None,
            description="Optional Call UUID for vendors that support it (e.g. Tata Tele)",
        ),
        vendor_config_id: str = Query(..., description="Vendor Configuration ID"),
        call_service: CallService = Depends(Provide[Container.call_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> JSONResponse:
        """
        Fetch call details from vendor using call_id, call_uuid, and vendor_config_id.

        This endpoint reuses the existing CDRUpdateTask via VendorCDRGateway.
        It is designed to be extensible for future vendors.
        """
        try:
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)

            holler_service_logger.info(
                "User {} (partner {}) requested call details - call_id: {}, call_uuid: {}, vendor_config_id: {}".format(
                    user_id, partner_id, call_id, call_uuid, vendor_config_id
                )
            )

            result: Dict[str, Any] = await call_service.get_call_details(
                call_id=call_id,
                call_uuid=call_uuid,
                vendor_config_id=vendor_config_id,
            )

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "success", "data": result},
            )

        except BadRequestError as e:
            holler_service_logger.error(
                "BadRequest in get_call_details: {}".format(str(e))
            )
            return BadRequestResponse(detail=str(e))

        except ResourceNotFound as e:
            holler_service_logger.error(
                "ResourceNotFound in get_call_details: {}".format(str(e))
            )
            return ResourceNotFoundResponse(detail=str(e))

        except Exception as e:
            holler_service_logger.error(
                "Unexpected error in get_call_details: {}".format(str(e))
            )
            raise InternalServerErrorResponse(detail="Failed to fetch call details")

    @call_router.patch(
        "/recovery/clicktocall-agent/fix",
        status_code=status.HTTP_200_OK,
    )
    @inject
    async def fix_clicktocall_agent(
        dry_run: bool = Query(
            False, description="If true, preview only — no writes performed"
        ),
        cdr_repository: CDRRepository = Depends(Provide[Container.cdr_repository]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> JSONResponse:
        """
        Fix wrongly updated agent field for partner_id=2 click-to-call CDRs.
        Scoped to last 2 days (based on created_at timestamp in ms).
        Fetches correct assigned_to agent from Maglo lead_request API using lead_id.
        Processes 30 records per API call.
        """
        try:
            holler_service_logger.info(
                "clicktocall agent recovery triggered — dry_run={}".format(dry_run)
            )

            # ── TIME RANGE ───────────────────────────────────────────
            now_utc = datetime.now(timezone.utc)
            two_days_ago = now_utc - timedelta(days=LOOKBACK_DAYS)
            since_ms = int(two_days_ago.timestamp() * 1000)
            now_ms = int(now_utc.timestamp() * 1000)

            time_range = {
                "from": two_days_ago.isoformat(),
                "to": now_utc.isoformat(),
                "from_ms": since_ms,
                "to_ms": now_ms,
            }

            query = {
                "partner_id": PARTNER_ID,
                # "calling_mode": "clicktocall",
                "lead_id": {"$exists": True, "$ne": None},
                "agent": WRONG_AGENT_ID,
                # "created_at": {
                #     "$gte": since_ms,
                #     "$lte": now_ms,
                # },
            }

            # ── DRY RUN / PREVIEW ────────────────────────────────────
            if dry_run:
                all_affected = await cdr_repository.get_cdrs_by_criteria(query)
                count = len(all_affected)
                sample = all_affected[:5]

                result = {
                    "dry_run": True,
                    "time_range": time_range,
                    "total_affected": count,
                    "sample_records": [
                        {
                            "cdr_id": str(r["_id"]),
                            "customer": r.get("customer"),
                            "lead_id": r.get("lead_id"),
                            "service_board_id": r.get("service_board_id"),
                            "agent": r.get("agent"),
                            "created_at": r.get("created_at"),
                            "created_at_human": (
                                datetime.fromtimestamp(
                                    r["created_at"] / 1000, tz=timezone.utc
                                ).isoformat()
                                if r.get("created_at")
                                else None
                            ),
                        }
                        for r in sample
                    ],
                }
                holler_service_logger.info(
                    "Dry run completed — total_affected: {}".format(count)
                )
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={"status": "success", "data": result},
                )

            # ── APPLY FIX — 30 records per call ──────────────────────
            batch = await cdr_repository.get_cdrs_by_criteria(query, limit=500)
            total_found = len(batch)
            results = []
            fixed = skipped = failed = 0

            async with httpx.AsyncClient(timeout=10) as client:
                for cdr in batch:
                    cdr_id = str(cdr["_id"])
                    lead_id = cdr.get("lead_id")
                    customer_number: str = cdr.get("customer", "")
                    service_board_id = cdr.get("service_board_id")

                    base_record = {
                        "cdr_id": cdr_id,
                        "lead_id": lead_id,
                        "customer_number": customer_number,
                        "service_board_id": service_board_id,
                        "old_agent": WRONG_AGENT_ID,
                        "new_agent": None,
                    }

                    # ── SKIP GUARDS ───────────────────────────────────
                    if not lead_id:
                        results.append(
                            {**base_record, "status": "skipped", "reason": "No lead_id in CDR"}
                        )
                        skipped += 1
                        continue

                    if not customer_number:
                        results.append(
                            {**base_record, "status": "skipped", "reason": "No customer number in CDR"}
                        )
                        skipped += 1
                        continue

                    if not service_board_id:
                        results.append(
                            {**base_record, "status": "skipped", "reason": "No service_board_id in CDR"}
                        )
                        skipped += 1
                        continue

                    try:
                        # ── CALL MAGLO LEAD REQUEST API ───────────────
                        url = "{}/maglo-service/v1/lead_request/{}".format(
                            MAGLO_BASE_URL, lead_id
                        )
                        response = await client.get(
                            url,
                            headers={
                                "accept": "application/json",
                                "Authorization": "Bearer {}".format(MAGLO_TOKEN),
                            },
                        )

                        if response.status_code != 200:
                            holler_service_logger.warning(
                                "Maglo API returned {} for lead_id={}: {}".format(
                                    response.status_code, lead_id, response.text
                                )
                            )
                            results.append(
                                {
                                    **base_record,
                                    "status": "skipped",
                                    "reason": "Maglo API error: status={}".format(
                                        response.status_code
                                    ),
                                }
                            )
                            skipped += 1
                            continue

                        lead_data = response.json().get("data", {})
                        correct_agent = lead_data.get("assigned_to")

                        if not correct_agent:
                            results.append(
                                {
                                    **base_record,
                                    "status": "skipped",
                                    "reason": "Maglo returned no assigned_to",
                                }
                            )
                            skipped += 1
                            continue

                        # ── UPDATE CDR ────────────────────────────────
                        await cdr_repository.update_one(
                            {"_id": cdr["_id"]},
                            {"$set": {"agent": correct_agent}},
                        )

                        holler_service_logger.info(
                            "CDR {} fixed — agent {} → {} (lead_id={})".format(
                                cdr_id, WRONG_AGENT_ID, correct_agent, lead_id
                            )
                        )
                        results.append(
                            {**base_record, "new_agent": correct_agent, "status": "fixed"}
                        )
                        fixed += 1

                    except Exception as e:
                        holler_service_logger.error(
                            "Failed to fix CDR {} (lead_id={}): {}".format(
                                cdr_id, lead_id, str(e)
                            )
                        )
                        results.append(
                            {**base_record, "status": "failed", "reason": str(e)}
                        )
                        failed += 1

            result = {
                "dry_run": False,
                "time_range": time_range,
                "batch_size": 30,
                "total_found": total_found,
                "fixed": fixed,
                "skipped": skipped,
                "failed": failed,
                "results": results,
            }

            holler_service_logger.info(
                "Fix completed — total_found: {}, fixed: {}, skipped: {}, failed: {}".format(
                    total_found, fixed, skipped, failed
                )
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "success", "data": result},
            )

        except Exception as e:
            holler_service_logger.error(
                "Error in fix_clicktocall_agent: {}".format(str(e))
            )
            raise InternalServerErrorResponse(
                detail="Failed to process clicktocall agent recovery"
            )