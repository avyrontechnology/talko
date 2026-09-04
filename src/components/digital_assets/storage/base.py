from abc import ABC, abstractmethod


class TalkoBaseStorageManager(ABC):
    """
    Abstract base class for managing file storage operations.
    """

    @abstractmethod
    def get_presigned_url(self, file_name: str, view_only: bool = False) -> str:
        """
        Generates a presigned URL for accessing a file in storage.
        """
        pass

    @abstractmethod
    async def upload_digital_asset(self, file: object, file_path: str) -> str:
        """
        Uploads a digital asset to the storage.
        """
        pass

    @abstractmethod
    async def delete_digital_asset(self, file_path: str):
        """
        Deletes a digital asset from the storage.
        """
        pass
