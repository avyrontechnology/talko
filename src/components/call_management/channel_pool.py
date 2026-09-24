from typing import Any

from src.components.cache.redis_client import get_redis_client
from src.components.vendor_config.repository import TalkoVendorConfigRepository
from src.core.redis_constants import CHANNEL_POOL_INUSE_KEY
from src.exceptions import TalkoBadRequestError
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoChannelPoolExhausted(TalkoBadRequestError):
    """Raised when a vendor config has no free channel left."""

    def __init__(self, vendor_config_id: str, max_channels: int, in_use: int):
        super().__init__(f"No free channel for vendor_config {vendor_config_id} (in_use={in_use}/{max_channels})")
        self.vendor_config_id = vendor_config_id
        self.max_channels = max_channels
        self.in_use = in_use


class TalkoChannelPoolService:
    """Redis-backed concurrent-call counter per vendor_config.

    Limit lives in Mongo (vendor_config.channel_pool.max_channels, None =
    unlimited). Counter lives in Redis and must be acquire/release paired:
    acquire in initiate_call, release on initiate failure + hangup.
    """

    def __init__(
        self,
        vendor_config_repository: TalkoVendorConfigRepository,
        logger: TalkoServiceLogger,
    ) -> None:
        self.__vendor_config_repo = vendor_config_repository
        self.__logger = logger

    def _key(self, vendor_config_id: str) -> str:
        return CHANNEL_POOL_INUSE_KEY.format(vendor_config_id=vendor_config_id)

    async def _get_max(self, vendor_config_id: str) -> dict[str, Any] | None:
        from bson import ObjectId

        try:
            cfg_id = ObjectId(vendor_config_id)
        except Exception:
            return None
        cfg: dict[str, Any] | None = await self.__vendor_config_repo.find_config_by_id(cfg_id)
        if not cfg:
            return None
        pool = cfg.get("channel_pool") or {}
        max_channels = pool.get("max_channels")
        return {
            "max_channels": max_channels,
            "reserved_channels": pool.get("reserved_channels", 0),
        }

    async def acquire(self, vendor_config_id: str) -> dict[str, Any]:
        limits = await self._get_max(vendor_config_id)
        if not limits or limits.get("max_channels") is None:
            return {"limited": False, "in_use": 0, "max_channels": None}
        max_channels: int = int(limits["max_channels"])
        redis = await get_redis_client()
        in_use = int(await redis.incr(self._key(vendor_config_id)))
        if in_use > max_channels:
            await redis.decr(self._key(vendor_config_id))
            self.__logger.error(
                f"Channel pool exhausted vendor_config_id={vendor_config_id} in_use={in_use} max={max_channels}"
            )
            raise TalkoChannelPoolExhausted(vendor_config_id, max_channels, in_use - 1)
        return {"limited": True, "in_use": in_use, "max_channels": max_channels}

    async def release(self, vendor_config_id: str) -> int:
        redis = await get_redis_client()
        raw = await redis.get(self._key(vendor_config_id))
        if raw is None:
            return 0
        in_use = int(await redis.decr(self._key(vendor_config_id)))
        if in_use < 0:
            await redis.set(self._key(vendor_config_id), 0)
            return 0
        return in_use

    async def get_status(self, vendor_config_id: str) -> dict[str, Any]:
        limits = await self._get_max(vendor_config_id)
        max_channels = (limits or {}).get("max_channels")
        reserved = (limits or {}).get("reserved_channels", 0)
        redis = await get_redis_client()
        raw = await redis.get(self._key(vendor_config_id))
        in_use = int(raw) if raw is not None else 0
        available = (max_channels - in_use) if max_channels is not None else None
        return {
            "vendor_config_id": vendor_config_id,
            "max_channels": max_channels,
            "reserved_channels": reserved,
            "in_use": in_use,
            "available": available,
        }

    async def set_limits(
        self,
        vendor_config_id: str,
        max_channels: int | None,
        reserved_channels: int = 0,
    ) -> dict[str, Any]:
        from bson import ObjectId

        if max_channels is not None and max_channels < 1:
            raise TalkoBadRequestError("max_channels must be >= 1 or null")
        if reserved_channels < 0:
            raise TalkoBadRequestError("reserved_channels must be >= 0")
        if max_channels is not None and reserved_channels > max_channels:
            raise TalkoBadRequestError("reserved_channels cannot exceed max_channels")
        updated = await self.__vendor_config_repo.update_vendor_config(
            ObjectId(vendor_config_id),
            {
                "channel_pool": {
                    "max_channels": max_channels,
                    "reserved_channels": reserved_channels,
                }
            },
        )
        return {
            "vendor_config_id": vendor_config_id,
            "channel_pool": (updated or {}).get("channel_pool"),
        }
