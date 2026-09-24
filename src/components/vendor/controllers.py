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

    @vendor_router.post("", response_model=TalkoContract.VendorResponse, status_code=status.HTTP_201_CREATED)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def create_vendor(
        request: Request,
        vendor_data: TalkoContract.VendorCreate,
        vendor_service: TalkoVendorService = Depends(Provide[TalkoContainer.vendor_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.VendorResponse:
        try:
            talko_service_logger.info(f"Received vendor data: {vendor_data}.")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(f"User: {user_id}, partner: {partner_id}, create vendor api initiated")
            created_vendor: TalkoContract.VendorResponse = await vendor_service.create_vendor(vendor_data)
            talko_service_logger.info(f"Vendor created successfully: {created_vendor}.")
            return TalkoResourceCreatedResponse(data=created_vendor)
        except Exception as e:
            talko_service_logger.error(f"Unexpected error creating vendor: {str(e)}.")
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
            talko_service_logger.info(f"User: {user_id}, partner: {partner_id}, get all vendors data api initiated.")
            vendors: list[TalkoContract.GetAllVendorData] = await vendor_service.get_vendors()
            talko_service_logger.info(f"Retrieved {len(vendors)} vendors.")
            return TalkoSuccessResponse(data=vendors)
        except Exception as e:
            talko_service_logger.error(f"Unexpected error retrieving vendors: {str(e)}.")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @vendor_router.get("/{vendor_id}", response_model=TalkoContract.GetVendorDataOnTheBasisOfId)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_vendor_by_id(
        request: Request,
        vendor_id: str,
        vendor_service: TalkoVendorService = Depends(Provide[TalkoContainer.vendor_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.GetVendorDataOnTheBasisOfId:
        try:
            talko_service_logger.info(f"Retrieving vendor with ID: {vendor_id}.")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(f"User: {user_id}, partner: {partner_id}, get vendor by id api initiated.")
            vendor: TalkoContract.GetVendorDataOnTheBasisOfId = await vendor_service.get_vendor_by_id(vendor_id)
            talko_service_logger.info(f"Vendor retrieved successfully: {vendor}.")
            return TalkoSuccessResponse(data=vendor)
        except ValueError as e:
            talko_service_logger.error(f"Error retrieving vendor: {str(e)}")
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoResourceNotFound as e:
            talko_service_logger.error(VENDOR_NOT_FOUND.format(str(e)))
            return TalkoResourceNotFoundResponse(detail=NOT_FOUND)
        except Exception as e:
            talko_service_logger.error(f"Unexpected error retrieving vendor: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @vendor_router.patch("/{vendor_id}/activate", response_model=TalkoContract.VendorResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def activate_vendor(
        request: Request,
        vendor_id: str,
        vendor_service: TalkoVendorService = Depends(Provide[TalkoContainer.vendor_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.VendorResponse:
        try:
            talko_service_logger.info(f"Activating vendor with ID: {vendor_id}")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(f"User: {user_id}, partner: {partner_id}, activate vendor api initiated.")
            updated_vendor: TalkoContract.VendorResponse = await vendor_service.activate_vendor(vendor_id)
            talko_service_logger.info(f"Vendor activated successfully: {updated_vendor}")
            return TalkoSuccessResponse(data=updated_vendor)
        except ValueError as e:
            talko_service_logger.error(f"Error activating vendor: {str(e)}.")
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoResourceNotFound as e:
            talko_service_logger.error(VENDOR_NOT_FOUND.format(str(e)))
            return TalkoResourceNotFoundResponse(detail=NOT_FOUND)
        except TalkoConflictError as e:
            talko_service_logger.error(f"Vendor with ID {vendor_id} is already active.")
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Unexpected error activating vendor: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @vendor_router.patch("/{vendor_id}/deactivate", response_model=TalkoContract.VendorResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def deactivate_vendor(
        request: Request,
        vendor_id: str,
        vendor_service: TalkoVendorService = Depends(Provide[TalkoContainer.vendor_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.VendorResponse:
        try:
            talko_service_logger.info(f"Deactivating vendor with ID: {vendor_id}")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(f"User: {user_id}, partner: {partner_id}, deactivate vendor api initiated.")
            updated_vendor: TalkoContract.VendorResponse = await vendor_service.deactivate_vendor(vendor_id)
            talko_service_logger.info(f"Vendor deactivated successfully: {updated_vendor}")
            return TalkoSuccessResponse(data=updated_vendor)
        except ValueError as e:
            talko_service_logger.error(f"Error deactivating vendor: {str(e)}")
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoResourceNotFound:
            return TalkoResourceNotFoundResponse(detail=NOT_FOUND)
        except TalkoConflictError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Unexpected error deactivating vendor: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))
