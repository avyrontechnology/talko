from src.components.partner_auth.models import TalkoPartnerApiKeyModel
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoPartnerApiKeyRepository:
    """Repository for CRUD operations on partner API key documents."""

    def __init__(self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger):
        self.db_manager = db_manager
        self.logger = logger

    async def insert_api_key(self, doc: dict) -> str:
        try:
            async with self.db_manager.collection(
                TalkoPartnerApiKeyModel.CollectionName.PARTNER_API_KEYS
            ) as collection:
                result = await collection.insert_one(doc)
                self.logger.info(f"Inserted partner api key with ID: {result.inserted_id}.")
                return str(result.inserted_id)
        except Exception as e:
            self.logger.error(f"Failed to insert partner api key: {str(e)}")
            raise

    async def find_by_key_hash(self, key_hash: str) -> dict | None:
        try:
            async with self.db_manager.collection(
                TalkoPartnerApiKeyModel.CollectionName.PARTNER_API_KEYS
            ) as collection:
                return await collection.find_one({"key_hash": key_hash})
        except Exception as e:
            self.logger.error(f"Failed to find partner api key by hash: {str(e)}")
            raise

    async def find_all_by_partner_id(self, partner_id: int) -> list[dict]:
        try:
            async with self.db_manager.collection(
                TalkoPartnerApiKeyModel.CollectionName.PARTNER_API_KEYS
            ) as collection:
                return await collection.find({"partner_id": partner_id}).to_list(length=None)
        except Exception as e:
            self.logger.error(f"Failed to find partner api keys for partner_id {partner_id}: {str(e)}")
            raise

    async def find_by_id(self, id: str) -> dict | None:
        try:
            async with self.db_manager.collection(
                TalkoPartnerApiKeyModel.CollectionName.PARTNER_API_KEYS
            ) as collection:
                return await collection.find_one({"_id": id})
        except Exception as e:
            self.logger.error(f"Failed to find partner api key by id {id}: {str(e)}")
            raise

    async def revoke(self, id: str, revoked_at: int) -> dict | None:
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
                    self.logger.error(f"Partner api key with id {id} not found for revoke")
                    raise ValueError(f"Partner api key with id {id} not found")
                self.logger.info(f"Revoked partner api key {id}")
                return result
        except Exception as e:
            self.logger.error(f"Failed to revoke partner api key {id}: {str(e)}")
            raise

    async def touch_last_used(self, id, last_used_at: int) -> None:
        # Best-effort — a failure here must never break request auth.
        try:
            async with self.db_manager.collection(
                TalkoPartnerApiKeyModel.CollectionName.PARTNER_API_KEYS
            ) as collection:
                await collection.update_one({"_id": id}, {"$set": {"last_used_at": last_used_at}})
        except Exception as e:
            self.logger.error(f"Failed to touch last_used_at for partner api key {id}: {str(e)}")
