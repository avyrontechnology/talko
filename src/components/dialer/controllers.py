from typing import Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path, Request, status

from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoAcceptedResponse,
    TalkoBadRequestResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceCreatedResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.dialer.dto import TalkoContract
from src.components.dialer.messages import INVALID_LEAD_LIST_ID, SOMETHING_WENT_WRONG
from src.components.dialer.services import TalkoDialerService
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import TalkoContainer
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoDialerController:
    """
    Controller for managing dialer-related operations with Tata Tele Smartflo.
    Provides endpoints for fetching lead lists and bulk creating leads in a list.
    """

    dialer_router = APIRouter()

    @dialer_router.get(
        "/lead-lists",
        response_model=TalkoContract.LeadListsFetchResponse,
        status_code=status.HTTP_200_OK,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_all_lead_lists(
        request: Request,
        dialer_service: TalkoDialerService = Depends(Provide[TalkoContainer.dialer_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        """
        Fetch all available lead lists (broadcast lists) from Tata Tele.
        """
        try:
            talko_service_logger.info("Fetch all lead lists API called.")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)

            talko_service_logger.info(
                "User: {}, partner: {}, Fetch all lead lists API initiated.".format(
                    user_id, partner_id
                )
            )

            data: list = await dialer_service.fetch_lead_lists(partner_id)

            talko_service_logger.debug(
                "Successfully fetched {} lead lists for partner {}.".format(
                    len(data), partner_id
                )
            )
            talko_service_logger.info(
                "Fetch all lead lists API completed for partner: {}.".format(partner_id)
            )

            return TalkoSuccessResponse(data={"data": data})

        except TalkoBadRequestError as e:
            talko_service_logger.error("Dialer fetch error: {}".format(str(e)))
            return TalkoBadRequestResponse(detail=str(e))

        except TalkoResourceNotFound as e:
            talko_service_logger.error("Resource not found: {}".format(str(e)))
            return TalkoResourceNotFoundResponse(detail=str(e))

        except Exception as e:
            talko_service_logger.error(
                "Unexpected error fetching lead lists: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @dialer_router.post(
        "/lead-lists/{list_id}/leads",
        response_model=TalkoContract.BulkLeadsCreateResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def bulk_create_leads(
        request: Request,
        payload: TalkoContract.BulkLeadsCreateRequest,
        list_id: str = Path(..., description="Unique ID of the target lead list"),
        dialer_service: TalkoDialerService = Depends(Provide[TalkoContainer.dialer_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        """
        Bulk upload/create multiple leads into the specified lead list.
        """
        try:
            talko_service_logger.info(
                "Bulk create leads API called for list_id: {}.".format(list_id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)

            talko_service_logger.info(
                "User: {}, partner: {}, Bulk create leads API initiated for list_id: {} "
                "with {} leads.".format(user_id, partner_id, list_id, len(payload.data))
            )

            result: dict = await dialer_service.bulk_create_leads(
                partner_id=partner_id,
                list_id=list_id,
                payload=payload.model_dump(exclude_unset=True),
            )

            talko_service_logger.debug(
                "Bulk leads creation result for list_id: {} by partner {}: {}".format(
                    list_id, partner_id, result
                )
            )

            talko_service_logger.info(
                "Bulk leads successfully created for list_id: {} by partner {}.".format(
                    list_id, partner_id
                )
            )

            return TalkoAcceptedResponse(
                message="Bulk upload initiated successfully.",
                data={
                    "success": True,
                    "message": "The request is being processed in the background. Later, you can check the status by batch id in batch_status API.",
                },
            )

        except TalkoBadRequestError as e:
            talko_service_logger.error(
                "Bulk leads creation validation error: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=str(e))

        except TalkoResourceNotFound as e:
            talko_service_logger.error(
                "Lead list not found: {} - {}".format(list_id, str(e))
            )
            return TalkoResourceNotFoundResponse(detail=INVALID_LEAD_LIST_ID)

        except Exception as e:
            talko_service_logger.error(
                "Unexpected error during bulk leads creation: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
