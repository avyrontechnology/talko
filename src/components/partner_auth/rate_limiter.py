import time

from src.components.cache.helper import TalkoCacheHelper
from src.components.partner_auth.constant import (
    RATE_LIMIT_MAX_REQUESTS_PER_WINDOW,
    RATE_LIMIT_WINDOW_SECONDS,
)
from src.core.redis import TalkoRedisCache
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoPartnerApiKeyRateLimiter:
    """Fixed-window per-partner rate limiter built on the existing atomic
    INCR+EXPIRE primitive — the only reusable rate-limit building block in
    the codebase. Fails open on Redis errors, consistent with
    TalkoCacheHelper.incr_with_ttl's own fail-safe behavior.
    """

    def __init__(self, cache_helper: TalkoCacheHelper, logger: TalkoServiceLogger):
        self.__cache_helper = cache_helper
        self.__logger = logger

    async def check(self, partner_id: int) -> bool:
        window = int(time.time()) // RATE_LIMIT_WINDOW_SECONDS
        key = "partner_rl:{}:{}".format(partner_id, window)
        count = await self.__cache_helper.incr_with_ttl(
            key,
            ttl_seconds=RATE_LIMIT_WINDOW_SECONDS,
            prefix=TalkoRedisCache.KeysPrefix.TALKO,
        )
        if count is None:
            self.__logger.error(
                "Rate limit check failed for partner_id {}; failing open".format(
                    partner_id
                )
            )
            return True
        return count <= RATE_LIMIT_MAX_REQUESTS_PER_WINDOW
