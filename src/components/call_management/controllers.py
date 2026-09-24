from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from src.components.call_management import messages as call_messages
from src.components.call_management.dto import TalkoContract
from src.components.call_management.services import TalkoCallService
from src.components.common.auth_context import get_current_auth_context
from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceNotFoundResponse,
)
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import TalkoContainer
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoCallController:
    """Controller to handle call-related API endpoints."""

    call_router = APIRouter()

    @call_router.post("", response_model=TalkoContract.CallResponse, status_code=status.HTTP_201_CREATED)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def initiate_call(
        request: Request,
        call_data: TalkoContract.CallCreate,
        call_service: TalkoCallService = Depends(Provide[TalkoContainer.call_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.CallResponse:
        """
        Initiate a new outbound or inbound call.

        Args:
            request (Request): The incoming FastAPI request object.
            call_data (TalkoContract.CallCreate): Data required to initiate the call.
            call_service (TalkoCallService): Service class to handle call logic.
            talko_service_logger (TalkoServiceLogger): Logger for tracking events.

        Returns:
            TalkoContract.CallResponse: The response containing call initiation details.
        """
        try:
            talko_service_logger.info(f"Received call request: {call_data}")
            auth_ctx = get_current_auth_context(request)
            user_id: int = auth_ctx.user_id  # None when called via API-KEY
            partner_id: int = auth_ctx.partner_id
            talko_service_logger.info(f"User: {user_id}, partner: {partner_id}, initiated call api.")
            call_response: TalkoContract.CallResponse = await call_service.initiate_call(call_data, user_id, partner_id)
            talko_service_logger.info(f"Call initiated successfully: {call_response}")
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content={
                    "status": "success",
                    "message": call_messages.CALL_PLACED_SUCCESSFULLY,
                },
            )
        except ValueError as e:
            talko_service_logger.error(f"Error in initiating call api: {str(e)}")
            return TalkoBadRequestResponse(detail=call_messages.SOMETHING_WENT_WRONG)
        except TalkoResourceNotFound as e:
            talko_service_logger.error(f"Error in initiate call api resource: {str(e)}")
            return TalkoResourceNotFoundResponse(detail=call_messages.SOMETHING_WENT_WRONG)
        except TalkoBadRequestError as e:
            talko_service_logger.error(f"Error in initiate call api resource: {str(e)}")
            return TalkoBadRequestResponse(detail=call_messages.CALL_INITIATION_FAILED)
        except Exception as e:
            talko_service_logger.error(f"Unexpected error initiating call: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=call_messages.UNEXPECTED_ERROR_INITIATING_CALL)

    @call_router.post(
        "/hangup",
        response_model=TalkoContract.HangupCallResponse,
        status_code=status.HTTP_200_OK,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def hangup_call(
        request: Request,
        hangup_data: TalkoContract.HangupCallRequest,
        call_service: TalkoCallService = Depends(Provide[TalkoContainer.call_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> JSONResponse:
        """
        Hang up an ongoing call via the partner's assigned vendor.

        Args:
            request (Request): The incoming FastAPI request object.
            hangup_data (TalkoContract.HangupCallRequest): Data required to hang up the call.
            call_service (TalkoCallService): Service class to handle call logic.
            talko_service_logger (TalkoServiceLogger): Logger for tracking events.

        Returns:
            JSONResponse: The vendor's hangup result.
        """
        try:
            talko_service_logger.info(f"Received hangup call request: {hangup_data}")
            auth_ctx = get_current_auth_context(request)
            user_id: int | None = auth_ctx.user_id  # None when called via API-KEY
            partner_id: int = auth_ctx.partner_id
            talko_service_logger.info(f"User: {user_id}, partner: {partner_id}, initiated hangup call api.")
            hangup_response: TalkoContract.HangupCallResponse = await call_service.hangup_call(
                hangup_data.call_id,
                user_id,
                partner_id,
                hangup_data.enable_ai_bridge or False,
            )
            talko_service_logger.info(f"Hangup call completed: {hangup_response}")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "success",
                    "data": hangup_response.model_dump(),
                },
            )
        except TalkoResourceNotFound as e:
            talko_service_logger.error(f"Error in hangup call api resource: {str(e)}")
            return TalkoResourceNotFoundResponse(detail=call_messages.SOMETHING_WENT_WRONG)
        except ValueError as e:
            talko_service_logger.error(f"Error in hangup call api: {str(e)}")
            return TalkoBadRequestResponse(detail=call_messages.CALL_HANGUP_FAILED)
        except Exception as e:
            talko_service_logger.error(f"Unexpected error hanging up call: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=call_messages.UNEXPECTED_ERROR_HANGUP_CALL)

    @call_router.post(
        "/transfer",
        response_model=TalkoContract.CallTransferResponse,
        status_code=status.HTTP_200_OK,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def transfer_call(
        request: Request,
        transfer_data: TalkoContract.CallTransferRequest,
        call_service: TalkoCallService = Depends(Provide[TalkoContainer.call_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.CallTransferResponse:
        """
        Transfer an in-progress call to another number.

        Args:
            request (Request): The incoming FastAPI request object.
            transfer_data (TalkoContract.CallTransferRequest): call_id (vendor's, passed
                directly by the caller) and destination_number to transfer to.
            call_service (TalkoCallService): Service class to handle call logic.
            talko_service_logger (TalkoServiceLogger): Logger for tracking events.

        Returns:
            TalkoContract.CallTransferResponse: Result of the transfer request.
        """
        try:
            talko_service_logger.info(f"Received call transfer request: {transfer_data}")
            auth_ctx = get_current_auth_context(request)
            partner_id: int = auth_ctx.partner_id
            talko_service_logger.info(f"Partner: {partner_id}, initiated call transfer api.")
            await call_service.transfer_call(
                transfer_data.call_id,
                transfer_data.destination_number,
                partner_id,
                transfer_data.enable_ai_bridge or False,
            )
            talko_service_logger.info(f"Call transferred successfully: call_id={transfer_data.call_id}")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "success",
                    "message": call_messages.CALL_TRANSFERRED_SUCCESSFULLY,
                },
            )
        except ValueError as e:
            talko_service_logger.error(f"Error in transferring call api: {str(e)}")
            return TalkoBadRequestResponse(detail=call_messages.SOMETHING_WENT_WRONG)
        except TalkoResourceNotFound as e:
            talko_service_logger.error(f"Error in transfer call api resource: {str(e)}")
            return TalkoResourceNotFoundResponse(detail=call_messages.SOMETHING_WENT_WRONG)
        except TalkoBadRequestError as e:
            talko_service_logger.error(f"Error in transfer call api resource: {str(e)}")
            return TalkoBadRequestResponse(detail=call_messages.CALL_TRANSFER_FAILED)
        except Exception as e:
            talko_service_logger.error(f"Unexpected error transferring call: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=call_messages.UNEXPECTED_ERROR_TRANSFERRING_CALL)

    # NOTE (grpc disabled for now): gRPC telephony control plane commented out.
    # @call_router.post(
    #     "/grpc/hangup",
    #     status_code=status.HTTP_200_OK,
    # )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def grpc_hangup_call(
        request: Request,
        hangup_data: TalkoContract.GrpcHangupRequest,
        call_service: TalkoCallService = Depends(Provide[TalkoContainer.call_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> JSONResponse:
        """Hang up via the gRPC TelephonyControl plane (non-Tata vendors)."""
        try:
            response = await call_service.grpc_hangup_call(hangup_data.call_id, hangup_data.vendor_config_id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "success", "data": response.model_dump()},
            )
        except TalkoResourceNotFound as e:
            talko_service_logger.error(f"gRPC hangup resource missing: {str(e)}")
            return TalkoResourceNotFoundResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"gRPC hangup failed: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    # NOTE (grpc disabled for now): gRPC telephony control plane commented out.
    # @call_router.post(
    #     "/grpc/transfer",
    #     status_code=status.HTTP_200_OK,
    # )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def grpc_transfer_call(
        request: Request,
        transfer_data: TalkoContract.GrpcTransferRequest,
        call_service: TalkoCallService = Depends(Provide[TalkoContainer.call_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> JSONResponse:
        """Blind-transfer via the gRPC TelephonyControl plane."""
        try:
            result = await call_service.grpc_transfer_call(
                transfer_data.call_id,
                transfer_data.destination_number,
                transfer_data.vendor_config_id,
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "success", "data": result},
            )
        except TalkoResourceNotFound as e:
            talko_service_logger.error(f"gRPC transfer resource missing: {str(e)}")
            return TalkoResourceNotFoundResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"gRPC transfer failed: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    # NOTE (grpc disabled for now): gRPC telephony control plane commented out.
    # @call_router.get(
    #     "/grpc/status",
    #     status_code=status.HTTP_200_OK,
    # )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def grpc_call_status(
        request: Request,
        call_id: str = Query(...),
        vendor_config_id: str = Query(""),
        call_service: TalkoCallService = Depends(Provide[TalkoContainer.call_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> JSONResponse:
        """Poll signalling state via the gRPC TelephonyControl plane."""
        try:
            result = await call_service.grpc_call_status(call_id, vendor_config_id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "success", "data": result},
            )
        except TalkoResourceNotFound as e:
            talko_service_logger.error(f"gRPC status resource missing: {str(e)}")
            return TalkoResourceNotFoundResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"gRPC status failed: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @call_router.post("/supervise", status_code=status.HTTP_200_OK)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def start_supervise(
        request: Request,
        payload: TalkoContract.SuperviseRequest,
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
        supervision_service=Depends(Provide[TalkoContainer.supervision_service]),
    ) -> JSONResponse:
        """Start a supervisor session (listen | whisper | barge) on a live call."""
        try:
            auth_ctx = get_current_auth_context(request)
            session = await supervision_service.start_supervise(
                call_id=payload.call_id,
                partner_id=auth_ctx.partner_id,
                supervisor_id=payload.supervisor_id,
                mode=payload.mode,
                room_name=payload.room_name,
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "success", "data": session},
            )
        except TalkoBadRequestError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Supervise start failed: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @call_router.delete("/supervise", status_code=status.HTTP_200_OK)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def stop_supervise(
        request: Request,
        call_id: str = Query(...),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
        supervision_service=Depends(Provide[TalkoContainer.supervision_service]),
    ) -> JSONResponse:
        """End the supervisor session on a live call."""
        try:
            auth_ctx = get_current_auth_context(request)
            session = await supervision_service.stop_supervise(call_id, auth_ctx.partner_id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "success", "data": session},
            )
        except TalkoResourceNotFound as e:
            return TalkoResourceNotFoundResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Supervise stop failed: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @call_router.get("/supervise", status_code=status.HTTP_200_OK)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_supervise(
        request: Request,
        call_id: str = Query(...),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
        supervision_service=Depends(Provide[TalkoContainer.supervision_service]),
    ) -> JSONResponse:
        """Fetch the active supervisor session for a call (if any)."""
        try:
            session = await supervision_service.get_supervise(call_id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "success", "data": session},
            )
        except Exception as e:
            talko_service_logger.error(f"Supervise fetch failed: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @call_router.post("/transfer/attended-start", status_code=status.HTTP_200_OK)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def attended_transfer_start(
        request: Request,
        payload: TalkoContract.AttendedTransferStart,
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
        supervision_service=Depends(Provide[TalkoContainer.supervision_service]),
    ) -> JSONResponse:
        """Stage 1 of warm transfer: park consult intent for target_number."""
        try:
            auth_ctx = get_current_auth_context(request)
            staged = await supervision_service.start_attended(
                call_id=payload.call_id,
                partner_id=auth_ctx.partner_id,
                target_number=payload.target_number,
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "success", "data": staged},
            )
        except TalkoBadRequestError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Attended start failed: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @call_router.post("/transfer/attended-complete", status_code=status.HTTP_200_OK)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def attended_transfer_complete(
        request: Request,
        call_id: str = Query(...),
        destination_number: str = Query(""),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
        supervision_service=Depends(Provide[TalkoContainer.supervision_service]),
        call_service: TalkoCallService = Depends(Provide[TalkoContainer.call_service]),
    ) -> JSONResponse:
        """Stage 2 of warm transfer: run the blind-transfer leg, then clear stage."""
        try:
            auth_ctx = get_current_auth_context(request)
            staged = await supervision_service.complete_attended(call_id, auth_ctx.partner_id)
            target = destination_number or staged.get("target_number", "")
            vendor_response = await call_service.transfer_call(call_id, target, auth_ctx.partner_id, False)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "success",
                    "data": {"staged": staged, "vendor_response": vendor_response},
                },
            )
        except TalkoResourceNotFound as e:
            return TalkoResourceNotFoundResponse(detail=str(e))
        except TalkoBadRequestError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Attended complete failed: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @call_router.post("/webhook")
    @inject
    async def handle_webhook(
        payload: dict,
        vendor: str = "tata_tele",
        type: str = Query("standard", description="standard | dialer"),
        call_service: TalkoCallService = Depends(Provide[TalkoContainer.call_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        """
        Handle incoming webhook events from a call vendor (default: Tata Tele).

        Args:
            payload (dict): The incoming webhook payload.
            vendor (str): Vendor identifier, defaults to "tata_tele".
            call_service (TalkoCallService): Service class to handle call logic.
            talko_service_logger (TalkoServiceLogger): Logger for tracking events.

        Returns:
            Any: Response returned by the vendor's webhook handler.
        """
        try:
            webhook_handler: dict = call_service.get_webhook_handler(vendor, type)
            return await webhook_handler.process_webhook(payload)
        except Exception as e:
            talko_service_logger.error(f"Webhook processing failed: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @call_router.post("/api/dialplan", status_code=status.HTTP_200_OK)
    @inject
    async def generate_dialplan_response(
        request: Request,
        call_service: TalkoCallService = Depends(Provide[TalkoContainer.call_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> JSONResponse:
        """
        Generate a dynamic dialplan response endpoint delegating to service logic.

        Args:
            request (Request): The incoming FastAPI request object.
            call_service (TalkoCallService): Service to handle dialplan logic.
            talko_service_logger (TalkoServiceLogger): Logger for tracking events.

        Returns:
            JSONResponse: Response from the dialplan service.
        """
        try:
            talko_service_logger.info("Delegating generate dialplan request to service")
            response = await call_service.generate_dialplan_response(request)
            talko_service_logger.info(f"Generated dialplan response delegated: {response}")
            return JSONResponse(response)
        except Exception as e:
            talko_service_logger.error(f"Error in generate_dialplan_response delegation: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=call_messages.UNEXPECTED_ERROR_INITIATING_CALL)

    @call_router.get("/details", status_code=status.HTTP_200_OK)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_call_details(
        request: Request,
        call_id: str | None = Query(None, description="Call ID from the vendor (e.g. Tata Tele)"),
        call_uuid: str | None = Query(
            None,
            description="Optional Call UUID for vendors that support it (e.g. Tata Tele)",
        ),
        vendor_config_id: str = Query(..., description="Vendor Configuration ID"),
        call_service: TalkoCallService = Depends(Provide[TalkoContainer.call_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> JSONResponse:
        """
        Fetch call details from vendor using call_id, call_uuid, and vendor_config_id.

        This endpoint reuses the existing TalkoCDRUpdateTask via TalkoVendorCDRGateway.
        It is designed to be extensible for future vendors.
        """
        try:
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)

            talko_service_logger.info(
                f"User {user_id} (partner {partner_id}) requested call details - call_id: {call_id}, call_uuid: {call_uuid}, vendor_config_id: {vendor_config_id}"
            )

            result: dict[str, Any] = await call_service.get_call_details(
                call_id=call_id,
                call_uuid=call_uuid,
                vendor_config_id=vendor_config_id,
            )

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "success", "data": result},
            )

        except TalkoBadRequestError as e:
            talko_service_logger.error(f"BadRequest in get_call_details: {str(e)}")
            return TalkoBadRequestResponse(detail=str(e))

        except TalkoResourceNotFound as e:
            talko_service_logger.error(f"TalkoResourceNotFound in get_call_details: {str(e)}")
            return TalkoResourceNotFoundResponse(detail=str(e))

        except Exception as e:
            talko_service_logger.error(f"Unexpected error in get_call_details: {str(e)}")
            return TalkoInternalServerErrorResponse(detail="Failed to fetch call details")
