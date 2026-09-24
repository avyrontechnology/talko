from unittest.mock import AsyncMock, Mock, patch

import pytest
from bson import ObjectId

from src.components.call_management.channel_pool import (
    TalkoChannelPoolExhausted,
    TalkoChannelPoolService,
)
from src.exceptions import TalkoBadRequestError


def _svc(max_channels=None, in_use=0):
    repo = AsyncMock()
    repo.find_config_by_id = AsyncMock(
        return_value={
            "_id": ObjectId(),
            "channel_pool": {"max_channels": max_channels, "reserved_channels": 0},
        }
    )
    repo.update_vendor_config = AsyncMock(
        return_value={"channel_pool": {"max_channels": max_channels, "reserved_channels": 0}}
    )
    logger = Mock()
    svc = TalkoChannelPoolService(vendor_config_repository=repo, logger=logger)
    return svc, repo


class FakeRedis:
    def __init__(self, val=0):
        self.val = val

    async def incr(self, _k):
        self.val += 1
        return self.val

    async def decr(self, _k):
        self.val -= 1
        return self.val

    async def get(self, _k):
        return str(self.val)

    async def set(self, _k, v):
        self.val = int(v)


class TestAcquire:
    @pytest.mark.asyncio
    async def test_unlimited_always_acquires(self):
        svc, _ = _svc(max_channels=None)
        out = await svc.acquire(str(ObjectId()))
        assert out["limited"] is False

    @pytest.mark.asyncio
    async def test_acquire_within_limit(self):
        svc, _ = _svc(max_channels=2)
        fake = FakeRedis(0)
        with patch(
            "src.components.call_management.channel_pool.get_redis_client",
            return_value=fake,
        ):
            out = await svc.acquire(str(ObjectId()))
            assert out["in_use"] == 1

    @pytest.mark.asyncio
    async def test_exhausted_raises_and_rolls_back(self):
        svc, _ = _svc(max_channels=1)
        fake = FakeRedis(1)  # next incr -> 2 > 1
        with patch(
            "src.components.call_management.channel_pool.get_redis_client",
            return_value=fake,
        ):
            with pytest.raises(TalkoChannelPoolExhausted):
                await svc.acquire(str(ObjectId()))
            assert fake.val == 1  # rolled back via decr

    @pytest.mark.asyncio
    async def test_release_clamps_at_zero(self):
        svc, _ = _svc(max_channels=1)
        fake = FakeRedis(0)
        fake.get = AsyncMock(return_value=None)
        with patch(
            "src.components.call_management.channel_pool.get_redis_client",
            return_value=fake,
        ):
            assert await svc.release(str(ObjectId())) == 0

    @pytest.mark.asyncio
    async def test_set_limits_validation(self):
        svc, _ = _svc(max_channels=5)
        with pytest.raises(TalkoBadRequestError):
            await svc.set_limits(str(ObjectId()), 0)
        with pytest.raises(TalkoBadRequestError):
            await svc.set_limits(str(ObjectId()), 2, reserved_channels=5)

    @pytest.mark.asyncio
    async def test_status_reports_available(self):
        svc, _ = _svc(max_channels=5)
        fake = FakeRedis(2)
        with patch(
            "src.components.call_management.channel_pool.get_redis_client",
            return_value=fake,
        ):
            st = await svc.get_status(str(ObjectId()))
            assert st["in_use"] == 2
            assert st["available"] == 3
