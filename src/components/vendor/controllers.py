from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, status

from src.components.common.constants import CurrentUserMap
from src.components.common.responses import (
    BadRequestResponse,
    InternalServerErrorResponse,
    ResourceCreatedResponse,
    ResourceNotFoundResponse,
    SuccessResponse,
)
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.vendor.dto import Contract
from src.components.vendor.message import NOT_FOUND
from src.components.vendor.services import VendorService
from src.core.container import Container
from src.exceptions import ConflictError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.common_messages import VENDOR_NOT_FOUND


class VendorController:
    vendor_router = APIRouter()

    @vendor_router.post(
        "", response_model=Contract.VendorResponse, status_code=status.HTTP_201_CREATED
    )
    @permission_check(PermissionDependency)
    @inject
    async def create_vendor(
        request: Request,
        vendor_data: Contract.VendorCreate,
        vendor_service: VendorService = Depends(Provide[Container.vendor_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.VendorResponse:
        try:
            holler_service_logger.info("Received vendor data: {}.".format(vendor_data))
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, create vendor api initiated".format(
                    user_id, partner_id
                )
            )
            created_vendor: Contract.VendorResponse = (
                await vendor_service.create_vendor(vendor_data)
            )
            holler_service_logger.info(
                "Vendor created successfully: {}.".format(created_vendor)
            )
            return ResourceCreatedResponse(data=created_vendor)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error creating vendor: {}.".format(str(e))
            )
            return InternalServerErrorResponse(detail=str(e))

    @vendor_router.get("", response_model=list[Contract.GetAllVendorData])
    @permission_check(PermissionDependency)
    @inject
    async def get_all_vendors(
        request: Request,
        vendor_service: VendorService = Depends(Provide[Container.vendor_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> list[Contract.GetAllVendorData]:
        try:
            holler_service_logger.info("Get all vendor data.")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, get all vendors data api initiated.".format(
                    user_id, partner_id
                )
            )
            vendors: list[Contract.GetAllVendorData] = (
                await vendor_service.get_vendors()
            )
            holler_service_logger.info("Retrieved {} vendors.".format(len(vendors)))
            return SuccessResponse(data=vendors)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving vendors: {}.".format(str(e))
            )
            return InternalServerErrorResponse(detail=str(e))

    @vendor_router.get(
        "/{vendor_id}", response_model=Contract.GetVendorDataOnTheBasisOfId
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_vendor_by_id(
        request: Request,
        vendor_id: str,
        vendor_service: VendorService = Depends(Provide[Container.vendor_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.GetVendorDataOnTheBasisOfId:
        try:
            holler_service_logger.info(
                "Retrieving vendor with ID: {}.".format(vendor_id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, get vendor by id api initiated.".format(
                    user_id, partner_id
                )
            )
            vendor: Contract.GetVendorDataOnTheBasisOfId = (
                await vendor_service.get_vendor_by_id(vendor_id)
            )
            holler_service_logger.info(
                "Vendor retrieved successfully: {}.".format(vendor)
            )
            return SuccessResponse(data=vendor)
        except ValueError as e:
            holler_service_logger.error("Error retrieving vendor: {}".format(str(e)))
            return BadRequestResponse(detail=str(e))
        except ResourceNotFound as e:
            holler_service_logger.error(VENDOR_NOT_FOUND.format(str(e)))
            return ResourceNotFoundResponse(detail=NOT_FOUND)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving vendor: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=str(e))

    @vendor_router.patch(
        "/{vendor_id}/activate", response_model=Contract.VendorResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def activate_vendor(
        request: Request,
        vendor_id: str,
        vendor_service: VendorService = Depends(Provide[Container.vendor_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.VendorResponse:
        try:
            holler_service_logger.info(
                "Activating vendor with ID: {}".format(vendor_id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, activate vendor api initiated.".format(
                    user_id, partner_id
                )
            )
            updated_vendor: Contract.VendorResponse = (
                await vendor_service.activate_vendor(vendor_id)
            )
            holler_service_logger.info(
                "Vendor activated successfully: {}".format(updated_vendor)
            )
            return SuccessResponse(data=updated_vendor)
        except ValueError as e:
            holler_service_logger.error("Error activating vendor: {}.".format(str(e)))
            return BadRequestResponse(detail=str(e))
        except ResourceNotFound as e:
            holler_service_logger.error(VENDOR_NOT_FOUND.format(str(e)))
            return ResourceNotFoundResponse(detail=NOT_FOUND)
        except ConflictError as e:
            holler_service_logger.error(
                "Vendor with ID {} is already active.".format(vendor_id)
            )
            return BadRequestResponse(detail=str(e))
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error activating vendor: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=str(e))

    @vendor_router.patch(
        "/{vendor_id}/deactivate", response_model=Contract.VendorResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def deactivate_vendor(
        request: Request,
        vendor_id: str,
        vendor_service: VendorService = Depends(Provide[Container.vendor_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.VendorResponse:
        try:
            holler_service_logger.info(
                "Deactivating vendor with ID: {}".format(vendor_id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, deactivate vendor api initiated.".format(
                    user_id, partner_id
                )
            )
            updated_vendor: Contract.VendorResponse = (
                await vendor_service.deactivate_vendor(vendor_id)
            )
            holler_service_logger.info(
                "Vendor deactivated successfully: {}".format(updated_vendor)
            )
            return SuccessResponse(data=updated_vendor)
        except ValueError as e:
            holler_service_logger.error("Error deactivating vendor: {}".format(str(e)))
            return BadRequestResponse(detail=str(e))
        except ResourceNotFound as e:
            return ResourceNotFoundResponse(detail=NOT_FOUND)
        except ConflictError as e:
            return BadRequestResponse(detail=str(e))
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error deactivating vendor: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=str(e))
