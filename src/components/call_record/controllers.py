from fastapi import APIRouter, Request, Depends
from src.components.call_record.dto import TalkoContract
from src.components.call_record.services import TalkoCallRecordService
from src.core.container import TalkoContainer
from dependency_injector.wiring import Provide, inject
from src.components.common.constants import TalkoCurrentUserMap
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.components.common.responses import (
    TalkoSuccessResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceCreatedResponse,
    TalkoNotFoundResponse,
    TalkoBadRequestResponse,
)


class TalkoCallRecordController:

    call_record_router = APIRouter()

    @call_record_router.post("/call-record")
    @permission_check(TalkoPermissionDependency)
    @inject
    async def create_call_record(
        request: Request,
        record_data: TalkoContract.CreateCallRecordReq,
        service: TalkoCallRecordService = Depends(Provide[TalkoContainer.call_record_service]),
        logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            logger.info("Received request to add call record")
            current_user: dict = request.state.user
            partner_id = current_user.get(TalkoCurrentUserMap.PARTNER_ID)
            user_id = current_user.get(TalkoCurrentUserMap.USER_ID)
            resp = await service.create_call_record(record_data, partner_id, user_id)
            return TalkoResourceCreatedResponse(data=resp)
        except Exception as e:
            logger.error(f"Error creating call record: {e}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @call_record_router.get("/call-record/{record_id}")
    @inject
    async def get_call_record(
        request: Request,
        record_id: str,
        service: TalkoCallRecordService = Depends(Provide[TalkoContainer.call_record_service]),
        logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            logger.info("Received request to get call record by call record id")
            current_user: dict = request.state.user
            partner_id = current_user.get(TalkoCurrentUserMap.PARTNER_ID)
            resp = await service.get_call_record(record_id, partner_id)
            if not resp:
                return TalkoNotFoundResponse(detail="No matching call record found")
            return TalkoSuccessResponse(data=resp)
        except Exception as e:
            logger.error(f"Error retrieving call record: {e}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @call_record_router.get("/call-records")
    @inject
    async def get_all_call_records(
        request: Request,
        service: TalkoCallRecordService = Depends(Provide[TalkoContainer.call_record_service]),
        logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            logger.info("Received request to get all call record of partner")
            current_user: dict = request.state.user
            partner_id = current_user.get(TalkoCurrentUserMap.PARTNER_ID)
            records = await service.get_all_call_records(partner_id)
            return TalkoSuccessResponse(data=records)
        except Exception as e:
            logger.error(f"Error fetching all call records: {e}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @call_record_router.put("/call-record/{record_id}")
    @inject
    async def update_call_record(
        request: Request,
        record_id: str,
        record_data: TalkoContract.UpdateCallRecordReq,
        service: TalkoCallRecordService = Depends(Provide[TalkoContainer.call_record_service]),
        logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            logger.info("Received request to update call record")
            current_user: dict = request.state.user
            partner_id = current_user.get(TalkoCurrentUserMap.PARTNER_ID)
            resp = await service.update_call_record(record_id, partner_id, record_data)
            return TalkoSuccessResponse(data=resp)
        except ValueError as er:
            logger.error("Validation error: {}".format(er))
            return TalkoBadRequestResponse(detail=str(er))
        except Exception as e:
            logger.error(f"Error updating call record: {e}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @call_record_router.delete("/call-record/{record_id}")
    @inject
    async def delete_call_record(
        request: Request,
        record_id: str,
        service: TalkoCallRecordService = Depends(Provide[TalkoContainer.call_record_service]),
        logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            logger.info("Received request to delete call record")
            current_user: dict = request.state.user
            partner_id = current_user.get(TalkoCurrentUserMap.PARTNER_ID)
            await service.delete_call_record(record_id, partner_id)
            return TalkoSuccessResponse(data={"message": "Call record deleted successfully"})
        except ValueError as er:
            logger.error("Validation error: {}".format(er))
            return TalkoBadRequestResponse(detail=str(er))
        except Exception as e:
            logger.error(f"Error deleting call record: {e}")
            return TalkoInternalServerErrorResponse(detail=str(e))
