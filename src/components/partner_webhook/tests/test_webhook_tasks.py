from unittest.mock import AsyncMock, MagicMock, patch

from src.components.partner_webhook.tasks import deliver_webhook_event


class TestDeliverWebhookEventTask:
    """deliver_webhook_event is a thin asyncio.run() wrapper around
    TalkoPartnerWebhookService.deliver_event (see that method's tests in
    test_partner_webhook_service.py for the actual delivery logic).

    Deliberately does NOT invoke the task via .run()/.apply() here: doing so
    calls asyncio.run() from within a sync pytest test, which corrupts the
    thread's asyncio event loop state for later, unrelated tests elsewhere
    in the suite (observed breaking src/grpc_client/tests/test_auth_service_client.py
    when both ran in the same session). Mocking asyncio.run() itself avoids that.
    """

    def test_delegates_to_service_deliver_event(self):
        service = MagicMock()
        service.deliver_event = AsyncMock(return_value="delivered")

        with patch(
            "src.components.partner_webhook.tasks.TalkoContainer"
        ) as mock_container_cls, patch(
            "src.components.partner_webhook.tasks.asyncio.run"
        ) as mock_asyncio_run:
            mock_container_cls.return_value.partner_webhook_service.return_value = service
            mock_asyncio_run.return_value = "delivered"

            result = deliver_webhook_event.run(
                partner_id=1,
                event_type="call.completed",
                event_id="evt-1",
                payload={"call_id": "abc"},
            )

        assert result == "delivered"
        mock_asyncio_run.assert_called_once()
        service.deliver_event.assert_called_once_with(
            partner_id=1,
            event_type="call.completed",
            event_id="evt-1",
            payload={"call_id": "abc"},
            attempt_number=1,
        )
