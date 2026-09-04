import enum

from redis import asyncio

from src.core.environment import TalkoENV


class TalkoRedisCache:

    class KeysPrefix(enum.Enum):
        CONSOLE = "console:"
        USER_SERVICE = "user_service:"
        MAGLO = "maglo:"
        TALKO = "talko:"
        BABBLER = "babbler:"

    @staticmethod
    async def init_redis_pool(db_index: int = TalkoENV.CACHE_DB):
        url = "{protocol}://{username}:{password}@{host}:{port}/{db}".format(
            protocol=TalkoENV.CACHE_PROTOCOL,
            username=TalkoENV.CACHE_USERNAME,
            password=TalkoENV.CACHE_PASSWORD,
            host=TalkoENV.CACHE_HOST,
            port=TalkoENV.CACHE_PORT,
            db=db_index,
        )
        # health_check_interval pings idle connections periodically so this
        # client (and anything long-lived built on it, e.g. the inbound call
        # event broker's pub/sub subscribe connection) doesn't get silently
        # dropped by Redis's own idle-client timeout — see "Connection closed
        # by server" in TalkoInboundCallEventBroker's listener logs without this.
        pool = asyncio.from_url(url, health_check_interval=30)
        yield pool
        # close()/wait_closed() are the old standalone-aioredis API and don't
        # exist on redis-py's built-in asyncio client (this project's actual
        # dependency, imported above) — aclose() is the correct teardown here.
        await pool.aclose()
