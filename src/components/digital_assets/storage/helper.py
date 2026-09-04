from fastapi import UploadFile

from src.components.digital_assets.logger_adapter import TalkoLoggerAdapter
from src.components.digital_assets.storage.factory import TalkoFactoryStorageManager
from src.core.environment import TalkoENV

logger = TalkoLoggerAdapter().get_logger()


class TalkoStorageHelper:
    """
    Helper class to interact with various storage providers.
    """

    @staticmethod
    def _get_storage_manager():
        """Returns the appropriate storage manager based on the provider."""
        provider = TalkoENV.STORAGE_SERVICE_PROVIDER
        if not provider:
            raise ValueError("STORAGE_SERVICE_PROVIDER is not set.")
        logger.info("Using storage provider: {}".format(provider))
        return TalkoFactoryStorageManager.get_storage_class(provider)

    @staticmethod
    def get_presigned_url(file_name: str, view_only: bool = False) -> str:
        """Fetches a presigned URL from the storage manager."""
        storage_class = TalkoStorageHelper._get_storage_manager()
        return storage_class.get_presigned_url(file_name, view_only)

    @staticmethod
    async def upload_file(file_obj: UploadFile, file_path: str):
        """Uploads a file to the storage provider."""
        storage_class = TalkoStorageHelper._get_storage_manager()
        return await storage_class.upload_digital_asset(file_obj, file_path)

    @staticmethod
    async def delete_file(file_path: str):
        """Deletes a file from the storage provider."""
        storage_class = TalkoStorageHelper._get_storage_manager()
        return await storage_class.delete_digital_asset(file_path)
