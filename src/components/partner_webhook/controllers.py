from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status

from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceCreatedResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.partner_webhook.constant import DEFAULT_DELIVERY_ATTEMPTS_LIMIT
from src.components.partner_webhook.dto import TalkoContract
from src.components.partner_webhook.message import SOMETHING_WENT_WRONG
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import TalkoContainer
from src.exceptions import TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger

from .services import TalkoPartnerWebhookService


class TalkoPartnerWebhookController:
    """Admin-only endpoints for configuring partner webhook delivery and
    inspecting delivery attempts for support/debugging. Protected by the
    existing JWT+RBAC stack — no partner self-serve.
    """

    router = APIRouter()

    @router.post(
        "/config",
        response_model=TalkoContract.WebhookConfigResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def create_webhook_config(
        request: Request,
        data: TalkoContract.WebhookConfigCreate,
        partner_webhook_service: TalkoPartnerWebhookService = Depends(
            Provide[TalkoContainer.partner_webhook_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            current_user_data: dict = request.state.user
            user_id = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            created = await partner_webhook_service.create_webhook_config(data, user_id)
            return TalkoResourceCreatedResponse(data=created)
        except ValueError as e:
            talko_service_logger.error(
                "Error creating webhook config: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error creating webhook config: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.patch(
        "/config/{partner_id}", response_model=TalkoContract.WebhookConfigResponse
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def update_webhook_config(
        request: Request,
        partner_id: int,
        data: TalkoContract.WebhookConfigUpdate,
        partner_webhook_service: TalkoPartnerWebhookService = Depends(
            Provide[TalkoContainer.partner_webhook_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            updated = await partner_webhook_service.update_webhook_config(
                partner_id, data
            )
            return TalkoSuccessResponse(data=updated)
        except ValueError as e:
            talko_service_logger.error(
                "Error updating webhook config for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error updating webhook config for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.get(
        "/config/{partner_id}", response_model=TalkoContract.WebhookConfigResponse
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_webhook_config(
        request: Request,
        partner_id: int,
        partner_webhook_service: TalkoPartnerWebhookService = Depends(
            Provide[TalkoContainer.partner_webhook_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            config = await partner_webhook_service.get_webhook_config(partner_id)
            return TalkoSuccessResponse(data=config)
        except TalkoResourceNotFound:
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error getting webhook config for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.get(
        "/deliveries", response_model=list[TalkoContract.DeliveryAttemptResponse]
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def list_deliveries(
        request: Request,
        partner_id: int = Query(...),
        limit: int = Query(DEFAULT_DELIVERY_ATTEMPTS_LIMIT),
        partner_webhook_service: TalkoPartnerWebhookService = Depends(
            Provide[TalkoContainer.partner_webhook_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        try:
            attempts = await partner_webhook_service.list_delivery_attempts(
                partner_id, limit
            )
            return TalkoSuccessResponse(data=attempts)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error listing webhook deliveries for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
