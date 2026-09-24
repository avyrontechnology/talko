from typing import Any

from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError
from pymongo.results import InsertOneResult

from src.components.call_assets.messages import DUPLICATE_ASSET_INSERTION
from src.components.call_assets.models import TalkoAssetsModel
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.exceptions import TalkoDuplicateResourceError
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoAssetRepository:
    def __init__(self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger):
        """
        Initialize the TalkoAssetRepository.

        Args:
            db_manager: MongoDB session manager.
            logger: Logger for capturing logs.
        """
        self.__db_manager: TalkoDocDatabaseSessionManager = db_manager
        self.__logger: TalkoServiceLogger = logger

    async def get_digital_asset_by_partner_id(self, partner_id: int, asset_type: str) -> dict | None:
        """
        Fetch a digital asset by its partner ID and type.

        This method retrieves a digital asset from the database based on the provided partner ID and asset type.
        It logs the success or failure of the operation and returns the digital asset if found.

        Args:
            partner_id (int): The ID of the partner associated with the digital asset.
            asset_type (str): The type of the digital asset (e.g., image, video).

        Returns:
            TalkoDigitalAssets: The digital asset object, or None if not found.

        Raises:
            Exception: If an unexpected error occurs during the database operation.
        """
        try:
            self.__logger.info(f"Fetching latest digital asset for partner_id={partner_id}, asset_type={asset_type}")
            async with self.__db_manager.collection(TalkoAssetsModel.CollectionName.ASSETS) as collection:
                doc = await collection.find_one(
                    {"partner_id": partner_id, "asset_type": asset_type}, sort=[("created_at", DESCENDING)]
                )
            if doc:
                self.__logger.info(f"Found digital asset: {doc}")
                asset: TalkoAssetsModel = TalkoAssetsModel(**doc)
                asset_dict: dict = asset.model_dump()
                asset_dict["id"] = str(doc["_id"])
                self.__logger.info(f"Digital Assets Dictionary: {asset_dict}")
                return asset_dict
            else:
                self.__logger.info("No digital asset found")
                return None
        except Exception as e:
            self.__logger.error(f"Error fetching digital asset: {str(e)}")
            raise e

    async def get_digital_asset_by_id(self, asset_id: str) -> TalkoAssetsModel | None:
        """
        Fetch a digital asset by its MongoDB _id.
        """
        try:
            self.__logger.info(f"Fetching digital asset with _id={asset_id}")
            async with self.__db_manager.collection(TalkoAssetsModel.CollectionName.ASSETS) as collection:
                doc: dict[str, Any] | None = await collection.find_one({"_id": asset_id})
            if doc:
                self.__logger.info(f"Found digital asset: {doc}")
                return TalkoAssetsModel(**doc)
            else:
                self.__logger.info("No digital asset found")
                return None
        except Exception as e:
            self.__logger.error(f"Error fetching digital asset by ID: {str(e)}")
            raise e

    async def create_digital_asset(
        self,
        partner_id: int,
        asset_type: str,
        file_name: str,
        user_id: int,
        lead_number: int,
        call_time: int | None = 0,
        agent_id: int | None = None,
        call_id: str | None = None,
    ) -> TalkoAssetsModel:
        """
        Create a new digital asset in MongoDB with versioning logic (1→2→3→1).
        """
        try:
            # Fetch latest version
            self.__logger.info(
                f"Received request for creating asset for partner_id {partner_id}, asset_type {asset_type}, filename {file_name}, user_id {user_id}, lead_number {lead_number}, call_time {call_time} and agent_id {agent_id}"
            )
            async with self.__db_manager.collection(TalkoAssetsModel.CollectionName.ASSETS) as collection:
                latest_doc: dict[str, Any] | None = await collection.find_one(
                    {"partner_id": partner_id, "asset_type": asset_type}, sort=[("created_at", DESCENDING)]
                )
            new_version: int = 1
            if latest_doc:
                new_version = latest_doc["version"] + 1

            self.__logger.info(f"Creating new digital asset with version={new_version}")

            new_asset: TalkoAssetsModel = TalkoAssetsModel(
                name=file_name,
                partner_id=partner_id,
                asset_type=asset_type,
                version=new_version,
                created_by=user_id,
                updated_by=user_id,
                additional_info={
                    "lead_number": lead_number,
                    "call_time": call_time,
                    "agent_id": agent_id,
                    "call_id": call_id,
                },
            )
            try:
                async with self.__db_manager.collection(TalkoAssetsModel.CollectionName.ASSETS) as collection:
                    result: InsertOneResult = await collection.insert_one(new_asset.model_dump())
                    self.__logger.info(
                        f"Digital asset record created successfully: {new_asset} with id {str(result.inserted_id)}"
                    )
                    return new_asset
            except Exception as e:
                self.__logger.error(f"Failed to insert TalkoCDR: {str(e)}")
                raise
        except DuplicateKeyError as e:
            self.__logger.error(f"Duplicate key error: {str(e)}")
            raise TalkoDuplicateResourceError(DUPLICATE_ASSET_INSERTION)
        except Exception as e:
            self.__logger.error(f"Error creating digital asset: {str(e)}")
            raise e
