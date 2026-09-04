from typing import Any, Dict, List, Optional

from bson import ObjectId

from src.components.custom_field.constants import SET
from src.components.custom_field.models import CustomFieldDefinition
from src.core.doc_db import DocDatabaseSessionManager
from src.loggers.holler_service_logger import HollerServiceLogger


class CustomFieldRepository:
    """
    Repository class for handling all database operations related to
    custom field definitions.
    """

    def __init__(
        self, db_manager: DocDatabaseSessionManager, logger: HollerServiceLogger
    ):
        self.__db_manager = db_manager
        self.__logger = logger

    async def insert_custom_field(self, field_dict: dict) -> str:
        try:
            async with self.__db_manager.collection(
                CustomFieldDefinition.CollectionName.CUSTOM_FIELD_DEFINITIONS
            ) as collection:
                result: Any = await collection.insert_one(field_dict)
                self.__logger.info(
                    "Inserted custom field definition with ID: {}".format(
                        result.inserted_id
                    )
                )
                return str(result.inserted_id)
        except Exception as e:
            self.__logger.error(
                "Failed to insert custom field definition: {}".format(str(e))
            )
            raise

    async def find_by_slug(
        self, partner_id: int, entity_type: str, field_slug: str
    ) -> Optional[Dict[str, Any]]:
        try:
            async with self.__db_manager.collection(
                CustomFieldDefinition.CollectionName.CUSTOM_FIELD_DEFINITIONS
            ) as collection:
                return await collection.find_one(
                    {
                        "partner_id": partner_id,
                        "entity_type": entity_type,
                        "field_slug": field_slug,
                    }
                )
        except Exception as e:
            self.__logger.error(
                "Failed to find custom field by slug {}: {}".format(field_slug, str(e))
            )
            raise

    async def find_by_id(self, field_id: ObjectId) -> Optional[Dict[str, Any]]:
        try:
            async with self.__db_manager.collection(
                CustomFieldDefinition.CollectionName.CUSTOM_FIELD_DEFINITIONS
            ) as collection:
                return await collection.find_one({"_id": field_id})
        except Exception as e:
            self.__logger.error(
                "Failed to find custom field by id {}: {}".format(field_id, str(e))
            )
            raise

    async def find_all(
        self,
        partner_id: int,
        entity_type: str,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        try:
            query: Dict[str, Any] = {
                "partner_id": partner_id,
                "entity_type": entity_type,
            }
            if not include_inactive:
                query["is_active"] = True

            async with self.__db_manager.collection(
                CustomFieldDefinition.CollectionName.CUSTOM_FIELD_DEFINITIONS
            ) as collection:
                cursor = collection.find(query).sort("sequence", 1)
                return await cursor.to_list(None)
        except Exception as e:
            self.__logger.error(
                "Failed to list custom fields for partner {}, entity_type {}: {}".format(
                    partner_id, entity_type, str(e)
                )
            )
            raise

    async def update_by_id(
        self, field_id: ObjectId, update_dict: dict
    ) -> Optional[Dict[str, Any]]:
        try:
            async with self.__db_manager.collection(
                CustomFieldDefinition.CollectionName.CUSTOM_FIELD_DEFINITIONS
            ) as collection:
                return await collection.find_one_and_update(
                    {"_id": field_id}, {SET: update_dict}, return_document=True
                )
        except Exception as e:
            self.__logger.error(
                "Failed to update custom field {}: {}".format(field_id, str(e))
            )
            raise
