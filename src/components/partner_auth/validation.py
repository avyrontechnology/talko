from src.components.partner_auth.message import PARTNER_API_KEY_NOT_FOUND
from src.components.partner_auth.repository import TalkoPartnerApiKeyRepository
from src.exceptions import TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoPartnerApiKeyValidator:
    def __init__(
        self,
        logger: TalkoServiceLogger,
        repository: TalkoPartnerApiKeyRepository,
    ):
        self.logger = logger
        self.repository = repository

    async def validate_key_exists(self, id: str) -> dict:
        api_key = await self.repository.find_by_id(id)
        if not api_key:
            self.logger.error("Partner api key with id {} not found".format(id))
            raise TalkoResourceNotFound(PARTNER_API_KEY_NOT_FOUND)
        return api_key
