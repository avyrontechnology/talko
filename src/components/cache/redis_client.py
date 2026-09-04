import asyncio
from typing import Optional

from redis import asyncio as aioredis

from src.core.environment import TalkoENV

# Singleton pool — created once, reused across all calls.
# The old implementation called aioredis.from_url() on every
# _get_redis() call, which created a new TCP connection each time.
# For PSTN calls this added 200-800ms on the first Redis op per call.
_redis_pool: Optional[aioredis.Redis] = None
_redis_pool_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _redis_pool_lock
    if _redis_pool_lock is None:
        _redis_pool_lock = asyncio.Lock()
    return _redis_pool_lock


async def get_redis_client() -> aioredis.Redis:
    global _redis_pool

    # Fast path — pool already created
    if _redis_pool is not None:
        return _redis_pool

    # Slow path — create once, protected against concurrent init
    async with _get_lock():
        if _redis_pool is not None:
            return _redis_pool

        url = "{protocol}://{username}:{password}@{host}:{port}/{db}".format(
            protocol=TalkoENV.CACHE_PROTOCOL,
            username=TalkoENV.CACHE_USERNAME,
            password=TalkoENV.CACHE_PASSWORD,
            host=TalkoENV.CACHE_HOST,
            port=TalkoENV.CACHE_PORT,
            db=TalkoENV.CACHE_DB,
        )
        _redis_pool = aioredis.from_url(
            url,
            max_connections=20,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
            health_check_interval=30,
            decode_responses=False,  # keep bytes — callers already handle decode
        )
        return _redis_pool
