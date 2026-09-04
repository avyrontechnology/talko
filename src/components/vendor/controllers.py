from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, status

from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceCreatedResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.vendor.dto import TalkoContract
from src.components.vendor.message import NOT_FOUND
from src.components.vendor.services import TalkoVendorService
from src.core.container import TalkoContainer
from src.exceptions import TalkoConflictError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.common_messages import VENDOR_NOT_FOUND


class TalkoVendorController:
    vendor_router = APIRouter()

    @vendor_router.post(
        "", response_model=TalkoContract.VendorResponse, status_code=status.HTTP_201_CREATED
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def create_vendor(
        request: Request,
        vendor_data: TalkoContract.VendorCreate,
        vendor_service: TalkoVendorService = Depends(Provide[TalkoContainer.vendor_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.VendorResponse:
        try:
            talko_service_logger.info("Received vendor data: {}.".format(vendor_data))
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, create vendor api initiated".format(
                    user_id, partner_id
                )
            )
            created_vendor: TalkoContract.VendorResponse = (
                await vendor_service.create_vendor(vendor_data)
            )
            talko_service_logger.info(
                "Vendor created successfully: {}.".format(created_vendor)
            )
            return TalkoResourceCreatedResponse(data=created_vendor)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error creating vendor: {}.".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=str(e))

    @vendor_router.get("", response_model=list[TalkoContract.GetAllVendorData])
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_all_vendors(
        request: Request,
        vendor_service: TalkoVendorService = Depends(Provide[TalkoContainer.vendor_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> list[TalkoContract.GetAllVendorData]:
        try:
            talko_service_logger.info("Get all vendor data.")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, get all vendors data api initiated.".format(
                    user_id, partner_id
                )
            )
            vendors: list[TalkoContract.GetAllVendorData] = (
                await vendor_service.get_vendors()
            )
            talko_service_logger.info("Retrieved {} vendors.".format(len(vendors)))
            return TalkoSuccessResponse(data=vendors)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error retrieving vendors: {}.".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=str(e))

    @vendor_router.get(
        "/{vendor_id}", response_model=TalkoContract.GetVendorDataOnTheBasisOfId
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_vendor_by_id(
        request: Request,
        vendor_id: str,
        vendor_service: TalkoVendorService = Depends(Provide[TalkoContainer.vendor_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.GetVendorDataOnTheBasisOfId:
        try:
            talko_service_logger.info(
                "Retrieving vendor with ID: {}.".format(vendor_id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, get vendor by id api initiated.".format(
                    user_id, partner_id
                )
            )
            vendor: TalkoContract.GetVendorDataOnTheBasisOfId = (
                await vendor_service.get_vendor_by_id(vendor_id)
            )
            talko_service_logger.info(
                "Vendor retrieved successfully: {}.".format(vendor)
            )
            return TalkoSuccessResponse(data=vendor)
        except ValueError as e:
            talko_service_logger.error("Error retrieving vendor: {}".format(str(e)))
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoResourceNotFound as e:
            talko_service_logger.error(VENDOR_NOT_FOUND.format(str(e)))
            return TalkoResourceNotFoundResponse(detail=NOT_FOUND)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error retrieving vendor: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=str(e))

    @vendor_router.patch(
        "/{vendor_id}/activate", response_model=TalkoContract.VendorResponse
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def activate_vendor(
        request: Request,
        vendor_id: str,
        vendor_service: TalkoVendorService = Depends(Provide[TalkoContainer.vendor_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.VendorResponse:
        try:
            talko_service_logger.info(
                "Activating vendor with ID: {}".format(vendor_id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, activate vendor api initiated.".format(
                    user_id, partner_id
                )
            )
            updated_vendor: TalkoContract.VendorResponse = (
                await vendor_service.activate_vendor(vendor_id)
            )
            talko_service_logger.info(
                "Vendor activated successfully: {}".format(updated_vendor)
            )
            return TalkoSuccessResponse(data=updated_vendor)
        except ValueError as e:
            talko_service_logger.error("Error activating vendor: {}.".format(str(e)))
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoResourceNotFound as e:
            talko_service_logger.error(VENDOR_NOT_FOUND.format(str(e)))
            return TalkoResourceNotFoundResponse(detail=NOT_FOUND)
        except TalkoConflictError as e:
            talko_service_logger.error(
                "Vendor with ID {} is already active.".format(vendor_id)
            )
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error activating vendor: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=str(e))

    @vendor_router.patch(
        "/{vendor_id}/deactivate", response_model=TalkoContract.VendorResponse
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def deactivate_vendor(
        request: Request,
        vendor_id: str,
        vendor_service: TalkoVendorService = Depends(Provide[TalkoContainer.vendor_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.VendorResponse:
        try:
            talko_service_logger.info(
                "Deactivating vendor with ID: {}".format(vendor_id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, deactivate vendor api initiated.".format(
                    user_id, partner_id
                )
            )
            updated_vendor: TalkoContract.VendorResponse = (
                await vendor_service.deactivate_vendor(vendor_id)
            )
            talko_service_logger.info(
                "Vendor deactivated successfully: {}".format(updated_vendor)
            )
            return TalkoSuccessResponse(data=updated_vendor)
        except ValueError as e:
            talko_service_logger.error("Error deactivating vendor: {}".format(str(e)))
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoResourceNotFound as e:
            return TalkoResourceNotFoundResponse(detail=NOT_FOUND)
        except TalkoConflictError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error deactivating vendor: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=str(e))
