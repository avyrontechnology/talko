from bson import ObjectId

from src.components.partner_config.message import (
    PARTNER_CONFIG_WITH_PARTNER_ID_ALREADY_EXIST,
)
from src.components.partner_config.repository import TalkoPartnerConfigRepository
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoPartnerConfigValidator:
    """
    Validator class for partner configuration operations.

    Ensures that partners and their configurations exist or meet certain criteria
    before proceeding with create/update actions.
    """

    def __init__(
        self,
        logger: TalkoServiceLogger,
        partner_config_repository: TalkoPartnerConfigRepository,
    ):
        """
        Initialize the validator with repositories and logger.

        :param logger: Logger for logging validation activities.
        :param partner_config_repository: Repository to access partner config data.
        """
        self.logger = logger
        self.partner_config_repository = partner_config_repository

    async def check_if_already_partner_exist_in_partner_config(
        self, partner_id: int
    ) -> None:
        """
        Validate that a partner exists and no config already exists for it.

        :param partner_id: The ObjectId of the partner.
        :raises ValueError: If the partner config already exists for partner id.
        """
        partner_config = (
            await self.partner_config_repository.find_partner_config_by_partner_id(
                partner_id
            )
        )
        if partner_config:
            self.logger.error(
                "Partner id: {} already exists in partner config.".format(partner_id)
            )
            raise ValueError(PARTNER_CONFIG_WITH_PARTNER_ID_ALREADY_EXIST)
