from typing import Union

from bson import ObjectId

from src.components.vendor.models import VendorModel
from src.components.vendor_config.constants import PULL_ALL, PUSH, SET
from src.components.vendor_config.message import VENDOR_CONFIG_FOR_VENDOR_ID_NOT_FOUND
from src.components.vendor_config.models import VendorConfigModel
from src.core.doc_db import DocDatabaseSessionManager
from src.loggers.holler_service_logger import HollerServiceLogger


class VendorConfigRepository:
    """
    Repository class for handling all database operations related to Vendor Configurations.
    """

    def __init__(
        self, db_manager: DocDatabaseSessionManager, logger: HollerServiceLogger
    ):
        """
        Initialize the repository with database manager and logger.

        :param db_manager: Database session manager for MongoDB operations.
        :param logger: Logger instance for logging events.
        """
        self.__db_manager = db_manager
        self.__logger = logger
        self.__lookup = "$lookup"
        self.__unwind = "$unwind"
        self.__vendor = "$vendor"
        self.__match = "$match"
        self.__project = "$project"
        self.__vendor_is_active = {"vendor.is_active": True}

    async def insert_vendor_config(self, config_dict: dict) -> str:
        """
        Insert a new vendor configuration document into the database.

        :param config_dict: Dictionary representing the vendor config to be inserted.
        :return: The ID of the inserted document as a string.
        """
        try:
            async with self.__db_manager.collection(
                VendorConfigModel.CollectionName.VENDOR_CONFIG
            ) as collection:
                result = await collection.insert_one(config_dict)
                self.__logger.info(
                    "Inserted vendor config with ID: {}".format(result.inserted_id)
                )
                return str(result.inserted_id)
        except Exception as e:
            self.__logger.error("Failed to insert vendor config: {}".format(str(e)))
            raise

    async def check_vendor_config_exists_for_existing_vendor(
        self, vendor_id: ObjectId
    ) -> bool:
        """
        Check if a vendor configuration exists for the given vendor ID.

        :param vendor_id: The ObjectId of the vendor.
        :return: True if config exists, False otherwise.
        """
        try:
            async with self.__db_manager.collection(
                VendorConfigModel.CollectionName.VENDOR_CONFIG
            ) as collection:
                exists = await collection.find_one({"vendor_id": vendor_id}) is not None
                self.__logger.info(
                    "Vendor config exists for vendor_id {}: {}".format(
                        vendor_id, exists
                    )
                )
                return exists
        except Exception as e:
            self.__logger.error(
                "Failed to check vendor config existence for vendor_id {}: {}".format(
                    vendor_id, str(e)
                )
            )
            raise

    async def check_vendor_config_exists_for_existing_vendor_using_pk_id(
        self, id: ObjectId
    ) -> bool:
        """
        Check if a vendor configuration exists for the given config primary key (_id).

        :param id: The ObjectId of the vendor config.
        :return: True if config exists, False otherwise.
        """
        try:
            async with self.__db_manager.collection(
                VendorConfigModel.CollectionName.VENDOR_CONFIG
            ) as collection:
                exists = await collection.find_one({"_id": id}) is not None
                self.__logger.info(
                    "Vendor config exists for vendor_id {}: {}".format(id, exists)
                )
                return exists
        except Exception as e:
            self.__logger.error(
                "Failed to check vendor config existence for vendor_id {}: {}".format(
                    id, str(e)
                )
            )
            raise

    async def find_all_configs(
        self, include_inactive_vendors: bool = False
    ) -> Union[dict, list[dict], None]:
        """
        Retrieve all vendor configurations, optionally excluding inactive vendors.

        :param include_inactive_vendors: If True, include inactive vendors; otherwise, exclude.
        :return: List of vendor config documents with vendor name joined.
        """
        try:
            async with self.__db_manager.collection(
                VendorConfigModel.CollectionName.VENDOR_CONFIG
            ) as configs_collection:
                pipeline = [
                    {
                        self.__lookup: {
                            "from": VendorModel.CollectionName.VENDOR,
                            "localField": "vendor_id",
                            "foreignField": "_id",
                            "as": "vendor",
                        }
                    },
                    {self.__unwind: self.__vendor},
                    (
                        {self.__match: self.__vendor_is_active}
                        if not include_inactive_vendors
                        else {}
                    ),
                    {
                        self.__project: {
                            "_id": 1,
                            "vendor_name": "$vendor.name",
                        }
                    },
                ]
                result = []
                async for config in configs_collection.aggregate(pipeline):
                    result.append(config)

                return result
        except Exception as e:
            self.__logger.error("Failed to retrieve vendor configs: {}".format(str(e)))
            raise

    async def find_config_by_id(self, config_id: ObjectId) -> Union[dict, None]:
        """
        Retrieve a specific vendor configuration by its ID, joined with vendor data.

        :param config_id: The ObjectId of the vendor config.
        :return: A single config dictionary if found; otherwise, None.
        """
        try:
            async with self.__db_manager.collection(
                VendorConfigModel.CollectionName.VENDOR_CONFIG
            ) as configs_collection:
                pipeline = [
                    {self.__match: {"_id": config_id}},
                    {
                        self.__lookup: {
                            "from": VendorModel.CollectionName.VENDOR,
                            "localField": "vendor_id",
                            "foreignField": "_id",
                            "as": "vendor",
                        }
                    },
                    {self.__unwind: self.__vendor},
                    {self.__match: self.__vendor_is_active},
                    {
                        self.__project: {
                            "_id": 1,
                            "vendor_id": 1,
                            "name": 1,
                            "generic_url_handler": 1,
                            "cdr_url_handler": 1,
                            "dialer_url_handler": 1,
                            "transfer_url_handler": 1,
                            "created_at": 1,
                            "updated_at": 1,
                            "vendor_name": "$vendor.name",
                            "vendor_type": "$vendor.vendor_type",
                        }
                    },
                ]
                result = None
                async for config in configs_collection.aggregate(pipeline):
                    result = config
                    break
                return result

        except Exception as e:
            self.__logger.error(
                "Failed to find vendor config for config_id {}: {}".format(
                    config_id, str(e)
                )
            )
            raise

    async def find_configs_by_vendor_id(self, vendor_id: ObjectId) -> list[dict]:
        try:
            async with self.__db_manager.collection(
                VendorConfigModel.CollectionName.VENDOR_CONFIG
            ) as configs_collection:
                pipeline = [
                    {self.__match: {"vendor_id": vendor_id}},
                    {
                        self.__lookup: {
                            "from": VendorModel.CollectionName.VENDOR,
                            "localField": "vendor_id",
                            "foreignField": "_id",
                            "as": "vendor",
                        }
                    },
                    {self.__unwind: self.__vendor},
                    {self.__match: self.__vendor_is_active},
                    {
                        self.__project: {
                            "_id": 1,
                            "vendor_id": 1,
                            "generic_url_handler": 1,
                            "cdr_url_handler": 1,
                            "dialer_url_handler": 1,
                            "transfer_url_handler": 1,
                            "created_at": 1,
                            "updated_at": 1,
                        }
                    },
                ]
                result = []
                async for config in configs_collection.aggregate(pipeline):
                    result.append(config)
                return result
        except Exception as e:
            self.__logger.error(
                "Failed to find vendor configs for vendor_id {}: {}".format(
                    vendor_id, str(e)
                )
            )
            raise

    async def get_vendor_config_by_vendor_type(self, vendor_type: str) -> list[dict]:
        """
        Fetch vendor configuration(s) by vendor_type.
        """
        try:
            async with self.__db_manager.collection(
                VendorConfigModel.CollectionName.VENDOR_CONFIG
            ) as configs_collection:
                pipeline = [
                    # Join with Vendor collection
                    {
                        self.__lookup: {
                            "from": VendorModel.CollectionName.VENDOR,
                            "localField": "vendor_id",  # link via vendor_id
                            "foreignField": "_id",
                            "as": "vendor",
                        }
                    },
                    {self.__unwind: "$vendor"},  # flatten the joined array
                    # Filter by active vendor and vendor_type
                    {
                        self.__match: {
                            "vendor.is_active": True,
                            "vendor.vendor_type": vendor_type,
                        }
                    },
                    # Select required fields
                    {
                        self.__project: {
                            "_id": 1,
                            "vendor_id": 1,
                            "generic_url_handler": 1,
                            "cdr_url_handler": 1,
                            "dialer_url_handler": 1,
                            "transfer_url_handler": 1,
                            "created_at": 1,
                            "updated_at": 1,
                            "vendor_name": "$vendor.name",
                            "vendor_type": "$vendor.vendor_type",
                        }
                    },
                ]

                result: list = []
                async for config in configs_collection.aggregate(pipeline):
                    result.append(config)
                return result

        except Exception as e:
            self.__logger.error(
                f"Failed to find vendor configs for vendor_type {vendor_type}: {str(e)}"
            )
            raise

    async def update_vendor_config(
        self, config_id: ObjectId, update_dict: dict
    ) -> dict:
        """
        Update a vendor configuration by its ID.

        :param config_id: The ObjectId of the vendor config.
        :param update_dict: Dictionary containing fields to update.
        :return: The updated vendor config document.
        :raises ValueError: If the config is not found.
        """
        try:
            async with self.__db_manager.collection(
                VendorConfigModel.CollectionName.VENDOR_CONFIG
            ) as collection:
                result = await collection.find_one_and_update(
                    {"_id": config_id}, {"$set": update_dict}, return_document=True
                )
                if not result:
                    self.__logger.error(
                        VENDOR_CONFIG_FOR_VENDOR_ID_NOT_FOUND.format(config_id)
                    )
                    raise ValueError(
                        VENDOR_CONFIG_FOR_VENDOR_ID_NOT_FOUND.format(config_id)
                    )
                self.__logger.info(
                    "Updated vendor config for vendor_id {}".format(config_id)
                )
                return result
        except Exception as e:
            self.__logger.error(
                "Failed to update vendor config for vendor_id {}: {}".format(
                    config_id, str(e)
                )
            )
            raise

    async def update_did_lists(
        self,
        vendor_id: ObjectId,
        remove_from_available: list[str],
        add_to_available: list[str],
        remove_from_assigned: list[str],
        add_to_assigned: list[str],
        updated_at: int,
    ) -> dict:
        """
        Update the available and assigned DID lists for a given vendor configuration.

        This method performs MongoDB update operations on the `vendor_configs` collection
        to modify `available_did` and `assigned_did` arrays, and sets the `updated_at` timestamp.

        Args:
            vendor_id (ObjectId): The ObjectId of the vendor whose config is being updated.
            remove_from_available (list[str]): DIDs to remove from the available_did list.
            add_to_available (list[str]): DIDs to add to the available_did list.
            remove_from_assigned (list[str]): DIDs to remove from the assigned_did list.
            add_to_assigned (list[str]): DIDs to add to the assigned_did list.
            updated_at (int): The timestamp to set as updated_at in the document.

        Returns:
            dict: The updated vendor configuration document.

        Raises:
            ValueError: If the vendor config document is not found.
            Exception: If any other error occurs during the database operation.
        """
        try:
            async with self.__db_manager.collection("vendor_configs") as collection:
                update_ops = {"updated_at": updated_at}
                if remove_from_available:
                    update_ops[PULL_ALL] = update_ops.get(PULL_ALL, {})
                    update_ops[PULL_ALL]["available_did"] = remove_from_available
                if add_to_available:
                    update_ops[PUSH] = update_ops.get(PUSH, {})
                    update_ops[PUSH]["available_did"] = {"$each": add_to_available}
                if remove_from_assigned:
                    update_ops[PULL_ALL] = update_ops.get(PULL_ALL, {})
                    update_ops[PULL_ALL]["assigned_did"] = remove_from_assigned
                if add_to_assigned:
                    update_ops[PUSH] = update_ops.get(PUSH, {})
                    update_ops[PUSH]["assigned_did"] = {"$each": add_to_assigned}

                result = await collection.find_one_and_update(
                    {"vendor_id": vendor_id}, {SET: update_ops}, return_document=True
                )
                if not result:
                    self.__logger.error(
                        "Vendor config for vendor_id {} not found".format(vendor_id)
                    )
                    raise ValueError("Vendor config for vendor_id not found.")
                self.__logger.info(
                    "Updated DID lists for vendor_id {}".format(vendor_id)
                )
                return result
        except Exception as e:
            self.__logger.error(
                "Failed to update DID lists for vendor_id {}: {}".format(
                    vendor_id, str(e)
                )
            )
            raise

    async def update_vendor_config_by_vendor_id(
        self, vendor_id: ObjectId, update_dict: dict
    ) -> dict:
        """
        Update a vendor configuration document based on the given vendor_id.

        Args:
            vendor_id (ObjectId): The ObjectId of the vendor whose configuration should be updated.
            update_dict (dict): A MongoDB update query containing fields to be updated.

        Returns:
            dict: The updated vendor configuration document.

        Raises:
            ValueError: If no document is found with the given vendor_id.
            Exception: If any error occurs during the database operation.
        """
        try:
            async with self.__db_manager.collection(
                VendorConfigModel.CollectionName.VENDOR_CONFIG
            ) as collection:
                result = await collection.find_one_and_update(
                    {"vendor_id": vendor_id}, update_dict, return_document=True
                )
                if not result:
                    self.__logger.error(
                        "No vendor config found for vendor_id {}".format(vendor_id)
                    )
                    raise ValueError("No vendor config found for vendor_id.")
                self.__logger.info(
                    "Updated vendor config for vendor_id: {}".format(vendor_id)
                )
                return result
        except Exception as e:
            self.__logger.error(
                "Failed to update vendor config for vendor_id {}: {}".format(
                    vendor_id, str(e)
                )
            )
            raise
