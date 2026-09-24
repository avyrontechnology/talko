from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.call_management.supervision import TalkoSupervisionService
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v

    async def delete(self, k):
        self.store.pop(k, None)


def _svc():
    return TalkoSupervisionService(logger=MagicMock(), event_publisher=None)


class TestSupervise:
    @pytest.mark.asyncio
    async def test_start_ok(self):
        fake = FakeRedis()
        with patch(
            "src.components.call_management.supervision.get_redis_client",
            return_value=fake,
        ):
            svc = _svc()
            out = await svc.start_supervise("C1", 7, "sup1", "whisper", "roomA")
            assert out["mode"] == "whisper"
            assert out["status"] == "active"

    @pytest.mark.asyncio
    async def test_bad_mode(self):
        with patch(
            "src.components.call_management.supervision.get_redis_client",
            return_value=FakeRedis(),
        ):
            with pytest.raises(TalkoBadRequestError):
                await _svc().start_supervise("C1", 7, "sup1", "shout")

    @pytest.mark.asyncio
    async def test_double_start_rejected(self):
        fake = FakeRedis()
        with patch(
            "src.components.call_management.supervision.get_redis_client",
            return_value=fake,
        ):
            svc = _svc()
            await svc.start_supervise("C1", 7, "sup1", "listen")
            with pytest.raises(TalkoBadRequestError):
                await svc.start_supervise("C1", 7, "sup2", "barge")

    @pytest.mark.asyncio
    async def test_stop_roundtrip(self):
        fake = FakeRedis()
        with patch(
            "src.components.call_management.supervision.get_redis_client",
            return_value=fake,
        ):
            svc = _svc()
            await svc.start_supervise("C1", 7, "sup1", "barge")
            out = await svc.stop_supervise("C1", 7)
            assert out["status"] == "ended"
            assert await svc.get_supervise("C1") is None

    @pytest.mark.asyncio
    async def test_stop_missing(self):
        with patch(
            "src.components.call_management.supervision.get_redis_client",
            return_value=FakeRedis(),
        ):
            with pytest.raises(TalkoResourceNotFound):
                await _svc().stop_supervise("NOPE")

    @pytest.mark.asyncio
    async def test_invite_published(self):
        fake = FakeRedis()
        pub = MagicMock()
        pub.publish_supervisor_event = AsyncMock()
        with patch(
            "src.components.call_management.supervision.get_redis_client",
            return_value=fake,
        ):
            svc = TalkoSupervisionService(logger=MagicMock(), event_publisher=pub)
            await svc.start_supervise("C1", 7, "sup1", "listen", "roomA")
            pub.publish_supervisor_event.assert_awaited_once()
            kwargs = pub.publish_supervisor_event.await_args.kwargs
            assert kwargs["event"] == "supervisor_invite"
            assert kwargs["room_name"] == "roomA"


class TestAttended:
    @pytest.mark.asyncio
    async def test_stage_and_complete(self):
        fake = FakeRedis()
        with patch(
            "src.components.call_management.supervision.get_redis_client",
            return_value=fake,
        ):
            svc = _svc()
            staged = await svc.start_attended("C1", 7, "999")
            assert staged["status"] == "consult"
            done = await svc.complete_attended("C1", 7)
            assert done["status"] == "completed"
            assert done["target_number"] == "999"

    @pytest.mark.asyncio
    async def test_complete_missing(self):
        with patch(
            "src.components.call_management.supervision.get_redis_client",
            return_value=FakeRedis(),
        ):
            with pytest.raises(TalkoResourceNotFound):
                await _svc().complete_attended("NOPE")

    @pytest.mark.asyncio
    async def test_double_stage_rejected(self):
        fake = FakeRedis()
        with patch(
            "src.components.call_management.supervision.get_redis_client",
            return_value=fake,
        ):
            svc = _svc()
            await svc.start_attended("C1", 7, "111")
            with pytest.raises(TalkoBadRequestError):
                await svc.start_attended("C1", 7, "222")
