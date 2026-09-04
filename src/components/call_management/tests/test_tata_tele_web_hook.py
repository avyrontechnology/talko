from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.analytics.constants import INBOUND
from src.components.call_management.messages import (
    CALL_ID_MUST_BE_PROVIDED,
    CDR_NOT_FOUND,
    FAILED_TO_UPDATE,
)
from src.components.call_management.tata_tele.call_webhook import TalkoTataTeleWebhookHandler
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound


@pytest.mark.asyncio
class TestTataTeleWebhookHandler:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.logger = MagicMock()
        self.call_repository = AsyncMock()
        self.vendor = "tata_tele"

        self.handler = TalkoTataTeleWebhookHandler(
            self.logger, self.call_repository, self.vendor
        )
        self.handler.datetime_util = MagicMock()

        # Mock field mappings so updates become predictable
        patcher = patch(
            "src.components.call_management.tata_tele.call_webhook.TATA_WEBHOOK_FIELD_MAPPINGS",
            {
                "status": "status",
                "start_stamp": "start_stamp",
                "end_stamp": "end_stamp",
            },
        )
        self.mock_map_webhook = patcher.start()
        self.addCleanup = patcher.stop

        patcher2 = patch(
            "src.components.call_management.tata_tele.call_webhook.TATA_CDR_FIELD_MAPPING",
            {
                "status": "status",
                "duration": "total_call_duration",
                "outbound_sec": "talk_time",
            },
        )
        self.mock_map_cdr = patcher2.start()

    async def test_webhook_success_simple(self):
        payload = {"call_id": "abc123", "status": "completed"}
        cdr = {"_id": "some_id", "call_id": "abc123"}
        self.call_repository.get_cdr_by_call_id_or_uuid.return_value = cdr
        self.call_repository.update_cdr.return_value = True

        self.handler.datetime_util.get_current_time.return_value = "2025-07-29"

        response = await self.handler.process_webhook(payload)

        assert response == {"status": "success", "call_id": "abc123"}

        self.call_repository.update_cdr.assert_called_once_with(
            "some_id", {"status": "completed", "updated_at": "2025-07-29"}
        )

    async def test_webhook_missing_call_id(self):
        payload = {}

        with pytest.raises(TalkoBadRequestError) as exc:
            await self.handler.process_webhook(payload)

        assert str(exc.value) == CALL_ID_MUST_BE_PROVIDED
        self.logger.error.assert_called()

    async def test_webhook_cdr_not_found(self):
        payload = {"call_id": "abc123"}
        self.call_repository.get_cdr_by_call_id_or_uuid.return_value = None

        with pytest.raises(TalkoResourceNotFound) as exc:
            await self.handler.process_webhook(payload)

        assert str(exc.value) == CDR_NOT_FOUND

    async def test_webhook_failed_update(self):
        payload = {"call_id": "abc123", "status": "completed"}
        self.call_repository.get_cdr_by_call_id_or_uuid.return_value = {
            "_id": "some_id"
        }
        self.call_repository.update_cdr.return_value = False

        with pytest.raises(TalkoBadRequestError) as exc:
            await self.handler.process_webhook(payload)

        assert str(exc.value) == FAILED_TO_UPDATE

    async def test_timestamp_fields_converted(self):
        payload = {
            "call_id": "abc123",
            "start_stamp": "2025-08-01T10:00:00Z",
            "end_stamp": "2025-08-01T10:10:00Z",
        }
        cdr = {"_id": "some_id"}
        self.call_repository.get_cdr_by_call_id_or_uuid.return_value = cdr
        self.call_repository.update_cdr.return_value = True

        self.handler.datetime_util.convert_date_time.side_effect = (
            lambda x: f"converted-{x}"
        )
        self.handler.datetime_util.get_current_time.return_value = "NOW"

        response = await self.handler.process_webhook(payload)
        assert response["status"] == "success"

        self.handler.datetime_util.convert_date_time.assert_any_call(
            "2025-08-01T10:00:00Z"
        )
        self.handler.datetime_util.convert_date_time.assert_any_call(
            "2025-08-01T10:10:00Z"
        )

    async def test_int_fields_converted(self):
        payload = {"call_id": "abc123", "duration": "12", "outbound_sec": "10"}
        cdr = {"_id": "some_id"}
        self.call_repository.get_cdr_by_call_id_or_uuid.return_value = cdr
        self.call_repository.update_cdr.return_value = True

        self.handler.datetime_util.get_current_time.return_value = "NOW"

        response = await self.handler.process_cdr_api_payload(payload, call_id="abc123")

        updates = self.call_repository.update_cdr.call_args[0][1]
        assert updates["total_call_duration"] == 12
        assert updates["talk_time"] == 10

    async def test_api_missing_call_id_and_uuid(self):
        payload = {}

        with pytest.raises(TalkoBadRequestError):
            await self.handler.process_cdr_api_payload(payload)

    async def test_api_success(self):
        payload = {"status": "completed"}
        cdr = {"_id": "some_id"}
        self.call_repository.get_cdr_by_call_id_or_uuid.return_value = cdr
        self.call_repository.update_cdr.return_value = True

        response = await self.handler.process_cdr_api_payload(payload, call_id="abc123")

        assert response["status"] == "success"

    async def test_answered_agent_number_from_payload(self):
        payload = {"call_id": "abc123", "answered_agent_number": "9876543210"}

        cdr = {
            "_id": "some_id",
            "call_id": "abc123",
            "agent_ids": [{"agent_number": "9876543210", "agent_id": "agent_1"}],
        }

        self.handler.call_repository.get_cdr_by_call_id_or_uuid.return_value = cdr
        self.handler.call_repository.update_cdr.return_value = True
        self.handler.datetime_util.get_current_time.return_value = (
            "2025-08-10T12:00:00Z"
        )

        response = await self.handler.process_webhook(payload)
        assert response["status"] == "success"

        updates = self.handler.call_repository.update_cdr.call_args[0][1]
        assert updates["agent"] == "agent_1"
        assert updates["agent_number"] == "9876543210"

    async def test_answered_agent_number_from_missed_agents(self):
        payload = {
            "call_id": "abc123",
            "missed_agents": {"agent_number": "999888777666"},
        }
        cdr = {
            "_id": "some_id",
            "agent_ids": [{"agent_number": "9888777666", "agent_id": 22}],
        }

        self.call_repository.get_cdr_by_call_id_or_uuid.return_value = cdr
        self.call_repository.update_cdr.return_value = True
        self.handler.datetime_util.get_current_time.return_value = "NOW"

        response = await self.handler.process_webhook(payload)

        updates = self.call_repository.update_cdr.call_args[0][1]
        assert updates["agent"] == 22

    async def test_inbound_call_without_agent_ids(self):
        payload = {
            "call_id": "abc123",
            "answered_agent_number": "9998887777",
        }

        cdr = {
            "_id": "some_id",
            "call_id": "abc123",
            "calling_mode": INBOUND,
            "agent_ids": [],
        }

        self.handler.call_repository.get_cdr_by_call_id_or_uuid.return_value = cdr
        self.handler.call_repository.update_cdr.return_value = True
        self.handler.datetime_util.get_current_time.return_value = (
            "2025-08-10T12:00:00Z"
        )

        response = await self.handler.process_webhook(payload)
        assert response["status"] == "success"

        updates = self.handler.call_repository.update_cdr.call_args[0][1]
        assert updates["agent_number"] == "9998887777"


@pytest.mark.asyncio
class TestResultsBranch:

    async def test_process_payload_with_results_key(self):
        handler = TalkoTataTeleWebhookHandler(MagicMock(), AsyncMock(), "tata_tele")
        handler.datetime_util = MagicMock()
        handler.datetime_util.get_current_time.return_value = "TIME"

        handler.call_repository.get_cdr_by_call_id_or_uuid.return_value = {
            "_id": "some_id",
            "call_id": "abc123",
        }
        handler.call_repository.update_cdr.return_value = True

        payload = {"call_id": "abc123", "results": [{"status": "completed"}]}

        response = await handler.process_webhook(payload)
        assert response == {"status": "success", "call_id": "abc123"}


@pytest.mark.asyncio
class TestRelayToMakunai:
    """
    AI-bridge/campaign calls complete via TalkoTataTeleWebhookHandler (Tata's
    standard call webhook, calling_mode=clicktocall) — NOT TalkoDialerWebhookHandler,
    which is a different Tata Tele product we don't use for campaigns. The
    relay (shared via TalkoWebhookHandler._relay_to_makunai) must fire from here.
    """

    _HTTPX_PATCH_PATH = (
        "src.components.call_management.handlers.webhook_base_handler.httpx.AsyncClient"
    )

    def _make_handler(self):
        logger = MagicMock()
        call_repository = AsyncMock()
        handler = TalkoTataTeleWebhookHandler(logger, call_repository, "tata_tele")
        handler.datetime_util = MagicMock()
        handler.datetime_util.get_current_time.return_value = "TIME"
        return handler, call_repository

    def _mock_httpx_client(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client

    async def test_webhook_relays_when_partner_id_present(self):
        handler, call_repository = self._make_handler()
        call_repository.get_cdr_by_call_id_or_uuid.return_value = {
            "_id": "some_id",
            "call_id": "abc123",
            "partner_id": 101,
        }
        call_repository.update_cdr.return_value = True

        payload = {"call_id": "abc123", "status": "completed"}
        mock_client = self._mock_httpx_client()
        with patch(self._HTTPX_PATCH_PATH, return_value=mock_client):
            await handler.process_webhook(payload)

        mock_client.post.assert_awaited_once()
        args, kwargs = mock_client.post.call_args
        assert kwargs["json"] == {
            "call_id": "abc123",
            "status": "completed",
            "partner_id": 101,
        }
        assert "X-Webhook-Secret" in kwargs["headers"]

    async def test_webhook_skips_relay_when_no_partner_id_on_cdr(self):
        handler, call_repository = self._make_handler()
        call_repository.get_cdr_by_call_id_or_uuid.return_value = {
            "_id": "some_id",
            "call_id": "abc123",
        }
        call_repository.update_cdr.return_value = True

        payload = {"call_id": "abc123", "status": "completed"}
        mock_client = self._mock_httpx_client()
        with patch(self._HTTPX_PATCH_PATH, return_value=mock_client):
            await handler.process_webhook(payload)

        mock_client.post.assert_not_awaited()

    async def test_api_payload_never_relays_even_with_partner_id(self):
        """process_cdr_api_payload (source=API, TalkoCDR polling) is not a live
        webhook delivery — relaying it would be meaningless/duplicative."""
        handler, call_repository = self._make_handler()
        call_repository.get_cdr_by_call_id_or_uuid.return_value = {
            "_id": "some_id",
            "call_id": "abc123",
            "partner_id": 101,
        }
        call_repository.update_cdr.return_value = True

        payload = {"status": "completed"}
        mock_client = self._mock_httpx_client()
        with patch(self._HTTPX_PATCH_PATH, return_value=mock_client):
            await handler.process_cdr_api_payload(payload, call_id="abc123")

        mock_client.post.assert_not_awaited()

    async def test_relay_failure_does_not_break_webhook_response(self):
        handler, call_repository = self._make_handler()
        call_repository.get_cdr_by_call_id_or_uuid.return_value = {
            "_id": "some_id",
            "call_id": "abc123",
            "partner_id": 101,
        }
        call_repository.update_cdr.return_value = True

        payload = {"call_id": "abc123", "status": "completed"}
        with patch(
            self._HTTPX_PATCH_PATH, side_effect=RuntimeError("connection refused")
        ):
            response = await handler.process_webhook(payload)

        assert response == {"status": "success", "call_id": "abc123"}


@pytest.mark.asyncio
class TestWebhookEventTrigger:
    """A completed call (source=WEBHOOK, call_status answered/missed) must
    enqueue a partner webhook delivery — see partner_webhook/tasks.py."""

    _DELIVER_PATCH_PATH = (
        "src.components.partner_webhook.tasks.deliver_webhook_event.apply_async"
    )

    def _make_handler(self):
        logger = MagicMock()
        call_repository = AsyncMock()
        handler = TalkoTataTeleWebhookHandler(logger, call_repository, "tata_tele")
        handler.datetime_util = MagicMock()
        handler.datetime_util.get_current_time.return_value = "TIME"
        return handler, call_repository

    def _patch_mappings(self):
        return patch.multiple(
            "src.components.call_management.tata_tele.call_webhook",
            TATA_WEBHOOK_FIELD_MAPPINGS={"call_status": "call_status"},
            TATA_CDR_FIELD_MAPPING={"call_status": "call_status"},
        )

    async def test_answered_call_enqueues_webhook_delivery(self):
        handler, call_repository = self._make_handler()
        call_repository.get_cdr_by_call_id_or_uuid.return_value = {
            "_id": "some_id",
            "call_id": "abc123",
            "partner_id": 101,
        }
        call_repository.update_cdr.return_value = True

        payload = {"call_id": "abc123", "call_status": "answered"}
        with self._patch_mappings(), patch(self._DELIVER_PATCH_PATH) as mock_apply_async:
            await handler.process_webhook(payload)

        mock_apply_async.assert_called_once()
        kwargs = mock_apply_async.call_args.kwargs["kwargs"]
        assert kwargs["partner_id"] == 101
        assert kwargs["event_type"] == "call.completed"
        assert "event_id" in kwargs
        assert kwargs["payload"]["call_status"] == "answered"

    async def test_missed_call_enqueues_webhook_delivery(self):
        handler, call_repository = self._make_handler()
        call_repository.get_cdr_by_call_id_or_uuid.return_value = {
            "_id": "some_id",
            "call_id": "abc123",
            "partner_id": 101,
            "action": "outbound",
        }
        call_repository.update_cdr.return_value = True

        payload = {"call_id": "abc123", "call_status": "missed"}
        with self._patch_mappings(), patch(self._DELIVER_PATCH_PATH) as mock_apply_async:
            await handler.process_webhook(payload)

        mock_apply_async.assert_called_once()

    async def test_no_partner_id_skips_webhook_delivery(self):
        handler, call_repository = self._make_handler()
        call_repository.get_cdr_by_call_id_or_uuid.return_value = {
            "_id": "some_id",
            "call_id": "abc123",
        }
        call_repository.update_cdr.return_value = True

        payload = {"call_id": "abc123", "call_status": "answered"}
        with self._patch_mappings(), patch(self._DELIVER_PATCH_PATH) as mock_apply_async:
            await handler.process_webhook(payload)

        mock_apply_async.assert_not_called()

    async def test_non_terminal_status_skips_webhook_delivery(self):
        handler, call_repository = self._make_handler()
        call_repository.get_cdr_by_call_id_or_uuid.return_value = {
            "_id": "some_id",
            "call_id": "abc123",
            "partner_id": 101,
        }
        call_repository.update_cdr.return_value = True

        payload = {"call_id": "abc123", "call_status": "ringing"}
        with self._patch_mappings(), patch(self._DELIVER_PATCH_PATH) as mock_apply_async:
            await handler.process_webhook(payload)

        mock_apply_async.assert_not_called()

    async def test_api_source_never_enqueues_webhook_delivery(self):
        """process_cdr_api_payload (source=API, TalkoCDR polling) must not
        fire live-delivery side effects, same rule as the makun-ai relay."""
        handler, call_repository = self._make_handler()
        call_repository.get_cdr_by_call_id_or_uuid.return_value = {
            "_id": "some_id",
            "call_id": "abc123",
            "partner_id": 101,
        }
        call_repository.update_cdr.return_value = True

        payload = {"call_status": "answered"}
        with self._patch_mappings(), patch(self._DELIVER_PATCH_PATH) as mock_apply_async:
            await handler.process_cdr_api_payload(payload, call_id="abc123")

        mock_apply_async.assert_not_called()
