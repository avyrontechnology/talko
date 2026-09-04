from src.components.partner_webhook.message import (
    PARTNER_WEBHOOK_CONFIG_ALREADY_EXISTS,
    PARTNER_WEBHOOK_URL_MUST_BE_HTTPS,
)
from src.components.partner_webhook.repository import TalkoPartnerWebhookRepository
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoPartnerWebhookValidator:
    def __init__(
        self,
        logger: TalkoServiceLogger,
        repository: TalkoPartnerWebhookRepository,
    ):
        self.logger = logger
        self.repository = repository

    def validate_url_is_https(self, url: str) -> None:
        if not url.startswith("https://"):
            self.logger.error("Rejected non-https webhook url: {}".format(url))
            raise ValueError(PARTNER_WEBHOOK_URL_MUST_BE_HTTPS)

    async def check_config_does_not_already_exist(self, partner_id: int) -> None:
        existing = await self.repository.find_config_by_partner_id(partner_id)
        if existing:
            self.logger.error(
                "Webhook config already exists for partner_id: {}".format(partner_id)
            )
            raise ValueError(PARTNER_WEBHOOK_CONFIG_ALREADY_EXISTS)
