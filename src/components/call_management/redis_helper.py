import asyncio
import json
import time
import traceback
from typing import Any, Dict, Optional

from redis import asyncio as aioredis

from src.components.cache.redis_client import get_redis_client
from src.core.redis import RedisCache
from src.core.redis_constants import (
    PENDING_CALL_CONTEXT_KEY,
    PENDING_CALL_CONTEXT_TTL_SECONDS,
)
from src.loggers.holler_service_logger import HollerServiceLogger

PENDING_CTX_TTL = PENDING_CALL_CONTEXT_TTL_SECONDS
PREFIX = RedisCache.KeysPrefix.HOLLER.value

# Guards to_num_idx / outbound_room writes against out-of-order background
# tasks: a call's context is only written by whichever caller passes the
# highest `created_at`, so a slow/retrying older call can never clobber a
# newer call's context for the same to_number. Both value shapes carry a
# top-level "created_at" field, so one script covers both key types.
_SET_IF_NEWER_SCRIPT = """
local key = KEYS[1]
local new_value = ARGV[1]
local new_created_at = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

local current = redis.call('GET', key)
if current then
    local ok, decoded = pcall(cjson.decode, current)
    if ok and decoded.created_at ~= nil then
        local cur_created_at = tonumber(decoded.created_at)
        if cur_created_at ~= nil and cur_created_at > new_created_at then
            return 0
        end
    end
end
redis.call('SET', key, new_value, 'EX', ttl)
return 1
"""

# Pre-created outbound room TTL: 5 minutes.
# If customer doesn't answer within 5 minutes the room expires automatically.
OUTBOUND_ROOM_TTL = 300


class CallRedisHelper:
    def __init__(self, logger: HollerServiceLogger) -> None:
        self.__logger = logger
        self.__redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        # Now returns the singleton pool — no new connection per call
        if self.__redis is None:
            self.__redis = await get_redis_client()
            self.__logger.info("[CallRedisHelper] Redis pool acquired")
        return self.__redis

    def _ctx_key(self, call_id: str) -> str:
        return "{}{}".format(PREFIX, PENDING_CALL_CONTEXT_KEY.format(call_id=call_id))

    def _idx_key(self, to_number: str) -> str:
        return "{}to_num_idx:{}".format(PREFIX, to_number)

    def _missed_callback_lock_key(self, call_uuid: str) -> str:
        return "{}missed_callback_lock:{}".format(PREFIX, call_uuid)

    def _missed_callback_exec_lock_key(self, call_uuid: str) -> str:
        return "{}missed_callback_exec:{}".format(PREFIX, call_uuid)

    async def try_acquire_missed_callback_lock(
        self, call_uuid: str, ttl: int = 120
    ) -> bool:
        """
        Best-effort dedup guard for the missed-inbound-call auto-callback flow.

        Returns True the first time it's called for a given call_uuid (lock
        acquired), False on every subsequent call within ttl seconds — so a
        duplicate Tata webhook delivery for the same missed call can't enqueue
        the callback task twice. ttl comfortably exceeds the 100s scheduling
        delay so the lock is still held when the task actually runs.
        """
        try:
            redis = await self._get_redis()
            key = self._missed_callback_lock_key(call_uuid)
            acquired = await redis.set(key, "1", nx=True, ex=ttl)
            return bool(acquired)
        except Exception as e:
            self.__logger.error(
                "[CallRedisHelper][MISSED_CALLBACK_LOCK] ❌ call_uuid={} error={}".format(
                    call_uuid, e
                )
            )
            # Fail open: if Redis is unavailable, don't silently drop the
            # callback — worst case is one duplicate callback, not zero.
            return True

    async def try_acquire_missed_callback_exec_lock(
        self, call_uuid: str, ttl: int = 600
    ) -> bool:
        """
        Exactly-once guard for callback *execution* (distinct from the
        short-lived scheduling lock above).

        The ETA task, the beat sweeper, and manual re-dispatches can all
        reach execution for the same call_uuid. Whichever execution acquires
        this lock first places the call; losers return "duplicate_suppressed".
        Paired with the callback-CDR existence check (which covers the case
        where the winner already finished and released nothing — locks
        expire, CDR rows don't).
        """
        try:
            redis = await self._get_redis()
            key = self._missed_callback_exec_lock_key(call_uuid)
            acquired = await redis.set(key, "1", nx=True, ex=ttl)
            return bool(acquired)
        except Exception as e:
            self.__logger.error(
                "[CallRedisHelper][MISSED_CALLBACK_EXEC] ❌ call_uuid={} error={}".format(
                    call_uuid, e
                )
            )
            # Fail open, same rationale as the scheduling lock.
            return True

    async def is_missed_callback_exec_locked(self, call_uuid: str) -> bool:
        """True if a callback execution for call_uuid is currently in flight."""
        try:
            redis = await self._get_redis()
            return bool(
                await redis.get(self._missed_callback_exec_lock_key(call_uuid))
            )
        except Exception as e:
            self.__logger.error(
                "[CallRedisHelper][MISSED_CALLBACK_EXEC] ❌ check call_uuid={} "
                "error={}".format(call_uuid, e)
            )
            # Fail closed here (treat as locked): the sweeper skips and
            # retries next run rather than risk a double-dial when Redis
            # state is unreadable.
            return True

    # ── NEW: outbound pre-session key ─────────────────────────────────────────
    def _outbound_room_key(self, to_number: str) -> str:
        """
        Redis key for a pre-created makun-ai room for an outbound call.
        Keyed by to_number (digits only, no leading +) so holler-service
        can find it when the Tata WebSocket start event arrives.
        """
        return "{}outbound_room:{}".format(PREFIX, to_number)

    # ─────────────────────────────────────────────────────────────────────────

    async def store_pending_call_context(
        self, call_id: str, payload: Dict[str, Any]
    ) -> None:
        try:
            redis = await self._get_redis()
            key = self._ctx_key(call_id)
            await redis.set(key, json.dumps(payload, default=str), ex=PENDING_CTX_TTL)
            self.__logger.info("[CallRedisHelper][STORE] ✅ key={}".format(key))
        except Exception as e:
            self.__logger.error(
                "[CallRedisHelper][STORE] ❌ error={} traceback={}".format(
                    e, traceback.format_exc()
                )
            )

    async def get_pending_call_context(self, call_id: str) -> Optional[Dict[str, Any]]:
        try:
            redis = await self._get_redis()
            key = self._ctx_key(call_id)
            raw = await redis.get(key)
            if raw is None:
                self.__logger.warning("[CallRedisHelper][GET] MISS key={}".format(key))
                return None
            self.__logger.info("[CallRedisHelper][GET] ✅ HIT key={}".format(key))
            return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except Exception as e:
            self.__logger.error("[CallRedisHelper][GET] ❌ error={}".format(e))
            return None

    async def delete_pending_call_context(self, call_id: str) -> None:
        try:
            redis = await self._get_redis()
            key = self._ctx_key(call_id)
            await redis.delete(key)
            self.__logger.info("[CallRedisHelper][DELETE] key={}".format(key))
        except Exception as e:
            self.__logger.error("[CallRedisHelper][DELETE] ❌ error={}".format(e))

    async def _set_if_newer(
        self, key: str, value: Dict[str, Any], created_at: float, ttl: int
    ) -> bool:
        """
        Atomically SET key only if no existing entry has a newer created_at.
        Prevents a slow/out-of-order background write (e.g. a retried call's
        _pre_create_session finishing late) from clobbering a fresher entry
        for the same to_number-scoped key.
        """
        redis = await self._get_redis()
        applied = await redis.eval(
            _SET_IF_NEWER_SCRIPT,
            1,
            key,
            json.dumps(value, default=str),
            created_at,
            ttl,
        )
        return bool(applied)

    def _decode_idx_value(self, raw: Any) -> Optional[str]:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        try:
            decoded = json.loads(text)
            return decoded.get("store_key")
        except (json.JSONDecodeError, TypeError, AttributeError):
            # Legacy plain-string index value (pre set-if-newer rollout).
            return text

    async def store_to_number_index(
        self, to_number: str, store_key: str, created_at: Optional[float] = None
    ) -> None:
        try:
            key = self._idx_key(to_number)
            effective_created_at = (
                created_at if created_at is not None else time.time() * 1000
            )
            applied = await self._set_if_newer(
                key,
                {"store_key": store_key, "created_at": effective_created_at},
                effective_created_at,
                PENDING_CTX_TTL,
            )
            if applied:
                self.__logger.info(
                    "[CallRedisHelper][IDX][STORE] to_number={} store_key={}".format(
                        to_number, store_key
                    )
                )
            else:
                self.__logger.warning(
                    "[CallRedisHelper][IDX][STORE] ⏭️ skipped stale write "
                    "to_number={} store_key={} — newer context already stored".format(
                        to_number, store_key
                    )
                )
        except Exception as e:
            self.__logger.error("[CallRedisHelper][IDX][STORE] ❌ error={}".format(e))

    async def get_store_key_by_to_number(self, to_number: str) -> Optional[str]:
        try:
            redis = await self._get_redis()
            key = self._idx_key(to_number)
            raw = await redis.get(key)
            if raw is None:
                self.__logger.warning(
                    "[CallRedisHelper][IDX][GET] MISS to_number={}".format(to_number)
                )
                return None
            result = self._decode_idx_value(raw)
            self.__logger.info(
                "[CallRedisHelper][IDX][GET] HIT to_number={} store_key={}".format(
                    to_number, result
                )
            )
            return result
        except Exception as e:
            self.__logger.error("[CallRedisHelper][IDX][GET] ❌ error={}".format(e))
            return None

    async def delete_to_number_index(self, to_number: str) -> None:
        try:
            redis = await self._get_redis()
            key = self._idx_key(to_number)
            await redis.delete(key)
            self.__logger.info(
                "[CallRedisHelper][IDX][DELETE] to_number={}".format(to_number)
            )
        except Exception as e:
            self.__logger.error("[CallRedisHelper][IDX][DELETE] ❌ error={}".format(e))

    async def fetch_and_delete_context(
        self, to_number: str
    ) -> Optional[Dict[str, Any]]:
        """
        Optimised single-method replacement for the 4-call sequence:
            get_store_key_by_to_number → get_pending_call_context
            → delete_pending_call_context → delete_to_number_index

        Uses a Redis pipeline to collapse GET context + DELETE both keys
        into one round trip after the initial index GET.

        Called by PSTNBridgeService._attach_pending_context().
        """
        try:
            redis = await self._get_redis()

            # Round trip 1: get the index key
            idx_key = self._idx_key(to_number)
            store_key_raw = await redis.get(idx_key)

            if store_key_raw is None:
                self.__logger.warning(
                    "[CallRedisHelper][FETCH_DEL] MISS idx to_number={}".format(
                        to_number
                    )
                )
                return None

            store_key = self._decode_idx_value(store_key_raw)
            if not store_key:
                self.__logger.warning(
                    "[CallRedisHelper][FETCH_DEL] ❌ malformed idx value "
                    "to_number={}".format(to_number)
                )
                return None
            ctx_key = self._ctx_key(store_key)

            # Round trip 2: pipeline GET context + DELETE both keys atomically
            pipe = redis.pipeline(transaction=False)
            pipe.get(ctx_key)
            pipe.delete(ctx_key)
            pipe.delete(idx_key)
            results = await pipe.execute()

            raw_context = results[0]
            if raw_context is None:
                self.__logger.warning(
                    "[CallRedisHelper][FETCH_DEL] MISS ctx store_key={}".format(
                        store_key
                    )
                )
                return None

            self.__logger.info(
                "[CallRedisHelper][FETCH_DEL] ✅ HIT store_key={}".format(store_key)
            )
            return json.loads(
                raw_context.decode("utf-8")
                if isinstance(raw_context, bytes)
                else raw_context
            )

        except Exception as e:
            self.__logger.error(
                "[CallRedisHelper][FETCH_DEL] ❌ error={} traceback={}".format(
                    e, traceback.format_exc()
                )
            )
            return None

    # ── NEW: outbound pre-session store / fetch ───────────────────────────────

    async def store_outbound_room(
        self, to_number: str, payload: Dict[str, Any]
    ) -> None:
        """
        Store a pre-created makun-ai room so handle_call() can consume it
        when the customer answers the outbound call.

        payload must contain:
            room_name    str   LiveKit room name
            caller_token str   LiveKit token for holler-service to join
            livekit_url  str   LiveKit server URL
            agent_id     int   makun-ai agent id (for logging)
            created_at   float time.time() when stored

        Key expires after OUTBOUND_ROOM_TTL (5 min). If the customer never
        answers, Redis cleans up automatically — no manual delete needed.

        Guarded with set-if-newer: if a second call to the same to_number
        was placed after this one and already stored its room, this write
        is skipped rather than overwriting the newer (correct) room.
        """
        try:
            key = self._outbound_room_key(to_number)
            created_at = payload.get("created_at", time.time())
            applied = await self._set_if_newer(
                key, payload, created_at, OUTBOUND_ROOM_TTL
            )
            if applied:
                self.__logger.info(
                    "[CallRedisHelper][OUTBOUND_ROOM][STORE] ✅ to_number={} "
                    "room={} ex={}s".format(
                        to_number, payload.get("room_name"), OUTBOUND_ROOM_TTL
                    )
                )
            else:
                self.__logger.warning(
                    "[CallRedisHelper][OUTBOUND_ROOM][STORE] ⏭️ skipped stale "
                    "write to_number={} room={} — newer room already stored".format(
                        to_number, payload.get("room_name")
                    )
                )
        except Exception as e:
            self.__logger.error(
                "[CallRedisHelper][OUTBOUND_ROOM][STORE] ❌ to_number={} "
                "error={} traceback={}".format(to_number, e, traceback.format_exc())
            )
            raise  # caller (_pre_create_session) must know it failed

    async def fetch_and_delete_outbound_room_with_retry(
        self, to_number: str, timeout: float = 0.4, interval: float = 0.05
    ) -> Optional[Dict[str, Any]]:
        """
        Like fetch_and_delete_outbound_room, but polls for up to `timeout`
        seconds instead of checking once.

        _pre_create_session only starts (DID lookup + possible gRPC + a
        makun-ai HTTP POST) after the vendor call has already been placed —
        there is no guarantee it finishes storing the room before Tata's
        WebSocket start event arrives. A single-shot GETDEL loses that race
        on any call where dial-to-answer is faster than the pre-warm chain,
        even though the room shows up in Redis moments later. This narrows
        the miss window instead of falling back on the first check.
        """
        deadline = time.monotonic() + timeout
        while True:
            room = await self.fetch_and_delete_outbound_room(to_number)
            if room is not None:
                return room
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(interval)

    async def fetch_and_delete_outbound_room(
        self, to_number: str
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically GET + DELETE the pre-created room for to_number.

        Uses GETDEL so there is no race condition between two concurrent
        WebSocket start events for the same number (shouldn't happen but
        defensive).

        Returns the room payload dict or None if not found / already consumed
        / expired.
        """
        try:
            redis = await self._get_redis()
            key = self._outbound_room_key(to_number)

            # GETDEL is atomic: fetches and removes in one round trip
            raw = await redis.getdel(key)

            if raw is None:
                self.__logger.info(
                    "[CallRedisHelper][OUTBOUND_ROOM][FETCH] MISS to_number={}".format(
                        to_number
                    )
                )
                return None

            payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            age = time.time() - payload.get("created_at", time.time())
            self.__logger.info(
                "[CallRedisHelper][OUTBOUND_ROOM][FETCH] ✅ HIT to_number={} "
                "room={} age={:.1f}s".format(to_number, payload.get("room_name"), age)
            )
            return payload

        except json.JSONDecodeError as e:
            self.__logger.error(
                "[CallRedisHelper][OUTBOUND_ROOM][FETCH] ❌ JSON decode error "
                "to_number={} error={}".format(to_number, e)
            )
            return None
        except Exception as e:
            self.__logger.error(
                "[CallRedisHelper][OUTBOUND_ROOM][FETCH] ❌ to_number={} "
                "error={} traceback={}".format(to_number, e, traceback.format_exc())
            )
            return None

    # ─────────────────────────────────────────────────────────────────────────
