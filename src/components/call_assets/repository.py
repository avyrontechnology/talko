from typing import Any, Dict, List, Optional

from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError
from pymongo.results import InsertOneResult

from src.components.call_assets.messages import DUPLICATE_ASSET_INSERTION
from src.components.call_assets.models import TalkoAssetsModel
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.exceptions import TalkoDuplicateResourceError
from src.loggers.talko_service_logger import TalkoServiceLogger

class TalkoAssetRepository:
    def __init__(
        self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger
    ):
        """
        Initialize the TalkoAssetRepository.

        Args:
            db_manager: MongoDB session manager.
            logger: Logger for capturing logs.
        """
        self.__db_manager: TalkoDocDatabaseSessionManager = db_manager
        self.__logger: TalkoServiceLogger = logger

    async def get_digital_asset_by_partner_id(
        self, partner_id: int, asset_type: str
    ) -> Optional[Dict]:
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
            self.__logger.info("Fetching latest digital asset for partner_id={}, asset_type={}".format(partner_id, asset_type))
            async with self.__db_manager.collection(
                TalkoAssetsModel.CollectionName.ASSETS
            ) as collection:
                doc = await collection.find_one(
                {"partner_id": partner_id, "asset_type": asset_type},
                sort=[("created_at", DESCENDING)]
            )
            if doc:
                self.__logger.info("Found digital asset: {}".format(doc))
                asset: TalkoAssetsModel = TalkoAssetsModel(**doc)
                asset_dict: dict = asset.model_dump()
                asset_dict["id"] = str(doc["_id"])
                self.__logger.info("Digital Assets Dictionary: {}".format(asset_dict))
                return asset_dict
            else:
                self.__logger.info("No digital asset found")
                return None
        except Exception as e:
            self.__logger.error("Error fetching digital asset: {}".format(str(e)))
            raise e

    async def get_digital_asset_by_id(self, asset_id: str) -> Optional[TalkoAssetsModel]:
        """
        Fetch a digital asset by its MongoDB _id.
        """
        try:
            self.__logger.info("Fetching digital asset with _id={}".format(asset_id))
            async with self.__db_manager.collection(
                TalkoAssetsModel.CollectionName.ASSETS
            ) as collection:
                doc: Optional[Dict[str, Any]] = await collection.find_one({"_id": asset_id})
            if doc:
                self.__logger.info("Found digital asset: {}".format(doc))
                return TalkoAssetsModel(**doc)
            else:
                self.__logger.info("No digital asset found")
                return None
        except Exception as e:
            self.__logger.error("Error fetching digital asset by ID: {}".format(str(e)))
            raise e

    async def create_digital_asset(
        self, partner_id: int, asset_type: str, file_name: str, user_id: int,lead_number: int, call_time:Optional[int] = 0, agent_id: Optional[int] = None, call_id: Optional[str] = None
    ) -> TalkoAssetsModel:
        """
        Create a new digital asset in MongoDB with versioning logic (1→2→3→1).
        """
        try:
            # Fetch latest version
            self.__logger.info("Received request for creating asset for partner_id {}, asset_type {}, filename {}, user_id {}, lead_number {}, call_time {} and agent_id {}".format(partner_id, asset_type, file_name, user_id, lead_number, call_time, agent_id))
            async with self.__db_manager.collection(
                TalkoAssetsModel.CollectionName.ASSETS
            ) as collection:
                latest_doc: Optional[Dict[str, Any]] = await collection.find_one(
                {"partner_id": partner_id, "asset_type": asset_type},
                sort=[("created_at", DESCENDING)]
            )
            new_version: int = 1
            if latest_doc:
                new_version = latest_doc["version"] + 1

            self.__logger.info("Creating new digital asset with version={}".format(new_version))

            new_asset: TalkoAssetsModel = TalkoAssetsModel(
                name=file_name,
                partner_id=partner_id,
                asset_type=asset_type,
                version=new_version,
                created_by=user_id,
                updated_by=user_id,
                additional_info = {
                    "lead_number":lead_number,
                    "call_time":call_time, 
                    "agent_id":agent_id,
                    "call_id":call_id,
                    }
            )
            try:
                async with self.__db_manager.collection(TalkoAssetsModel.CollectionName.ASSETS) as collection:
                    result: InsertOneResult = await collection.insert_one(new_asset.model_dump())
                    self.__logger.info("Digital asset record created successfully: {} with id {}".format(new_asset, str(result.inserted_id)))
                    return new_asset
            except Exception as e:
                self.__logger.error("Failed to insert TalkoCDR: {}".format(str(e)))
                raise
        except DuplicateKeyError as e:
            self.__logger.error("Duplicate key error: {}".format(str(e)))
            raise TalkoDuplicateResourceError(DUPLICATE_ASSET_INSERTION)
        except Exception as e:
            self.__logger.error("Error creating digital asset: {}".format(str(e)))
            raise e
