from typing import Dict, Any, Optional
from bson import ObjectId
from src.components.call_record.models import TalkoCallRecordModel
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoCallRecordRepository:

    def __init__(
        self, session_factory: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger
    ):
        self.__session_factory = session_factory
        self.__logger = logger

    async def add_call_record(self, data: Dict[str, Any]) -> str:
        async with self.__session_factory.collection(
            TalkoCallRecordModel.CollectionName.CALL_RECORD
        ) as collection:
            result = await collection.insert_one(data)
            return str(result.inserted_id)

    async def is_call_record_exist(self, record_id: str, partner_id: int) -> bool:
        async with self.__session_factory.collection(
            TalkoCallRecordModel.CollectionName.CALL_RECORD
        ) as collection:
            self.__logger.info("Checking call record existance")
            result = await collection.find_one(
                {"_id": ObjectId(record_id), "partner_id": partner_id}
            )
            return result != None

    async def get_call_record(
        self, record_id: str, partner_id: int
    ) -> Optional[TalkoCallRecordModel]:
        async with self.__session_factory.collection(
            TalkoCallRecordModel.CollectionName.CALL_RECORD
        ) as collection:
            result = await collection.find_one(
                {"_id": ObjectId(record_id), "partner_id": partner_id}
            )
            return TalkoCallRecordModel(**result) if result else None

    async def get_all_call_records(self, partner_id: int) -> list[TalkoCallRecordModel]:
        async with self.__session_factory.collection(
            TalkoCallRecordModel.CollectionName.CALL_RECORD
        ) as collection:
            cursor = collection.find({"partner_id": partner_id})
            results = await cursor.to_list(length=None)
            chats = [TalkoCallRecordModel(**chat) for chat in results]
            return chats

    async def update_call_record(
        self, record_id: str, partner_id: int, data: Dict[str, Any]
    ):
        async with self.__session_factory.collection(
            TalkoCallRecordModel.CollectionName.CALL_RECORD
        ) as collection:
            await collection.update_one(
                {"_id": ObjectId(record_id), "partner_id": partner_id}, {"$set": data}
            )

    async def delete_call_record(self, record_id: str, partner_id: int):
        async with self.__session_factory.collection(
            TalkoCallRecordModel.CollectionName.CALL_RECORD
        ) as collection:
            await collection.delete_one(
                {"_id": ObjectId(record_id), "partner_id": partner_id}
            )
