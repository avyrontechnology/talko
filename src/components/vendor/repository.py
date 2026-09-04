from typing import Any, Dict, Union

from bson import ObjectId

from src.components.vendor.models import TalkoVendorModel
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoVendorRepository:
    """
    Repository class for handling database operations related to vendors.
    Uses asynchronous MongoDB sessions via the TalkoDocDatabaseSessionManager.
    """

    def __init__(
        self, session_factory: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger
    ):
        """
        Initialize the TalkoVendorRepository.

        Args:
            session_factory (TalkoDocDatabaseSessionManager): MongoDB session manager.
            logger (TalkoServiceLogger): Logger instance for logging operations.
        """
        self.db_manager = session_factory
        self.logger = logger

    async def insert_vendor(self, vendor_dict: Dict[str, Any]) -> str:
        """
        Insert a new vendor into the database.

        Args:
            vendor_dict (Dict[str, Any]): Dictionary containing vendor data.

        Returns:
            str: ID of the inserted vendor.
        """
        try:
            async with self.db_manager.collection(
                TalkoVendorModel.CollectionName.VENDOR
            ) as collection:
                result = await collection.insert_one(vendor_dict)
                self.logger.info(f"Inserted vendor with ID: {result.inserted_id}")
                return str(result.inserted_id)
        except Exception as e:
            self.logger.error(f"Failed to insert vendor: {str(e)}")
            raise

    async def find_vendor_by_slug(self, slug: str) -> Union[dict, None]:
        """
        Find a vendor by its slug.

        Args:
            slug (str): Unique slug identifier of the vendor.

        Returns:
            dict | None: Vendor document if found, else None.
        """
        try:
            async with self.db_manager.collection(
                TalkoVendorModel.CollectionName.VENDOR
            ) as collection:
                return await collection.find_one({"slug": slug})
        except Exception as e:
            self.logger.error(f"Failed to find vendor by slug {slug}: {str(e)}")
            raise

    async def find_vendor_by_type(
        self, vendor_type: str, vendor_name: str
    ) -> Union[dict, None]:
        """
        Find a vendor by its type.

        Args:
            vendor_type (str): Vendor type.
            vendor_name (str): Name of the vendor.

        Returns:
            dict | None: Vendor document if found, else None.
        """
        try:
            async with self.db_manager.collection(
                TalkoVendorModel.CollectionName.VENDOR
            ) as collection:
                return await collection.find_one(
                    {"vendor_type": vendor_type, "name": vendor_name}
                )
        except Exception as e:
            self.logger.error(f"Failed to find vendor by type {vendor_type}: {str(e)}")
            raise

    async def find_all_vendors(self, include_inactive: bool = False) -> list[dict]:
        """
        Retrieve all vendors from the database.

        Args:
            include_inactive (bool): Whether to include inactive vendors. Defaults to False.

        Returns:
            list[dict]: List of vendor documents.
        """
        try:
            async with self.db_manager.collection(
                TalkoVendorModel.CollectionName.VENDOR
            ) as collection:
                query = {} if include_inactive else {"is_active": True}
                return await collection.find(query).to_list(length=None)
        except Exception as e:
            self.logger.error(f"Failed to retrieve vendors: {str(e)}")
            raise

    async def find_vendor_by_id(self, vendor_id: ObjectId) -> Union[dict, None]:
        """
        Find an active vendor by its ObjectId.

        Args:
            vendor_id (ObjectId): The ID of the vendor.

        Returns:
            dict | None: Vendor document if found and active, else None.
        """
        try:
            async with self.db_manager.collection(
                TalkoVendorModel.CollectionName.VENDOR
            ) as collection:
                return await collection.find_one({"_id": vendor_id, "is_active": True})
        except Exception as e:
            self.logger.error(f"Failed to find vendor by ID {vendor_id}: {str(e)}")
            raise

    async def find_vendor_by_id_all(self, vendor_id: ObjectId) -> Union[dict, None]:
        """
        Find a vendor by its ObjectId regardless of active status.

        Args:
            vendor_id (ObjectId): The ID of the vendor.

        Returns:
            dict | None: Vendor document if found, else None.
        """
        try:
            async with self.db_manager.collection(
                TalkoVendorModel.CollectionName.VENDOR
            ) as collection:
                return await collection.find_one({"_id": vendor_id})
        except Exception as e:
            self.logger.error(f"Failed to find vendor by ID {vendor_id}: {str(e)}")
            raise

    async def update_vendor_status(
        self, vendor_id: ObjectId, is_active: bool, updated_at: int
    ) -> dict:
        """
        Update the active status and updated_at timestamp of a vendor.

        Args:
            vendor_id (ObjectId): The ID of the vendor to update.
            is_active (bool): The new active status.
            updated_at (int): Timestamp representing when the update occurred.

        Returns:
            dict: The updated vendor document.

        Raises:
            ValueError: If the vendor is not found.
        """
        try:
            async with self.db_manager.collection(
                TalkoVendorModel.CollectionName.VENDOR
            ) as collection:
                result = await collection.find_one_and_update(
                    {"_id": vendor_id},
                    {"$set": {"is_active": is_active, "updated_at": updated_at}},
                    return_document=True,
                )
                if not result:
                    self.logger.error(f"Vendor with ID {vendor_id} not found")
                    raise ValueError(f"Vendor with ID {vendor_id} not found")
                self.logger.info(
                    f"Updated vendor status for ID {vendor_id} to is_active={is_active}"
                )
                return result
        except Exception as e:
            self.logger.error(
                f"Failed to update vendor status for ID {vendor_id}: {str(e)}"
            )
            raise
