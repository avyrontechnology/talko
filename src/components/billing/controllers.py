from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status

from src.components.billing.dto import TalkoContract
from src.components.billing.message import SOMETHING_WENT_WRONG
from src.components.billing.services import TalkoBillingService
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceCreatedResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import TalkoContainer
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoBillingController:
    billing_router = APIRouter()

    @billing_router.post(
        "/rate-cards",
        response_model=TalkoContract.RateCardResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def save_rate_card(
        request: Request,
        payload: TalkoContract.RateCardCreate,
        billing_service: TalkoBillingService = Depends(Provide[TalkoContainer.billing_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            saved = await billing_service.save_rate_card(payload)
            return TalkoResourceCreatedResponse(data=saved)
        except Exception as e:
            talko_service_logger.error(f"Error saving rate card: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @billing_router.get("/rate-cards", response_model=list[TalkoContract.RateCardResponse])
    @permission_check(TalkoPermissionDependency)
    @inject
    async def list_rate_cards(
        request: Request,
        billing_service: TalkoBillingService = Depends(Provide[TalkoContainer.billing_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            return TalkoSuccessResponse(data=await billing_service.list_rate_cards())
        except Exception as e:
            talko_service_logger.error(f"Error listing rate cards: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @billing_router.post("/topup", response_model=TalkoContract.LedgerResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def topup(
        request: Request,
        payload: TalkoContract.TopupRequest,
        billing_service: TalkoBillingService = Depends(Provide[TalkoContainer.billing_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            return TalkoSuccessResponse(data=await billing_service.topup(payload))
        except TalkoBadRequestError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Error applying topup: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @billing_router.get("/ledger", response_model=TalkoContract.LedgerResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_ledger(
        request: Request,
        partner_id: int = Query(...),
        client_id: str | None = Query(None),
        billing_service: TalkoBillingService = Depends(Provide[TalkoContainer.billing_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            return TalkoSuccessResponse(data=await billing_service.get_ledger(partner_id, client_id))
        except TalkoResourceNotFound:
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            talko_service_logger.error(f"Error fetching ledger: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @billing_router.get("/transactions")
    @permission_check(TalkoPermissionDependency)
    @inject
    async def list_transactions(
        request: Request,
        partner_id: int = Query(...),
        limit: int = Query(50, ge=1, le=200),
        billing_service: TalkoBillingService = Depends(Provide[TalkoContainer.billing_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            return TalkoSuccessResponse(data=await billing_service.list_transactions(partner_id, limit))
        except Exception as e:
            talko_service_logger.error(f"Error listing transactions: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @billing_router.post("/price", response_model=TalkoContract.PriceResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def price_call(
        request: Request,
        payload: TalkoContract.PriceRequest,
        billing_service: TalkoBillingService = Depends(Provide[TalkoContainer.billing_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            return TalkoSuccessResponse(data=await billing_service.price_call(payload.call_id, payload.client_id))
        except TalkoResourceNotFound:
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except TalkoBadRequestError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Error pricing call: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
