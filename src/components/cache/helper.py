import json
from typing import Any

from redis import asyncio as aioredis

from src.core.redis import TalkoRedisCache
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoCacheHelper:
    def __init__(
        self,
        redis_pool: aioredis.Redis,
        talko_service_logger: TalkoServiceLogger,
    ):
        self._redis_pool = redis_pool
        self.__logger = talko_service_logger

    @property
    def redis(self) -> aioredis.Redis:
        return self._redis_pool

    async def set_cache(
        self,
        key: str,
        value: Any,
        prefix: TalkoRedisCache.KeysPrefix = TalkoRedisCache.KeysPrefix.MAGLO,
        ttl: int | None = None,
    ) -> bool:
        try:
            serialized_value = json.dumps(
                value,
                default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o),
            )
            full_key = f"{prefix.value}{key}"
            await self._redis_pool.set(full_key, serialized_value, ex=ttl)
            self.__logger.info(f"Successfully set cache for key: {full_key}")
            return True
        except Exception as e:
            self.__logger.error(f"Error setting cache for key: {full_key}, error: {str(e)}")
            return False

    async def get_cache(
        self, key: str, prefix: TalkoRedisCache.KeysPrefix = TalkoRedisCache.KeysPrefix.MAGLO
    ) -> Any | None:
        try:
            full_key = f"{prefix.value}{key}"
            value = await self._redis_pool.get(full_key)
            if value is None:
                self.__logger.info(f"Cache miss for key: {full_key}")
                return None
            self.__logger.info(f"Cache hit for key: {full_key}")
            return json.loads(value.decode("utf-8"))
        except Exception as e:
            self.__logger.error(f"Error getting cache for key: {full_key}, error: {str(e)}")
            return None

    async def delete_cache(
        self, key: str, prefix: TalkoRedisCache.KeysPrefix = TalkoRedisCache.KeysPrefix.MAGLO
    ) -> bool:
        try:
            full_key = f"{prefix.value}{key}"
            result = bool(await self._redis_pool.delete(full_key))
            self.__logger.info(f"Successfully deleted cache for key: {full_key}")
            return result
        except Exception as e:
            self.__logger.error(f"Error deleting cache for key: {full_key}, error: {str(e)}")
            return False

    async def bulk_set_cache(
        self,
        data: dict[str, Any],
        prefix: TalkoRedisCache.KeysPrefix = TalkoRedisCache.KeysPrefix.MAGLO,
        ttl: int | None = None,
    ) -> bool:
        try:
            pipeline = self._redis_pool.pipeline()
            full_keys = []
            for key, value in data.items():
                serialized_value = json.dumps(
                    value,
                    default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o),
                )
                full_key = f"{prefix.value}{key}"
                full_keys.append(full_key)
                pipeline.set(full_key, serialized_value, ex=ttl)
            await pipeline.execute()
            self.__logger.info("Successfully bulk set cache for keys: {}".format(", ".join(full_keys)))
            return True
        except Exception as e:
            self.__logger.error("Error bulk setting cache for keys: {}, error: {}".format(", ".join(full_keys), str(e)))
            return False

    async def bulk_get_cache(
        self,
        keys: list[str],
        prefix: TalkoRedisCache.KeysPrefix = TalkoRedisCache.KeysPrefix.MAGLO,
    ) -> dict[str, Any]:
        try:
            full_keys = [f"{prefix.value}{key}" for key in keys]
            values = await self._redis_pool.mget(full_keys)
            result = {}
            for key, value in zip(keys, values, strict=True):
                if value is not None:
                    result[key] = json.loads(value.decode("utf-8"))
                    self.__logger.info("Cache hit for key: {}".format(f"{prefix.value}{key}"))
                else:
                    self.__logger.info("Cache miss for key: {}".format(f"{prefix.value}{key}"))
            return result
        except Exception as e:
            self.__logger.error("Error bulk getting cache for keys: {}, error: {}".format(", ".join(full_keys), str(e)))
            return {}

    async def bulk_delete_cache(
        self,
        keys: list[str],
        prefix: TalkoRedisCache.KeysPrefix = TalkoRedisCache.KeysPrefix.MAGLO,
    ) -> int:
        try:
            full_keys = [f"{prefix.value}{key}" for key in keys]
            await self._redis_pool.delete(*full_keys)
            self.__logger.info("Successfully bulk deleted cache for keys: {}".format(", ".join(full_keys)))
            return True
        except Exception as e:
            self.__logger.error(
                "Error bulk deleting cache for keys: {}, error: {}".format(", ".join(full_keys), str(e))
            )
            return False

    async def clear_pattern(
        self,
        prefix: TalkoRedisCache.KeysPrefix,
        pattern: str | list[str] | None = None,
    ) -> bool:
        try:
            patterns = [pattern] if isinstance(pattern, str) else (pattern or [""])
            all_keys = []
            for p in patterns:
                match_pattern = f"{prefix.value}{p}*"
                keys = await self._redis_pool.keys(match_pattern)
                all_keys.extend(keys)
                self.__logger.info(
                    "Found keys for pattern: {}, keys: {}".format(
                        match_pattern, ", ".join(key.decode("utf-8") for key in keys)
                    )
                )
            if all_keys:
                await self._redis_pool.delete(*all_keys)
                self.__logger.info(f"Successfully cleared cache for {len(all_keys)} keys across patterns")
            else:
                self.__logger.info(f"No keys found for any patterns with prefix: {prefix.value}")
            return True
        except Exception as e:
            self.__logger.error(f"Error clearing cache for prefix: {prefix.value}, error: {str(e)}")
            return False

    async def incr_with_ttl(
        self,
        key: str,
        ttl_seconds: int,
        prefix: TalkoRedisCache.KeysPrefix = TalkoRedisCache.KeysPrefix.CONSOLE,
    ) -> int | None:
        full_key = f"{prefix.value}{key}"
        try:
            pipe = self._redis_pool.pipeline()
            pipe.incr(full_key)
            pipe.expire(full_key, ttl_seconds)
            results = await pipe.execute()
            return int(results[0])
        except Exception as e:
            self.__logger.error(f"incr_with_ttl failed for key={full_key}, err={str(e)}")
            return None


class TalkoCentralizedCacheHelper(TalkoCacheHelper):
    def __init__(
        self,
        centralized_redis_pool: aioredis.Redis,
        talko_service_logger: TalkoServiceLogger,
    ):
        super().__init__(centralized_redis_pool, talko_service_logger)
