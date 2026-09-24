from typing import Any

from bson import ObjectId

from src.components.client.models import TalkoClientModel
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoClientRepository:
    def __init__(self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger) -> None:
        self.__db_manager = db_manager
        self.__logger = logger

    async def insert_client(self, client_dict: dict[str, Any]) -> str:
        try:
            async with self.__db_manager.collection(TalkoClientModel.CollectionName.CLIENT) as collection:
                result = await collection.insert_one(client_dict)
                return str(result.inserted_id)
        except Exception as e:
            self.__logger.error(f"Failed to insert client: {str(e)}")
            raise

    async def find_by_id(self, client_id: ObjectId) -> dict[str, Any] | None:
        try:
            async with self.__db_manager.collection(TalkoClientModel.CollectionName.CLIENT) as collection:
                return await collection.find_one({"_id": client_id})
        except Exception as e:
            self.__logger.error(f"Failed to find client {client_id}: {str(e)}")
            raise

    async def find_all(self, active_only: bool = False) -> list[dict[str, Any]]:
        try:
            query: dict[str, Any] = {}
            if active_only:
                query["is_active"] = True
            async with self.__db_manager.collection(TalkoClientModel.CollectionName.CLIENT) as collection:
                return await collection.find(query).sort("created_at", -1).to_list(length=None)
        except Exception as e:
            self.__logger.error(f"Failed to list all clients: {str(e)}")
            raise

    async def find_by_partner(self, partner_id: int, active_only: bool = False) -> list[dict[str, Any]]:
        try:
            query: dict[str, Any] = {"partner_id": partner_id}
            if active_only:
                query["is_active"] = True
            async with self.__db_manager.collection(TalkoClientModel.CollectionName.CLIENT) as collection:
                return await collection.find(query).sort("created_at", -1).to_list(length=None)
        except Exception as e:
            self.__logger.error(f"Failed to list clients for partner {partner_id}: {str(e)}")
            raise

    async def find_by_name(self, partner_id: int, name: str) -> dict[str, Any] | None:
        try:
            async with self.__db_manager.collection(TalkoClientModel.CollectionName.CLIENT) as collection:
                return await collection.find_one({"partner_id": partner_id, "name": name})
        except Exception as e:
            self.__logger.error(f"Failed to find client by name: {str(e)}")
            raise

    async def update_client(self, client_id: ObjectId, update_dict: dict[str, Any]) -> dict[str, Any] | None:
        try:
            async with self.__db_manager.connect() as db:
                collection = db[TalkoClientModel.CollectionName.CLIENT]
                return await collection.find_one_and_update(
                    {"_id": client_id}, {"$set": update_dict}, return_document=True
                )
        except Exception as e:
            self.__logger.error(f"Failed to update client {client_id}: {str(e)}")
            raise
