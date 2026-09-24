import logging

from src.components.digital_assets.constants import TalkoDigitalAssetEnum

logger = logging.getLogger(__name__)


class TalkoDigitalAssetUtils:
    """
    Utility class for handling operations related to Digital Assets.
    """

    @staticmethod
    def is_valid_asset_type(asset_type: str) -> bool:
        """
        Validates if the given asset type is a valid member of TalkoDigitalAssetEnum.

        Args:
            asset_type (str): The asset type to validate.

        Returns:
            bool: True if the asset type is valid, False otherwise.
        """

        is_valid = asset_type in TalkoDigitalAssetEnum.__members__
        logger.info(f"Validating asset type: {asset_type}. Result: {is_valid}")
        return is_valid
