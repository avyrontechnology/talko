from src.components.partner_webhook.constant import DEFAULT_DELIVERY_ATTEMPTS_LIMIT
from src.components.partner_webhook.models import (
    TalkoPartnerWebhookConfigModel,
    TalkoWebhookDeliveryAttemptModel,
)
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoPartnerWebhookRepository:
    def __init__(self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger):
        self.db_manager = db_manager
        self.logger = logger

    async def insert_config(self, doc: dict) -> str:
        try:
            async with self.db_manager.collection(
                TalkoPartnerWebhookConfigModel.CollectionName.PARTNER_WEBHOOK_CONFIGS
            ) as collection:
                result = await collection.insert_one(doc)
                self.logger.info(f"Inserted partner webhook config with ID: {result.inserted_id}.")
                return str(result.inserted_id)
        except Exception as e:
            self.logger.error(f"Failed to insert partner webhook config: {str(e)}")
            raise

    async def find_config_by_partner_id(self, partner_id: int) -> dict | None:
        try:
            async with self.db_manager.collection(
                TalkoPartnerWebhookConfigModel.CollectionName.PARTNER_WEBHOOK_CONFIGS
            ) as collection:
                return await collection.find_one({"partner_id": partner_id})
        except Exception as e:
            self.logger.error(f"Failed to find partner webhook config for partner_id {partner_id}: {str(e)}")
            raise

    async def update_config(self, partner_id: int, update_dict: dict) -> dict:
        try:
            async with self.db_manager.collection(
                TalkoPartnerWebhookConfigModel.CollectionName.PARTNER_WEBHOOK_CONFIGS
            ) as collection:
                result = await collection.find_one_and_update(
                    {"partner_id": partner_id},
                    {"$set": update_dict},
                    return_document=True,
                )
                if not result:
                    self.logger.error(f"Partner webhook config for partner_id {partner_id} not found")
                    raise ValueError(f"Partner webhook config for partner_id {partner_id} not found")
                self.logger.info(f"Updated partner webhook config for partner_id {partner_id}")
                return result
        except Exception as e:
            self.logger.error(f"Failed to update partner webhook config for partner_id {partner_id}: {str(e)}")
            raise

    async def insert_delivery_attempt(self, doc: dict) -> str:
        try:
            async with self.db_manager.collection(
                TalkoWebhookDeliveryAttemptModel.CollectionName.WEBHOOK_DELIVERY_ATTEMPTS
            ) as collection:
                result = await collection.insert_one(doc)
                return str(result.inserted_id)
        except Exception as e:
            self.logger.error(f"Failed to insert webhook delivery attempt: {str(e)}")
            raise

    async def find_delivery_attempts_by_partner_id(
        self, partner_id: int, limit: int = DEFAULT_DELIVERY_ATTEMPTS_LIMIT
    ) -> list[dict]:
        try:
            async with self.db_manager.collection(
                TalkoWebhookDeliveryAttemptModel.CollectionName.WEBHOOK_DELIVERY_ATTEMPTS
            ) as collection:
                cursor = collection.find({"partner_id": partner_id}).sort("created_at", -1)
                return await cursor.to_list(length=limit)
        except Exception as e:
            self.logger.error(f"Failed to find webhook delivery attempts for partner_id {partner_id}: {str(e)}")
            raise
