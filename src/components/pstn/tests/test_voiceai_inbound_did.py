from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.pstn.constants import TalkoCallDirection, TalkoPSTNProvider
from src.components.pstn.dto import TalkoCallContext
from src.components.pstn.services import TalkoPSTNBridgeService
from src.core.environment import TalkoENV


def make_service(**overrides):
    defaults = dict(
        did_repository=AsyncMock(),
        logger=MagicMock(),
        http_client=AsyncMock(),
        call_redis_helper=AsyncMock(),
        call_repository=AsyncMock(),
    )
    defaults.update(overrides)
    return TalkoPSTNBridgeService(**defaults), defaults


def ai_agent_did_record(**overrides):
    record = {
        "did_type": "ai_agent",
        "partner_id": 2,
        "vendor_config_id": "vc1",
        "agent_id": 0,
        "agent_bot_id": 0,
        "is_active": True,
    }
    record.update(overrides)
    return record


def make_ctx(**overrides):
    defaults = dict(
        provider=TalkoPSTNProvider.TATA_TELE,
        call_sid="CA1",
        did_number="+917965263087",
        caller_number="+9191",
        direction=TalkoCallDirection.INBOUND,
        stream_sid="MZ1",
    )
    defaults.update(overrides)
    return TalkoCallContext(**defaults)


class TestResolveDidVoiceaiMapped:
    @pytest.mark.asyncio
    async def test_ai_agent_without_bot_id_passes_when_mapped(self, monkeypatch):
        monkeypatch.setattr(
            TalkoENV, "VOICEAI_INBOUND_AGENT_MAP",
            '{"+917965263087": "agent_1"}', raising=False,
        )
        service, deps = make_service()
        deps["did_repository"].get_did_by_number = AsyncMock(
            return_value=ai_agent_did_record()
        )
        ctx = await service._resolve_did(make_ctx())
        assert ctx.partner_id == 2
        assert ctx.makunai_agent_id is None  # voiceai Step 4b resolves the agent

    @pytest.mark.asyncio
    async def test_plus_prefix_tolerated(self, monkeypatch):
        monkeypatch.setattr(
            TalkoENV, "VOICEAI_INBOUND_AGENT_MAP",
            '{"917965263087": "agent_9"}', raising=False,
        )
        service, deps = make_service()
        deps["did_repository"].get_did_by_number = AsyncMock(
            return_value=ai_agent_did_record()
        )
        ctx = await service._resolve_did(make_ctx(did_number="+917965263087"))
        assert ctx.partner_id == 2

    @pytest.mark.asyncio
    async def test_ai_agent_without_bot_id_still_raises_when_unmapped(self, monkeypatch):
        monkeypatch.setattr(TalkoENV, "VOICEAI_INBOUND_AGENT_MAP", "", raising=False)
        service, deps = make_service()
        deps["did_repository"].get_did_by_number = AsyncMock(
            return_value=ai_agent_did_record()
        )
        with pytest.raises(ValueError, match="agent_bot_id is missing"):
            await service._resolve_did(make_ctx())

    def test_resolve_by_did_map(self, monkeypatch):
        service, _ = make_service()
        monkeypatch.setattr(
            TalkoENV, "VOICEAI_INBOUND_AGENT_MAP",
            '{"917965263087": "agent_9"}', raising=False,
        )
        assert service._resolve_voiceai_agent_id_for_did("+917965263087") == "agent_9"
        assert service._resolve_voiceai_agent_id_for_did("910000000000") is None

    @pytest.mark.asyncio
    async def test_create_session_skipped_for_mapped_did(self, monkeypatch):
        monkeypatch.setattr(
            TalkoENV, "VOICEAI_INBOUND_AGENT_MAP",
            '{"+917965263087": "agent_1"}', raising=False,
        )
        service, _ = make_service()
        ctx = make_ctx(context_data=None)
        out = await service._create_session(ctx)
        assert out is ctx
        assert out.room_name is None  # no makun-ai room touched

    @pytest.mark.asyncio
    async def test_create_session_runs_makunai_when_unmapped(self, monkeypatch):
        monkeypatch.setattr(TalkoENV, "VOICEAI_INBOUND_AGENT_MAP", "", raising=False)
        service, _ = make_service()
        # Without mapping it proceeds to the makun-ai path, which fails here
        # on the (mocked) API-key resolve — proving no skip happened.
        service._resolve_partner_api_key = AsyncMock(side_effect=RuntimeError("grpc down"))
        with pytest.raises(RuntimeError, match="grpc down"):
            await service._create_session(make_ctx(context_data=None))
