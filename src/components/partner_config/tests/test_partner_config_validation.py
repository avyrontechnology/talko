from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.partner_config.message import (
    PARTNER_CONFIG_WITH_PARTNER_ID_ALREADY_EXIST,
)
from src.components.partner_config.repository import TalkoPartnerConfigRepository
from src.components.partner_config.validation import TalkoPartnerConfigValidator
from src.loggers.talko_service_logger import TalkoServiceLogger


@pytest.mark.asyncio
class TestPartnerConfigValidator:
    @pytest.fixture
    def mock_logger(self):
        return MagicMock(spec=TalkoServiceLogger)

    @pytest.fixture
    def mock_partner_config_repository(self):
        return MagicMock(spec=TalkoPartnerConfigRepository)

    @pytest.fixture
    def validator(self, mock_logger, mock_partner_config_repository):
        return TalkoPartnerConfigValidator(
            logger=mock_logger,
            partner_config_repository=mock_partner_config_repository,
        )

    async def test_validate_partner_config_exists_success(self, validator, mock_partner_config_repository, mock_logger):
        mock_partner_config_repository.find_partner_config_by_partner_and_client = AsyncMock(return_value=True)

        with pytest.raises(Exception) as exc_info:
            await validator.check_if_already_partner_exist_in_partner_config(123, None)

        assert str(exc_info.value) == PARTNER_CONFIG_WITH_PARTNER_ID_ALREADY_EXIST
        mock_partner_config_repository.find_partner_config_by_partner_and_client.assert_called_once_with(123, None)
        mock_logger.error.assert_called_once()

    async def test_validate_partner_config_not_exists(self, validator, mock_partner_config_repository, mock_logger):
        mock_partner_config_repository.find_partner_config_by_partner_and_client = AsyncMock(return_value=None)

        await validator.check_if_already_partner_exist_in_partner_config(123, None)

        mock_partner_config_repository.find_partner_config_by_partner_and_client.assert_called_once_with(123, None)
        mock_logger.error.assert_not_called()
