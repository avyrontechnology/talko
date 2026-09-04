from unittest.mock import MagicMock

import pytest

from src.components.call_management.handlers.webhook_base_handler import WebhookHandler


class TestWebhookHandler:

    @pytest.mark.asyncio
    async def test_abstract_base_functionality(self):
        """Test basic initialization and hit the 'pass' lines via super()."""

        class MockWebhookHandler(WebhookHandler):
            async def process_webhook(self, payload):
                await super().process_webhook(payload)
                return {"status": "mocked"}

            async def process_cdr_api_payload(self, payload, call_id=None, uuid=None):
                await super().process_cdr_api_payload(payload, call_id, uuid)
                return {"status": "mocked"}

        mock_logger = MagicMock()
        mock_call_repo = MagicMock()

        handler = MockWebhookHandler(
            logger=mock_logger, call_repository=mock_call_repo, vendor_type="tata_tele"
        )

        await handler.process_webhook({})
        await handler.process_cdr_api_payload({})

        assert handler.vendor_type == "tata_tele"
        assert handler.datetime_util is not None

    def test_cannot_instantiate_abstract_class(self):
        """
        Ensures the class remains abstract.
        """
        with pytest.raises(TypeError) as excinfo:
            WebhookHandler(MagicMock(), MagicMock(), "vendor")

        assert "Can't instantiate abstract class WebhookHandler" in str(excinfo.value)
