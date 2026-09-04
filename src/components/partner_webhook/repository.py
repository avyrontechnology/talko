from typing import Union

from src.components.partner_webhook.constant import DEFAULT_DELIVERY_ATTEMPTS_LIMIT
from src.components.partner_webhook.models import (
    TalkoPartnerWebhookConfigModel,
    TalkoWebhookDeliveryAttemptModel,
)
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoPartnerWebhookRepository:
    def __init__(
        self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger
    ):
        self.db_manager = db_manager
        self.logger = logger

    async def insert_config(self, doc: dict) -> str:
        try:
            async with self.db_manager.collection(
                TalkoPartnerWebhookConfigModel.CollectionName.PARTNER_WEBHOOK_CONFIGS
            ) as collection:
                result = await collection.insert_one(doc)
                self.logger.info(
                    "Inserted partner webhook config with ID: {}.".format(
                        result.inserted_id
                    )
                )
                return str(result.inserted_id)
        except Exception as e:
            self.logger.error(
                "Failed to insert partner webhook config: {}".format(str(e))
            )
            raise

    async def find_config_by_partner_id(self, partner_id: int) -> Union[dict, None]:
        try:
            async with self.db_manager.collection(
                TalkoPartnerWebhookConfigModel.CollectionName.PARTNER_WEBHOOK_CONFIGS
            ) as collection:
                return await collection.find_one({"partner_id": partner_id})
        except Exception as e:
            self.logger.error(
                "Failed to find partner webhook config for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
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
                    self.logger.error(
                        "Partner webhook config for partner_id {} not found".format(
                            partner_id
                        )
                    )
                    raise ValueError(
                        "Partner webhook config for partner_id {} not found".format(
                            partner_id
                        )
                    )
                self.logger.info(
                    "Updated partner webhook config for partner_id {}".format(
                        partner_id
                    )
                )
                return result
        except Exception as e:
            self.logger.error(
                "Failed to update partner webhook config for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise

    async def insert_delivery_attempt(self, doc: dict) -> str:
        try:
            async with self.db_manager.collection(
                TalkoWebhookDeliveryAttemptModel.CollectionName.WEBHOOK_DELIVERY_ATTEMPTS
            ) as collection:
                result = await collection.insert_one(doc)
                return str(result.inserted_id)
        except Exception as e:
            self.logger.error(
                "Failed to insert webhook delivery attempt: {}".format(str(e))
            )
            raise

    async def find_delivery_attempts_by_partner_id(
        self, partner_id: int, limit: int = DEFAULT_DELIVERY_ATTEMPTS_LIMIT
    ) -> list[dict]:
        try:
            async with self.db_manager.collection(
                TalkoWebhookDeliveryAttemptModel.CollectionName.WEBHOOK_DELIVERY_ATTEMPTS
            ) as collection:
                cursor = collection.find({"partner_id": partner_id}).sort(
                    "created_at", -1
                )
                return await cursor.to_list(length=limit)
        except Exception as e:
            self.logger.error(
                "Failed to find webhook delivery attempts for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise
