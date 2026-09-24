from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.call_management.otoba.call_webhook import TalkoOtobaWebhookHandler


def _handler():
    return TalkoOtobaWebhookHandler(logger=MagicMock(), call_repository=MagicMock(), vendor_type="otoba")


class TestNormalize:
    def test_snake_keys(self):
        h = _handler()
        out = h.normalize({"call_id": "C1", "status": "completed", "duration": 42})
        assert out["call_id"] == "C1"
        assert out["call_status"] == "completed"
        assert out["total_call_duration"] == 42

    def test_camel_keys(self):
        h = _handler()
        out = h.normalize({"callId": "C2", "callStatus": "busy", "callDuration": 7})
        assert out["call_id"] == "C2"
        assert out["call_status"] == "busy"
        assert out["total_call_duration"] == 7

    def test_envelope_unwrap(self):
        h = _handler()
        out = h.normalize({"data": {"call_id": "C3", "status": "done"}})
        assert out["call_id"] == "C3"

    def test_field_map_override(self):
        h = TalkoOtobaWebhookHandler(
            logger=MagicMock(),
            call_repository=MagicMock(),
            vendor_type="otoba",
            field_map={"custom_status": "call_status"},
        )
        out = h.normalize({"custom_status": "x"})
        assert out["call_status"] == "x"

    @pytest.mark.asyncio
    async def test_process_delegates_normalized(self):
        h = _handler()
        from unittest.mock import patch

        with patch(
            "src.components.call_management.tata_tele.call_webhook.TalkoTataTeleWebhookHandler.process_cdr_api_payload",
            new=AsyncMock(return_value={"status": "success"}),
        ) as m:
            await h.process_cdr_api_payload({"callId": "C9"}, call_id="C9")
            sent = m.await_args.args[0]
            assert sent["call_id"] == "C9"


class TestGatewayOtoba:
    @pytest.mark.asyncio
    async def test_otoba_registered(self):
        from src.components.call_operation.vendor_cdr_gateway import TalkoVendorCDRGateway

        task = MagicMock()
        task.fetch_single_cdr = AsyncMock(return_value={"status": "success"})
        gw = TalkoVendorCDRGateway(cdr_update_task=task, logger=MagicMock())
        assert "otoba" in gw._handlers
        out = await gw.fetch_call_details(
            call_id="O1",
            call_uuid=None,
            vendor_config={
                "vendor_type": "otoba",
                "cdr_url_handler": {"endpoint": "https://otoba/cdr"},
            },
        )
        assert out["status"] == "success"
        task.fetch_single_cdr.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_selection(self):
        from src.components.call_operation.cdr_update import TalkoCDRUpdateTask

        task = TalkoCDRUpdateTask(
            cdr_repository=MagicMock(),
            vendor_config_repository=MagicMock(),
            call_repository=MagicMock(),
            logger=MagicMock(),
        )
        h = task._build_cdr_handler("otoba", {})
        assert isinstance(h, TalkoOtobaWebhookHandler)
        h2 = task._build_cdr_handler("tata_tele", {})
        from src.components.call_management.tata_tele.call_webhook import (
            TalkoTataTeleWebhookHandler,
        )

        assert type(h2) is TalkoTataTeleWebhookHandler
