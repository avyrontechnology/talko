from typing import Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path, Request, status

from src.components.common.constants import CurrentUserMap
from src.components.common.responses import (
    AcceptedResponse,
    BadRequestResponse,
    InternalServerErrorResponse,
    ResourceCreatedResponse,
    ResourceNotFoundResponse,
    SuccessResponse,
)
from src.components.dialer.dto import Contract
from src.components.dialer.messages import INVALID_LEAD_LIST_ID, SOMETHING_WENT_WRONG
from src.components.dialer.services import DialerService
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import BadRequestError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger


class DialerController:
    """
    Controller for managing dialer-related operations with Tata Tele Smartflo.
    Provides endpoints for fetching lead lists and bulk creating leads in a list.
    """

    dialer_router = APIRouter()

    @dialer_router.get(
        "/lead-lists",
        response_model=Contract.LeadListsFetchResponse,
        status_code=status.HTTP_200_OK,
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_all_lead_lists(
        request: Request,
        dialer_service: DialerService = Depends(Provide[Container.dialer_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ):
        """
        Fetch all available lead lists (broadcast lists) from Tata Tele.
        """
        try:
            holler_service_logger.info("Fetch all lead lists API called.")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)

            holler_service_logger.info(
                "User: {}, partner: {}, Fetch all lead lists API initiated.".format(
                    user_id, partner_id
                )
            )

            data: list = await dialer_service.fetch_lead_lists(partner_id)

            holler_service_logger.debug(
                "Successfully fetched {} lead lists for partner {}.".format(
                    len(data), partner_id
                )
            )
            holler_service_logger.info(
                "Fetch all lead lists API completed for partner: {}.".format(partner_id)
            )

            return SuccessResponse(data={"data": data})

        except BadRequestError as e:
            holler_service_logger.error("Dialer fetch error: {}".format(str(e)))
            return BadRequestResponse(detail=str(e))

        except ResourceNotFound as e:
            holler_service_logger.error("Resource not found: {}".format(str(e)))
            return ResourceNotFoundResponse(detail=str(e))

        except Exception as e:
            holler_service_logger.error(
                "Unexpected error fetching lead lists: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @dialer_router.post(
        "/lead-lists/{list_id}/leads",
        response_model=Contract.BulkLeadsCreateResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(PermissionDependency)
    @inject
    async def bulk_create_leads(
        request: Request,
        payload: Contract.BulkLeadsCreateRequest,
        list_id: str = Path(..., description="Unique ID of the target lead list"),
        dialer_service: DialerService = Depends(Provide[Container.dialer_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ):
        """
        Bulk upload/create multiple leads into the specified lead list.
        """
        try:
            holler_service_logger.info(
                "Bulk create leads API called for list_id: {}.".format(list_id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)

            holler_service_logger.info(
                "User: {}, partner: {}, Bulk create leads API initiated for list_id: {} "
                "with {} leads.".format(user_id, partner_id, list_id, len(payload.data))
            )

            result: dict = await dialer_service.bulk_create_leads(
                partner_id=partner_id,
                list_id=list_id,
                payload=payload.model_dump(exclude_unset=True),
            )

            holler_service_logger.debug(
                "Bulk leads creation result for list_id: {} by partner {}: {}".format(
                    list_id, partner_id, result
                )
            )

            holler_service_logger.info(
                "Bulk leads successfully created for list_id: {} by partner {}.".format(
                    list_id, partner_id
                )
            )

            return AcceptedResponse(
                message="Bulk upload initiated successfully.",
                data={
                    "success": True,
                    "message": "The request is being processed in the background. Later, you can check the status by batch id in batch_status API.",
                },
            )

        except BadRequestError as e:
            holler_service_logger.error(
                "Bulk leads creation validation error: {}".format(str(e))
            )
            return BadRequestResponse(detail=str(e))

        except ResourceNotFound as e:
            holler_service_logger.error(
                "Lead list not found: {} - {}".format(list_id, str(e))
            )
            return ResourceNotFoundResponse(detail=INVALID_LEAD_LIST_ID)

        except Exception as e:
            holler_service_logger.error(
                "Unexpected error during bulk leads creation: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
