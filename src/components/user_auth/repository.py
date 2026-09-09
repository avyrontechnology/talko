from typing import Union

from src.components.user_auth.models import TalkoUserModel
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoUserRepository:
    """CRUD over the talko_users collection."""

    def __init__(
        self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger
    ):
        self.db_manager = db_manager
        self.logger = logger

    async def count_users(self) -> int:
        try:
            async with self.db_manager.collection(
                TalkoUserModel.CollectionName.TALKO_USERS
            ) as collection:
                return await collection.count_documents({})
        except Exception as e:
            self.logger.error("Failed to count talko users: {}".format(str(e)))
            raise

    async def insert_user(self, doc: dict) -> str:
        try:
            async with self.db_manager.collection(
                TalkoUserModel.CollectionName.TALKO_USERS
            ) as collection:
                result = await collection.insert_one(doc)
                return str(result.inserted_id)
        except Exception as e:
            self.logger.error("Failed to insert talko user: {}".format(str(e)))
            raise

    async def find_by_email(self, email: str) -> Union[dict, None]:
        try:
            async with self.db_manager.collection(
                TalkoUserModel.CollectionName.TALKO_USERS
            ) as collection:
                return await collection.find_one({"email": email.strip().lower()})
        except Exception as e:
            self.logger.error("Failed to find talko user by email: {}".format(str(e)))
            raise

    async def find_by_id(self, user_id: str) -> Union[dict, None]:
        try:
            from bson import ObjectId

            async with self.db_manager.collection(
                TalkoUserModel.CollectionName.TALKO_USERS
            ) as collection:
                try:
                    key = ObjectId(user_id)
                except Exception:
                    key = user_id
                return await collection.find_one({"_id": key})
        except Exception as e:
            self.logger.error("Failed to find talko user by id: {}".format(str(e)))
            raise

    async def list_users(self, limit: int = 100) -> list[dict]:
        try:
            async with self.db_manager.collection(
                TalkoUserModel.CollectionName.TALKO_USERS
            ) as collection:
                cursor = collection.find({}).sort("created_at", -1).limit(limit)
                return await cursor.to_list(length=limit)
        except Exception as e:
            self.logger.error("Failed to list talko users: {}".format(str(e)))
            raise

    async def update_user(self, user_id: str, patch: dict) -> bool:
        try:
            from bson import ObjectId

            async with self.db_manager.collection(
                TalkoUserModel.CollectionName.TALKO_USERS
            ) as collection:
                try:
                    key = ObjectId(user_id)
                except Exception:
                    key = user_id
                result = await collection.update_one({"_id": key}, {"$set": patch})
                return result.matched_count > 0
        except Exception as e:
            self.logger.error("Failed to update talko user: {}".format(str(e)))
            raise
