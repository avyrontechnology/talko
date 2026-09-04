from typing import Union

from src.components.partner_config.models import TalkoPartnerConfigModel
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoPartnerConfigRepository:
    """
    Repository class for managing CRUD operations on Partner Configuration documents.
    """

    def __init__(
        self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger
    ):
        """
        Initialize the repository with a database session manager and logger.

        Args:
            db_manager (TalkoDocDatabaseSessionManager): The MongoDB session manager.
            logger (TalkoServiceLogger): Logger instance for logging operations.
        """
        self.db_manager = db_manager
        self.logger = logger

    async def insert_partner_config(self, config_dict: dict) -> str:
        """
        Insert a new partner configuration document into the database.

        Args:
            config_dict (dict): The partner configuration data to insert.

        Returns:
            str: The string representation of the inserted document's ObjectId.

        Raises:
            Exception: If insertion fails.
        """
        try:
            async with self.db_manager.collection(
                TalkoPartnerConfigModel.CollectionName.PARTNER_CONFIG
            ) as collection:
                result = await collection.insert_one(config_dict)
                self.logger.info(
                    "Inserted partner config with ID: {}.".format(result.inserted_id)
                )
                return str(result.inserted_id)
        except Exception as e:
            self.logger.error("Failed to insert partner config: {}".format(str(e)))
            raise

    async def find_all_partner_configs(self) -> list[dict]:
        """
        Retrieve all partner configuration documents.

        Returns:
            list[dict]: A list of all partner configuration documents.

        Raises:
            Exception: If retrieval fails.
        """
        try:
            async with self.db_manager.collection(
                TalkoPartnerConfigModel.CollectionName.PARTNER_CONFIG
            ) as collection:
                return await collection.find().to_list(length=None)
        except Exception as e:
            self.logger.error("Failed to retrieve partner configs: {}".format(str(e)))
            raise

    async def find_partner_config_by_id(self, id: str) -> Union[dict, None]:
        """
        Retrieve a partner configuration document by its ID.

        Args:
            id (str): The string representation of the document's ObjectId.

        Returns:
            dict | None: The partner configuration document, or None if not found.

        Raises:
            Exception: If retrieval fails.
        """
        try:
            async with self.db_manager.collection(
                TalkoPartnerConfigModel.CollectionName.PARTNER_CONFIG
            ) as collection:
                return await collection.find_one({"_id": id})
        except Exception as e:
            self.logger.error(
                "Failed to find partner config by id {}: {}".format(id, str(e))
            )
            raise

    async def find_partner_config_by_partner_id(self, id: int) -> Union[dict, None]:
        try:
            async with self.db_manager.collection(
                TalkoPartnerConfigModel.CollectionName.PARTNER_CONFIG
            ) as collection:
                return await collection.find_one({"partner_id": id})
        except Exception as e:
            self.logger.error(
                "Failed to find partner config by partner_id {}: {}".format(id, str(e))
            )
            raise

    async def update_partner_config(self, id: str, update_dict: dict) -> dict:
        """
        Update a partner configuration document by its ID.

        Args:
            id (str): The string representation of the document's ObjectId.
            update_dict (dict): The fields to update.

        Returns:
            dict: The updated partner configuration document.

        Raises:
            ValueError: If the document is not found.
            Exception: If update fails.
        """
        try:
            async with self.db_manager.collection(
                TalkoPartnerConfigModel.CollectionName.PARTNER_CONFIG
            ) as collection:
                result = await collection.find_one_and_update(
                    {"_id": id}, {"$set": update_dict}, return_document=True
                )
                if not result:
                    self.logger.error(
                        "In update partner config method partner config for id {} not found".format(
                            id
                        )
                    )
                    raise ValueError("Partner config for id {} not found".format(id))
                self.logger.info("Updated partner config for partner_id {}".format(id))
                return result
        except Exception as e:
            self.logger.error(
                "Failed to update partner config for partner_id {}: {}".format(
                    id, str(e)
                )
            )
            raise

    async def assign_did_to_partner(self, id: str, did: str, updated_at: int) -> dict:
        """
        Assign a DID to a partner configuration by its ID.

        Args:
            id (str): The string representation of the document's ObjectId.
            did (str): The DID to assign.
            updated_at (int): The timestamp of the update.

        Returns:
            dict: The updated partner configuration document.

        Raises:
            ValueError: If the document is not found.
            Exception: If assignment fails.
        """
        try:
            async with self.db_manager.collection(
                TalkoPartnerConfigModel.CollectionName.PARTNER_CONFIG
            ) as collection:
                result = await collection.find_one_and_update(
                    {"_id": id},
                    {"$set": {"did": did, "updated_at": updated_at}},
                    return_document=True,
                )
                if not result:
                    self.logger.error(
                        "In assign did to partner method partner config for partner_id {} not found.".format(
                            id
                        )
                    )
                    raise ValueError(
                        "Partner config for partner_id {} not found".format(id)
                    )
                self.logger.info("Assigned DID {} to partner_id {}".format(did, id))
                return result
        except Exception as e:
            self.logger.error(
                "Failed to assign DID to partner_id {}: {}".format(id, str(e))
            )
            raise

    async def remove_did_from_partner(self, id: str, updated_at: int) -> dict:
        """
        Remove the DID from a partner configuration by its ID.

        Args:
            id (str): The string representation of the document's ObjectId.
            updated_at (int): The timestamp of the update.

        Returns:
            dict: The updated partner configuration document.

        Raises:
            ValueError: If the document is not found.
            Exception: If removal fails.
        """
        try:
            async with self.db_manager.collection(
                TalkoPartnerConfigModel.CollectionName.PARTNER_CONFIG
            ) as collection:
                result = await collection.find_one_and_update(
                    {"_id": id},
                    {"$set": {"did": None, "updated_at": updated_at}},
                    return_document=True,
                )
                if not result:
                    self.logger.error(
                        "Remove did from partner method partner config for partner_id {} not found".format(
                            id
                        )
                    )
                    raise ValueError(
                        "Partner config for partner_id {} not found".format(id)
                    )
                self.logger.info("Removed DID from partner_id {}".format(id))
                return result
        except Exception as e:
            self.logger.error(
                "Failed to remove DID from partner_id {}: {}".format(id, str(e))
            )
            raise
