from fastapi import APIRouter, Request, Depends
from src.components.call_record.dto import Contract
from src.components.call_record.services import CallRecordService
from src.core.container import Container
from dependency_injector.wiring import Provide, inject
from src.components.common.constants import CurrentUserMap
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.loggers.holler_service_logger import HollerServiceLogger
from src.components.common.responses import (
    SuccessResponse,
    InternalServerErrorResponse,
    ResourceCreatedResponse,
    NotFoundResponse,
    BadRequestResponse,
)


class CallRecordController:

    call_record_router = APIRouter()

    @call_record_router.post("/call-record")
    @permission_check(PermissionDependency)
    @inject
    async def create_call_record(
        request: Request,
        record_data: Contract.CreateCallRecordReq,
        service: CallRecordService = Depends(Provide[Container.call_record_service]),
        logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ):
        try:
            logger.info("Received request to add call record")
            current_user: dict = request.state.user
            partner_id = current_user.get(CurrentUserMap.PARTNER_ID)
            user_id = current_user.get(CurrentUserMap.USER_ID)
            resp = await service.create_call_record(record_data, partner_id, user_id)
            return ResourceCreatedResponse(data=resp)
        except Exception as e:
            logger.error(f"Error creating call record: {e}")
            return InternalServerErrorResponse(detail=str(e))

    @call_record_router.get("/call-record/{record_id}")
    @inject
    async def get_call_record(
        request: Request,
        record_id: str,
        service: CallRecordService = Depends(Provide[Container.call_record_service]),
        logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ):
        try:
            logger.info("Received request to get call record by call record id")
            current_user: dict = request.state.user
            partner_id = current_user.get(CurrentUserMap.PARTNER_ID)
            resp = await service.get_call_record(record_id, partner_id)
            if not resp:
                return NotFoundResponse(detail="No matching call record found")
            return SuccessResponse(data=resp)
        except Exception as e:
            logger.error(f"Error retrieving call record: {e}")
            return InternalServerErrorResponse(detail=str(e))

    @call_record_router.get("/call-records")
    @inject
    async def get_all_call_records(
        request: Request,
        service: CallRecordService = Depends(Provide[Container.call_record_service]),
        logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ):
        try:
            logger.info("Received request to get all call record of partner")
            current_user: dict = request.state.user
            partner_id = current_user.get(CurrentUserMap.PARTNER_ID)
            records = await service.get_all_call_records(partner_id)
            return SuccessResponse(data=records)
        except Exception as e:
            logger.error(f"Error fetching all call records: {e}")
            return InternalServerErrorResponse(detail=str(e))

    @call_record_router.put("/call-record/{record_id}")
    @inject
    async def update_call_record(
        request: Request,
        record_id: str,
        record_data: Contract.UpdateCallRecordReq,
        service: CallRecordService = Depends(Provide[Container.call_record_service]),
        logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ):
        try:
            logger.info("Received request to update call record")
            current_user: dict = request.state.user
            partner_id = current_user.get(CurrentUserMap.PARTNER_ID)
            resp = await service.update_call_record(record_id, partner_id, record_data)
            return SuccessResponse(data=resp)
        except ValueError as er:
            logger.error("Validation error: {}".format(er))
            return BadRequestResponse(detail=str(er))
        except Exception as e:
            logger.error(f"Error updating call record: {e}")
            return InternalServerErrorResponse(detail=str(e))

    @call_record_router.delete("/call-record/{record_id}")
    @inject
    async def delete_call_record(
        request: Request,
        record_id: str,
        service: CallRecordService = Depends(Provide[Container.call_record_service]),
        logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ):
        try:
            logger.info("Received request to delete call record")
            current_user: dict = request.state.user
            partner_id = current_user.get(CurrentUserMap.PARTNER_ID)
            await service.delete_call_record(record_id, partner_id)
            return SuccessResponse(data={"message": "Call record deleted successfully"})
        except ValueError as er:
            logger.error("Validation error: {}".format(er))
            return BadRequestResponse(detail=str(er))
        except Exception as e:
            logger.error(f"Error deleting call record: {e}")
            return InternalServerErrorResponse(detail=str(e))
