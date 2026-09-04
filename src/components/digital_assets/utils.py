from src.components.digital_assets.constants import TalkoDigitalAssetEnum
from src.components.digital_assets.logger_adapter import TalkoLoggerAdapter

logger = TalkoLoggerAdapter().get_logger()


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
        logger.info(
            "Validating asset type: {}. Result: {}".format(asset_type, is_valid)
        )
        return is_valid
