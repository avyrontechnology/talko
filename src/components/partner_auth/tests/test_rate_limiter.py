from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.partner_auth.constant import RATE_LIMIT_MAX_REQUESTS_PER_WINDOW
from src.components.partner_auth.rate_limiter import TalkoPartnerApiKeyRateLimiter


@pytest.mark.asyncio
class TestPartnerApiKeyRateLimiter:
    @pytest.fixture
    def limiter(self):
        cache_helper = AsyncMock()
        return TalkoPartnerApiKeyRateLimiter(cache_helper=cache_helper, logger=MagicMock())

    async def test_under_limit_allows(self, limiter):
        limiter._TalkoPartnerApiKeyRateLimiter__cache_helper.incr_with_ttl.return_value = 1
        assert await limiter.check(partner_id=1) is True

    async def test_at_limit_allows(self, limiter):
        limiter._TalkoPartnerApiKeyRateLimiter__cache_helper.incr_with_ttl.return_value = (
            RATE_LIMIT_MAX_REQUESTS_PER_WINDOW
        )
        assert await limiter.check(partner_id=1) is True

    async def test_over_limit_rejects(self, limiter):
        limiter._TalkoPartnerApiKeyRateLimiter__cache_helper.incr_with_ttl.return_value = (
            RATE_LIMIT_MAX_REQUESTS_PER_WINDOW + 1
        )
        assert await limiter.check(partner_id=1) is False

    async def test_redis_error_fails_open(self, limiter):
        limiter._TalkoPartnerApiKeyRateLimiter__cache_helper.incr_with_ttl.return_value = None
        assert await limiter.check(partner_id=1) is True
