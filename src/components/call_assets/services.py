import uuid
from typing import Dict, List, Optional

from fastapi import HTTPException

from src.components.call_assets.messages import INVALID_ASSET_TYPE
from src.components.call_assets.models import AssetsModel
from src.components.call_assets.repository import AssetRepository
from src.components.digital_assets.constants import DigitalAssetEnum
from src.components.digital_assets.schema import DigitalAssetResponse
from src.components.digital_assets.storage.helper import StorageHelper
from src.components.digital_assets.utils import DigitalAssetUtils
from src.core.environment import ENV
from src.exceptions import InvalidAssetTypeError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger


class AssetService:
    def __init__(self, repository: AssetRepository, logger: HollerServiceLogger):
        """
        Initialize the DigitalAssetService.

        Args:
            digital_asset_repository (DigitalAssetRepository): The repository for digital asset operations.
            logger: The logger instance for logging service operations.
        """
        self.__repository: AssetRepository = repository
        self.__logger: HollerServiceLogger = logger

    async def get_digital_asset_details(self, partner_id: int, asset_type: str) -> dict:
        """
        Fetch the details of a digital asset by its ID and Type.

        Args:
            asset_unique_id (int): The ID of the digital asset to retrieve.
            asset_type (str): The Type of the digital asset to retrieve.

        Returns:
            DigitalAssetResponse: The response schema containing digital asset details.

        Raises:
            ValueError: If the digital asset is not found.
            Exception: For other unexpected errors.
        """
        try:
            self.__logger.info(
                "Trying to fetch the digital asset details for partner_id: {}, asset_type: {}".format(
                    partner_id, asset_type
                )
            )
            if not DigitalAssetUtils.is_valid_asset_type(asset_type):
                raise InvalidAssetTypeError(INVALID_ASSET_TYPE)
            asset: Optional[Dict] = (
                await self.__repository.get_digital_asset_by_partner_id(
                    partner_id, asset_type
                )
            )

            if not asset:
                self.__logger.error(
                    "Digital asset not found for partner_id {}".format(partner_id)
                )
                raise ResourceNotFound(
                    "Digital asset with ID {} not found".format(partner_id)
                )

            asset_url: str = StorageHelper.get_presigned_url(asset["name"])
            result: dict = {
                "id": asset["id"],
                "name": asset["name"],
                "partner_id": asset["partner_id"],
                "version": asset["version"],
                "url": asset_url,
                "asset_type": DigitalAssetEnum[asset["asset_type"]],
                "additional_info": asset.get("additional_info"),
                "created_by": asset.get("created_by"),
                "updated_by": asset.get("updated_by"),
            }
            return result

        except Exception as e:
            self.__logger.error(
                "An unexpected error occurred while fetching digital asset details for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise e
