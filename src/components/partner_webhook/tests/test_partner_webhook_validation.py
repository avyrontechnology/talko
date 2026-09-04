from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.partner_webhook.validation import TalkoPartnerWebhookValidator


@pytest.mark.asyncio
class TestPartnerWebhookValidator:
    @pytest.fixture
    def validator(self):
        return TalkoPartnerWebhookValidator(logger=MagicMock(), repository=AsyncMock())

    def test_validate_url_is_https_accepts_https(self, validator):
        validator.validate_url_is_https("https://example.com/webhook")  # no raise

    def test_validate_url_is_https_rejects_http(self, validator):
        with pytest.raises(ValueError):
            validator.validate_url_is_https("http://example.com/webhook")

    async def test_check_config_does_not_already_exist_passes_when_absent(
        self, validator
    ):
        validator.repository.find_config_by_partner_id.return_value = None
        await validator.check_config_does_not_already_exist(1)  # no raise

    async def test_check_config_does_not_already_exist_raises_when_present(
        self, validator
    ):
        validator.repository.find_config_by_partner_id.return_value = {"partner_id": 1}
        with pytest.raises(ValueError):
            await validator.check_config_does_not_already_exist(1)
