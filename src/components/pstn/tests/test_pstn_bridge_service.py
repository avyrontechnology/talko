import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.pstn.constants import CallDirection, PSTNProvider
from src.components.pstn.dto import CallContext
from src.components.pstn.services import PSTNBridgeService


def make_service(**overrides):
    """Helper to instantiate PSTNBridgeService with default AsyncMock dependencies."""
    defaults = dict(
        did_repository=AsyncMock(),
        logger=MagicMock(),
        http_client=AsyncMock(),
        call_redis_helper=AsyncMock(),
        call_repository=AsyncMock(),
    )
    defaults.update(overrides)
    return PSTNBridgeService(**defaults), defaults


def make_ctx(**overrides):
    defaults = dict(
        provider=PSTNProvider.TATA_TELE,
        call_sid="call-sid-1",
        did_number="917965802977",
        caller_number="+918103492952",
        direction=CallDirection.OUTBOUND,
        partner_id=113,
    )
    defaults.update(overrides)
    return CallContext(**defaults)


class TestBackfillRealVendorCallId:
    """
    Covers the best-effort second pass that resolves Tata's real vendor
    call_id (not just ctx.call_sid) via live_calls and republishes it over
    the LiveKit data channel, for the auto-hangup tool to consume.
    """

    @pytest.mark.asyncio
    async def test_resolves_and_publishes_real_call_id(self):
        service, deps = make_service()
        deps["call_repository"].get_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": "vendor-1", "vendor_config_id": "config-1"}
        )
        deps["call_repository"].get_vendor_config = AsyncMock(
            return_value={"vendor_type": "tata_tele"}
        )

        room = MagicMock()
        room.name = "call-abc"
        room.local_participant.publish_data = AsyncMock()

        ctx = make_ctx()

        mock_handler = AsyncMock()
        mock_handler.find_live_call_id = AsyncMock(return_value="CAXX-real-123")

        with patch(
            "src.components.pstn.services.TataTeleCallHandler",
            return_value=mock_handler,
        ):
            await service._backfill_real_vendor_call_id(ctx, room)

        mock_handler.find_live_call_id.assert_awaited_once_with(
            did_number="917965802977", customer_number="+918103492952"
        )
        room.local_participant.publish_data.assert_awaited_once()
        _, kwargs = room.local_participant.publish_data.call_args
        sent = json.loads(kwargs["payload"].decode("utf-8"))
        assert sent == {"type": "call_id", "call_id": "CAXX-real-123"}
        assert kwargs["reliable"] is True

    @pytest.mark.asyncio
    async def test_prefers_ai_vendor_config_id_over_vendor_config_id(self):
        service, deps = make_service()
        deps["call_repository"].get_partner_config_by_partner_id = AsyncMock(
            return_value={
                "vendor_id": "vendor-1",
                "vendor_config_id": "config-1",
                "ai_vendor_config_id": "ai-config-1",
            }
        )
        deps["call_repository"].get_vendor_config = AsyncMock(
            return_value={"vendor_type": "tata_tele"}
        )

        room = MagicMock()
        room.local_participant.publish_data = AsyncMock()

        mock_handler = AsyncMock()
        mock_handler.find_live_call_id = AsyncMock(return_value="CAXX-real-123")

        with patch(
            "src.components.pstn.services.TataTeleCallHandler",
            return_value=mock_handler,
        ):
            await service._backfill_real_vendor_call_id(make_ctx(), room)

        deps["call_repository"].get_vendor_config.assert_awaited_once_with(
            "vendor-1", "ai-config-1"
        )

    @pytest.mark.asyncio
    async def test_no_partner_config_skips_publish(self):
        service, deps = make_service()
        deps["call_repository"].get_partner_config_by_partner_id = AsyncMock(
            return_value=None
        )
        room = MagicMock()
        room.local_participant.publish_data = AsyncMock()

        await service._backfill_real_vendor_call_id(make_ctx(), room)

        room.local_participant.publish_data.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_vendor_ids_skips_publish(self):
        service, deps = make_service()
        deps["call_repository"].get_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": None, "vendor_config_id": "config-1"}
        )
        room = MagicMock()
        room.local_participant.publish_data = AsyncMock()

        await service._backfill_real_vendor_call_id(make_ctx(), room)

        room.local_participant.publish_data.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_vendor_config_skips_publish(self):
        service, deps = make_service()
        deps["call_repository"].get_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": "vendor-1", "vendor_config_id": "config-1"}
        )
        deps["call_repository"].get_vendor_config = AsyncMock(return_value=None)
        room = MagicMock()
        room.local_participant.publish_data = AsyncMock()

        await service._backfill_real_vendor_call_id(make_ctx(), room)

        room.local_participant.publish_data.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unresolved_call_id_skips_publish(self):
        service, deps = make_service()
        deps["call_repository"].get_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": "vendor-1", "vendor_config_id": "config-1"}
        )
        deps["call_repository"].get_vendor_config = AsyncMock(
            return_value={"vendor_type": "tata_tele"}
        )
        room = MagicMock()
        room.local_participant.publish_data = AsyncMock()

        mock_handler = AsyncMock()
        mock_handler.find_live_call_id = AsyncMock(return_value=None)

        with patch(
            "src.components.pstn.services.TataTeleCallHandler",
            return_value=mock_handler,
        ):
            await service._backfill_real_vendor_call_id(make_ctx(), room)

        room.local_participant.publish_data.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unresolved_call_id_still_updates_cdr_via_ctx_call_sid(self):
        """The exact case hit live: find_live_call_id comes back empty (call
        already progressed past ringing, or the poll window missed it). The
        CDR must still get updated — using ctx.call_sid, itself a genuine
        Tata call identifier (parsed off the WS start event) — rather than
        being left with call_id="" forever just because this one poll missed."""
        service, deps = make_service()
        deps["call_repository"].get_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": "vendor-1", "vendor_config_id": "config-1"}
        )
        deps["call_repository"].get_vendor_config = AsyncMock(
            return_value={"vendor_type": "tata_tele"}
        )
        deps["call_repository"].update_cdr = AsyncMock(return_value=True)

        room = MagicMock()
        room.local_participant.publish_data = AsyncMock()

        ctx = make_ctx(context_data={"cdr_id": "cdr-abc-123"})

        mock_handler = AsyncMock()
        mock_handler.find_live_call_id = AsyncMock(return_value=None)

        with patch(
            "src.components.pstn.services.TataTeleCallHandler",
            return_value=mock_handler,
        ):
            await service._backfill_real_vendor_call_id(ctx, room)

        room.local_participant.publish_data.assert_not_awaited()
        deps["call_repository"].update_cdr.assert_awaited_once_with(
            "cdr-abc-123", {"call_id": ctx.call_sid}
        )

    @pytest.mark.asyncio
    async def test_updates_original_cdr_when_cdr_id_present(self):
        """cdr_id rides along in ctx.context_data (see CallService's
        _pre_create_session Step 4 / initiate_call's pending_context_payload)
        — once the real call_id resolves, the original CDR row (inserted at
        initiate_call time with call_id="") must be updated in place so
        Tata's later webhook can match it via get_cdr_by_call_id_or_uuid."""
        service, deps = make_service()
        deps["call_repository"].get_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": "vendor-1", "vendor_config_id": "config-1"}
        )
        deps["call_repository"].get_vendor_config = AsyncMock(
            return_value={"vendor_type": "tata_tele"}
        )
        deps["call_repository"].update_cdr = AsyncMock(return_value=True)

        room = MagicMock()
        room.local_participant.publish_data = AsyncMock()

        ctx = make_ctx(context_data={"cdr_id": "cdr-abc-123", "campaign_id": "7"})

        mock_handler = AsyncMock()
        mock_handler.find_live_call_id = AsyncMock(return_value="CAXX-real-123")

        with patch(
            "src.components.pstn.services.TataTeleCallHandler",
            return_value=mock_handler,
        ):
            await service._backfill_real_vendor_call_id(ctx, room)

        deps["call_repository"].update_cdr.assert_awaited_once_with(
            "cdr-abc-123", {"call_id": "CAXX-real-123"}
        )

    @pytest.mark.asyncio
    async def test_skips_cdr_update_when_no_cdr_id_in_context(self):
        service, deps = make_service()
        deps["call_repository"].get_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": "vendor-1", "vendor_config_id": "config-1"}
        )
        deps["call_repository"].get_vendor_config = AsyncMock(
            return_value={"vendor_type": "tata_tele"}
        )
        deps["call_repository"].update_cdr = AsyncMock()

        room = MagicMock()
        room.local_participant.publish_data = AsyncMock()

        mock_handler = AsyncMock()
        mock_handler.find_live_call_id = AsyncMock(return_value="CAXX-real-123")

        with patch(
            "src.components.pstn.services.TataTeleCallHandler",
            return_value=mock_handler,
        ):
            await service._backfill_real_vendor_call_id(make_ctx(), room)

        deps["call_repository"].update_cdr.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cdr_update_failure_is_swallowed(self):
        """Best-effort — a failed CDR update must not prevent the call_id
        publish from having already succeeded, nor raise."""
        service, deps = make_service()
        deps["call_repository"].get_partner_config_by_partner_id = AsyncMock(
            return_value={"vendor_id": "vendor-1", "vendor_config_id": "config-1"}
        )
        deps["call_repository"].get_vendor_config = AsyncMock(
            return_value={"vendor_type": "tata_tele"}
        )
        deps["call_repository"].update_cdr = AsyncMock(
            side_effect=RuntimeError("mongo down")
        )

        room = MagicMock()
        room.local_participant.publish_data = AsyncMock()

        ctx = make_ctx(context_data={"cdr_id": "cdr-abc-123"})

        mock_handler = AsyncMock()
        mock_handler.find_live_call_id = AsyncMock(return_value="CAXX-real-123")

        with patch(
            "src.components.pstn.services.TataTeleCallHandler",
            return_value=mock_handler,
        ):
            await service._backfill_real_vendor_call_id(ctx, room)

        room.local_participant.publish_data.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_repository_exception_is_swallowed(self):
        service, deps = make_service()
        deps["call_repository"].get_partner_config_by_partner_id = AsyncMock(
            side_effect=RuntimeError("db down")
        )
        room = MagicMock()
        room.local_participant.publish_data = AsyncMock()

        # Must never raise — this is a best-effort background task.
        await service._backfill_real_vendor_call_id(make_ctx(), room)

        room.local_participant.publish_data.assert_not_awaited()
