from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status

from src.components.call_assets.messages import INVALID_REQUESTED_DATA, NOT_FOUND, SOMETHING_WENT_WRONG
from src.components.call_assets.services import AssetService
from src.components.common.responses import BadRequestResponse, ResourceNotFoundResponse
from src.components.digital_assets.schema import DigitalAssetResponse
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import BadRequestError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger


class AssetsController:
    """Controller to handle call-recordings"""
    callassets = APIRouter()

    @callassets.get(
        "",
        response_model=dict,
        status_code=status.HTTP_201_CREATED,
        description="Fetch a digital asset by its ID and type",
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_digital_assets(
        partner_id: int,
        asset_type: str,
        asset_service: AssetService = Depends(
            Provide[Container.assets_service]
        ),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    )->dict:
        """
        Fetch the details of a digital asset by its partner ID and type.

        This endpoint retrieves detailed information about a digital asset using the provided
        partner ID and asset type. It returns a response with the asset's metadata, including:
        - name
        - Partner ID
        - Version
        - Asset type
        - Additional information
        - Created by and updated by details

        Args:
            partner_id (int): The partner ID associated with the digital asset.
            asset_type (str): The type of the digital asset (e.g., image, video).

        Returns:
            DigitalAssetResponse: A response model containing the details of the digital asset.

        Raises:
            HTTPException: If an error occurs during the retrieval of asset details, a 500
                           internal server error will be raised with the exception details.
        """
        try:
            holler_service_logger.info(
                "Fetching digital asset details for partner_id: {}, asset_type: {}".format(
                    partner_id, asset_type
                )
            )
            asset_details: dict = await asset_service.get_digital_asset_details(
                partner_id,
                asset_type,
            )
            holler_service_logger.info(
                "Successfully fetched digital asset details for partner_id: {}, asset_type: {}".format(
                    partner_id, asset_type
                )
            )
            return asset_details
        except ResourceNotFound as e:
            holler_service_logger.error(
                "Resource not found while getting digital assets: {}".format(str(e))
            )
            return ResourceNotFoundResponse(detail=NOT_FOUND)
        except BadRequestError as e:
            holler_service_logger.error(
                "Bad request Error while getting digital assets: {}".format(str(e))
            )
            return BadRequestResponse(detail=INVALID_REQUESTED_DATA)

        except Exception as e:
            holler_service_logger.error(
                "Error fetching digital asset details for partner_id: {}, asset_type: {}. Error: {}".format(
                    partner_id, asset_type, str(e)
                )
            )
            raise HTTPException(status_code=500, detail=SOMETHING_WENT_WRONG)