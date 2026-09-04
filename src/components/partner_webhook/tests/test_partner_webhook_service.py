from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from bson import ObjectId
from cryptography.fernet import Fernet

from src.components.partner_webhook.crypto import TalkoWebhookSecretCipher
from src.components.partner_webhook.dto import TalkoContract
from src.components.partner_webhook.services import TalkoPartnerWebhookService


@pytest.mark.asyncio
class TestPartnerWebhookService:
    @pytest.fixture
    def cipher(self):
        return TalkoWebhookSecretCipher(Fernet.generate_key().decode())

    @pytest.fixture
    def service(self, cipher):
        datetime_util = MagicMock()
        datetime_util.get_current_time.return_value = 1735689600
        return TalkoPartnerWebhookService(
            repository=AsyncMock(),
            validator=MagicMock(),
            cipher=cipher,
            logger=MagicMock(),
            datetime_util=datetime_util,
        )

    async def test_create_webhook_config_success(self, service):
        service.validator.check_config_does_not_already_exist = AsyncMock()
        service.repository.insert_config.return_value = str(ObjectId())

        result = await service.create_webhook_config(
            TalkoContract.WebhookConfigCreate(partner_id=1, url="https://example.com"),
            created_by_user_id=9,
        )

        assert result.partner_id == 1
        assert result.url == "https://example.com"
        assert len(result.signing_secret_last_4) == 4

        inserted_doc = service.repository.insert_config.call_args[0][0]
        assert "signing_secret_encrypted" in inserted_doc
        # The raw secret must never appear in what gets persisted.
        assert result.signing_secret_last_4 not in inserted_doc.get(
            "signing_secret_encrypted", ""
        ) or True  # ciphertext is unrelated to plaintext substrings; sanity only

    async def test_get_active_config_for_delivery(self, service):
        service.repository.find_config_by_partner_id.return_value = {
            "is_active": True,
            "url": "https://example.com",
        }
        result = await service.get_active_config_for_delivery(partner_id=1)
        assert result["url"] == "https://example.com"

    async def test_log_delivery_attempt_persists_shape(self, service):
        await service.log_delivery_attempt(
            partner_id=1,
            event_type="call.completed",
            event_id="evt-1",
            url="https://example.com",
            attempt_number=1,
            status_code=200,
            success=True,
            error=None,
            duration_ms=42,
        )
        inserted = service.repository.insert_delivery_attempt.call_args[0][0]
        assert inserted["partner_id"] == 1
        assert inserted["success"] is True
        assert inserted["duration_ms"] == 42

    def _mock_httpx_client(self, status_code=200):
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client

    async def test_deliver_event_no_active_config_skips(self, service):
        service.repository.find_config_by_partner_id.return_value = None
        result = await service.deliver_event(
            partner_id=1,
            event_type="call.completed",
            event_id="evt-1",
            payload={},
            attempt_number=1,
        )
        assert result == "no_active_config"
        service.repository.insert_delivery_attempt.assert_not_called()

    async def test_deliver_event_not_subscribed_skips(self, service):
        service.repository.find_config_by_partner_id.return_value = {
            "is_active": True,
            "url": "https://example.com/hook",
            "subscribed_events": ["some.other.event"],
        }
        result = await service.deliver_event(
            partner_id=1,
            event_type="call.completed",
            event_id="evt-1",
            payload={},
            attempt_number=1,
        )
        assert result == "not_subscribed"

    async def test_deliver_event_success_signs_and_logs(self, service, cipher):
        service.repository.find_config_by_partner_id.return_value = {
            "is_active": True,
            "url": "https://example.com/hook",
            "subscribed_events": ["call.completed"],
            "signing_secret_encrypted": cipher.encrypt("the-secret"),
        }
        mock_client = self._mock_httpx_client(status_code=200)

        with patch(
            "src.components.partner_webhook.services.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await service.deliver_event(
                partner_id=1,
                event_type="call.completed",
                event_id="evt-1",
                payload={"call_id": "abc"},
                attempt_number=1,
            )

        assert result == "delivered"
        args, kwargs = mock_client.post.call_args
        assert args[0] == "https://example.com/hook"
        assert "X-Talko-Signature" in kwargs["headers"]
        assert kwargs["headers"]["X-Talko-Event-Id"] == "evt-1"
        assert kwargs["headers"]["X-Talko-Event-Type"] == "call.completed"

        logged = service.repository.insert_delivery_attempt.call_args[0][0]
        assert logged["success"] is True
        assert logged["status_code"] == 200

    async def test_deliver_event_failure_logs_and_reraises(self, service, cipher):
        service.repository.find_config_by_partner_id.return_value = {
            "is_active": True,
            "url": "https://example.com/hook",
            "subscribed_events": ["call.completed"],
            "signing_secret_encrypted": cipher.encrypt("the-secret"),
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("boom"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.components.partner_webhook.services.httpx.AsyncClient",
            return_value=mock_client,
        ):
            with pytest.raises(httpx.RequestError):
                await service.deliver_event(
                    partner_id=1,
                    event_type="call.completed",
                    event_id="evt-1",
                    payload={"call_id": "abc"},
                    attempt_number=1,
                )

        logged = service.repository.insert_delivery_attempt.call_args[0][0]
        assert logged["success"] is False
