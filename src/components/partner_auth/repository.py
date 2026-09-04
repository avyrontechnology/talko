from typing import Union

from src.components.partner_auth.models import TalkoPartnerApiKeyModel
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoPartnerApiKeyRepository:
    """Repository for CRUD operations on partner API key documents."""

    def __init__(
        self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger
    ):
        self.db_manager = db_manager
        self.logger = logger

    async def insert_api_key(self, doc: dict) -> str:
        try:
            async with self.db_manager.collection(
                TalkoPartnerApiKeyModel.CollectionName.PARTNER_API_KEYS
            ) as collection:
                result = await collection.insert_one(doc)
                self.logger.info(
                    "Inserted partner api key with ID: {}.".format(result.inserted_id)
                )
                return str(result.inserted_id)
        except Exception as e:
            self.logger.error("Failed to insert partner api key: {}".format(str(e)))
            raise

    async def find_by_key_hash(self, key_hash: str) -> Union[dict, None]:
        try:
            async with self.db_manager.collection(
                TalkoPartnerApiKeyModel.CollectionName.PARTNER_API_KEYS
            ) as collection:
                return await collection.find_one({"key_hash": key_hash})
        except Exception as e:
            self.logger.error(
                "Failed to find partner api key by hash: {}".format(str(e))
            )
            raise

    async def find_all_by_partner_id(self, partner_id: int) -> list[dict]:
        try:
            async with self.db_manager.collection(
                TalkoPartnerApiKeyModel.CollectionName.PARTNER_API_KEYS
            ) as collection:
                return await collection.find({"partner_id": partner_id}).to_list(
                    length=None
                )
        except Exception as e:
            self.logger.error(
                "Failed to find partner api keys for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise

    async def find_by_id(self, id: str) -> Union[dict, None]:
        try:
            async with self.db_manager.collection(
                TalkoPartnerApiKeyModel.CollectionName.PARTNER_API_KEYS
            ) as collection:
                return await collection.find_one({"_id": id})
        except Exception as e:
            self.logger.error(
                "Failed to find partner api key by id {}: {}".format(id, str(e))
            )
            raise

    async def revoke(self, id: str, revoked_at: int) -> Union[dict, None]:
        try:
            async with self.db_manager.collection(
                TalkoPartnerApiKeyModel.CollectionName.PARTNER_API_KEYS
            ) as collection:
                result = await collection.find_one_and_update(
                    {"_id": id},
                    {"$set": {"is_active": False, "revoked_at": revoked_at}},
                    return_document=True,
                )
                if not result:
                    self.logger.error(
                        "Partner api key with id {} not found for revoke".format(id)
                    )
                    raise ValueError(
                        "Partner api key with id {} not found".format(id)
                    )
                self.logger.info("Revoked partner api key {}".format(id))
                return result
        except Exception as e:
            self.logger.error(
                "Failed to revoke partner api key {}: {}".format(id, str(e))
            )
            raise

    async def touch_last_used(self, id, last_used_at: int) -> None:
        # Best-effort — a failure here must never break request auth.
        try:
            async with self.db_manager.collection(
                TalkoPartnerApiKeyModel.CollectionName.PARTNER_API_KEYS
            ) as collection:
                await collection.update_one(
                    {"_id": id}, {"$set": {"last_used_at": last_used_at}}
                )
        except Exception as e:
            self.logger.error(
                "Failed to touch last_used_at for partner api key {}: {}".format(
                    id, str(e)
                )
            )
