from __future__ import annotations

import asyncio
import base64
import json
import time
import traceback
from typing import Any

import httpx
from livekit import rtc
from redis import asyncio as aioredis

from src.components.cache.redis_client import get_redis_client
from src.components.call_management.redis_helper import TalkoCallRedisHelper
from src.components.call_management.repository import TalkoCallRepository
from src.components.call_management.tata_tele.call_service import TalkoTataTeleCallHandler
from src.components.did_management.constants import TalkoDIDType
from src.components.did_management.repositories import TalkoDidRepository
from src.components.pstn.audio_bridge import TalkoAudioBridge  # noqa: F401 (re-export)
from src.components.pstn.dto import TalkoCallContext
from src.components.pstn.providers.base import TalkoAbstractPSTNProvider
from src.components.pstn.voiceai_relay import VOICEAI_AGENT_ID_KEY, TalkoVoiceaiRelay
from src.core.environment import TalkoENV
from src.core.redis_constants import (
    ACK_WAIT_SECONDS,
    API_KEY_CACHE_KEY,
    API_KEY_CACHE_TTL_SECONDS,
    CHUNK_SIZE,
    DID_CACHE_KEY,
    DID_CACHE_TTL_SECONDS,
    MAX_PENDING_MARKS,
    STREAM_CONTEXT_KEY,
    STREAM_CONTEXT_TTL_SECONDS,
    VOICEAI_DID_CACHE_KEY,
)
from src.exceptions import TalkoBadRequestError
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.mongo_utils import stringify_object_ids
from src.utils.phone_number_utils import normalize_phone_number

GREETING_PLAYED_KEY = "greeting_played:{call_sid}"
GREETING_PLAYED_TTL_SECONDS = 60 * 60  # generous upper bound on call duration

INBOUND_GREETING_DELAY_SECONDS = 2.2  # natural pause before inbound greeting starts

# httpx's default is 5s; makun-ai session creation (LLM/voice provisioning)
# can legitimately take longer under load, so it needs its own, longer budget
# rather than inheriting the shared client's default.
MAKUNAI_SESSION_TIMEOUT_SECONDS = 15.0


class TalkoPSTNBridgeService:
    def __init__(
        self,
        did_repository: TalkoDidRepository,
        logger: TalkoServiceLogger,
        http_client: httpx.AsyncClient,
        call_redis_helper: TalkoCallRedisHelper,
        call_repository: TalkoCallRepository,
    ) -> None:
        self.__did_repository = did_repository
        self.__logger = logger
        self.__http_client = http_client
        self.__call_redis_helper = call_redis_helper
        self.__call_repository = call_repository
        self.__redis: aioredis.Redis | None = None
        self.__logger.info(f"[TalkoPSTNBridgeService][INIT] call_redis_helper_id={id(call_redis_helper)}")

    async def _get_redis(self) -> aioredis.Redis:
        # Returns the singleton pool — no new connection per call
        if self.__redis is None:
            self.__redis = await get_redis_client()
            self.__logger.info("[TalkoPSTNBridgeService] Redis pool acquired")
        return self.__redis

    async def _get_cached_did(self, did_number: str) -> dict[str, Any] | None:
        key = DID_CACHE_KEY.format(did_number=did_number)
        try:
            redis = await self._get_redis()
            raw = await redis.get(key)
            if raw is not None:
                if isinstance(raw, bytes):
                    raw = raw.decode()
                self.__logger.debug(f"[PSTN][DID_CACHE][GET] HIT did_number={did_number}")
                return json.loads(raw)
            self.__logger.debug(f"[PSTN][DID_CACHE][GET] MISS did_number={did_number}")
        except Exception as exc:
            self.__logger.warning(f"[PSTN][DID_CACHE][GET] ERROR did={did_number} error={exc}")
        return None

    async def _set_cached_did(self, did_number: str, record: dict[str, Any], ttl: int | None = None) -> None:
        key = DID_CACHE_KEY.format(did_number=did_number)
        try:
            redis = await self._get_redis()
            serializable_record: dict[str, Any] = stringify_object_ids(record)
            await redis.set(key, json.dumps(serializable_record), ex=ttl or DID_CACHE_TTL_SECONDS)
            self.__logger.debug(f"[PSTN][DID_CACHE][SET] OK did_number={did_number}")
        except Exception as exc:
            self.__logger.warning(f"[PSTN][DID_CACHE][SET] ERROR did={did_number} error={exc}")

    async def _get_cached_api_key(self, partner_id: int) -> str | None:
        key = API_KEY_CACHE_KEY.format(partner_id=partner_id)
        try:
            redis = await self._get_redis()
            raw = await redis.get(key)
            if raw is not None:
                self.__logger.debug(f"[PSTN][API_KEY_CACHE][GET] HIT partner_id={partner_id}")
                return raw if isinstance(raw, str) else raw.decode()
            self.__logger.debug(f"[PSTN][API_KEY_CACHE][GET] MISS partner_id={partner_id}")
        except Exception as exc:
            self.__logger.warning(f"[PSTN][API_KEY_CACHE][GET] ERROR partner_id={partner_id} error={exc}")
        return None

    async def _set_cached_api_key(self, partner_id: int, api_key: str) -> None:
        key = API_KEY_CACHE_KEY.format(partner_id=partner_id)
        try:
            redis = await self._get_redis()
            await redis.set(key, api_key, ex=API_KEY_CACHE_TTL_SECONDS)
            self.__logger.debug(f"[PSTN][API_KEY_CACHE][SET] OK partner_id={partner_id}")
        except Exception as exc:
            self.__logger.warning(f"[PSTN][API_KEY_CACHE][SET] ERROR partner_id={partner_id} error={exc}")

    async def _set_stream_context(self, stream_sid: str, payload: dict[str, Any]) -> None:
        key = STREAM_CONTEXT_KEY.format(stream_sid=stream_sid)
        try:
            redis = await self._get_redis()
            await redis.set(key, json.dumps(payload), ex=STREAM_CONTEXT_TTL_SECONDS)
            self.__logger.info(f"[PSTN][STREAM_CTX][SET] OK stream_sid={stream_sid}")
        except Exception as exc:
            self.__logger.warning(f"[PSTN][STREAM_CTX][SET] ERROR stream_sid={stream_sid} error={exc}")

    async def _resolve_partner_api_key(self, partner_id: int) -> str:
        self.__logger.info(f"[PSTN][API_KEY] Resolving partner_id={partner_id}")
        cached = await self._get_cached_api_key(partner_id)
        if cached:
            self.__logger.info(f"[PSTN][API_KEY] Cache HIT partner_id={partner_id}")
            return cached
        self.__logger.info(f"[PSTN][API_KEY] Cache MISS fetching via gRPC partner_id={partner_id}")
        grpc_client = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.AUTH)
        if grpc_client is None:
            raise TalkoBadRequestError("Console API key unavailable — gRPC disabled and key not cached")
        api_key: str = await grpc_client.get_partner_api_key(partner_id)
        await self._set_cached_api_key(partner_id, api_key)
        return api_key

    async def _resolve_did(self, ctx: TalkoCallContext) -> TalkoCallContext:
        self.__logger.info(f"[PSTN][DID] Resolving did_number={ctx.did_number}")
        did_record = await self._get_cached_did(ctx.did_number)
        # Prefetched by the dynamic DB-miss branch below — reuse it in the
        # ai_agent branch so one inbound call pays one engine HTTP max.
        prefetched_voiceai_agent: str | None = None

        if did_record is None:
            self.__logger.info(f"[PSTN][DID] Cache MISS fetching from DB did_number={ctx.did_number}")
            try:
                did_record = await self.__did_repository.get_did_by_number(
                    call_to_number=ctx.did_number, partner_id=None
                )
                self.__logger.info(
                    f"[PSTN][DID] DB fetch done did_number={ctx.did_number} found={did_record is not None}"
                )
            except Exception as e:
                self.__logger.error(
                    f"[PSTN][DID] DB fetch failed did_number={ctx.did_number} error={e} traceback={traceback.format_exc()}"
                )
                raise
            if not did_record or not did_record.get("is_active", True):
                if did_record and not did_record.get("is_active", True):
                    raise ValueError(f"No active DID record found for {ctx.did_number}")
                # DB-miss: single-entry dynamic inbound. Otoba is source of
                # truth — if the engine has DID -> (agent, talko_partner_id),
                # auto-use it without a Talko DID row. Inactive rows still
                # reject above (explicit disable wins over engine).
                dynamic = await self._aresolve_voiceai_resolution_for_did(ctx.did_number)
                if dynamic is None or not dynamic.get("agent_id") or not dynamic.get("partner_id"):
                    raise ValueError(f"No active DID record found for {ctx.did_number}")
                did_record = {
                    "did_type": TalkoDIDType.AI_AGENT.value,
                    "partner_id": dynamic["partner_id"],
                    "vendor_config_id": dynamic.get("vendor_config_id") or "",
                    "agent_id": 0,
                    "agent_bot_id": 0,
                    "is_active": True,
                    "_synthetic": True,
                    "did_number": ctx.did_number,
                }
                prefetched_voiceai_agent = dynamic.get("agent_id")
                self.__logger.info(
                    "[PSTN][DID] dynamic engine-owned DID {} partner_id={} — no Talko row needed".format(
                        ctx.did_number, dynamic["partner_id"]
                    )
                )
                # Short TTL so a later real Talko row / engine unassign
                # re-resolves quickly; agent truth still re-checked per call
                # via the voiceai agent cache (60s) + Step 4b.
                try:
                    ttl = int(getattr(TalkoENV, "VOICEAI_DID_CACHE_TTL_SECONDS", 60) or 60)
                except Exception:
                    ttl = 60
                await self._set_cached_did(ctx.did_number, did_record, ttl=ttl)
            else:
                await self._set_cached_did(ctx.did_number, did_record)
        else:
            self.__logger.info(f"[PSTN][DID] Cache HIT did_number={ctx.did_number}")
            if not did_record.get("is_active", True):
                raise ValueError(f"No active DID record found for {ctx.did_number}")

        did_type: str = did_record.get("did_type", TalkoDIDType.NORMAL.value)
        partner_id: int = did_record["partner_id"]
        vendor_config_id: str = str(did_record.get("vendor_config_id", ""))
        agent_id: int | None = did_record.get("agent_id")
        agent_bot_id: int | None = did_record.get("agent_bot_id")

        self.__logger.info(
            f"[PSTN][DID] did_type={did_type} partner_id={partner_id} vendor_config_id={vendor_config_id} agent_id={agent_id} agent_bot_id={agent_bot_id}"
        )

        if did_type == TalkoDIDType.AI_AGENT.value:
            if not agent_bot_id:
                # VoiceAI-routed inbound DIDs store only did_number -> partner_id
                # (agent_bot_id stays 0). The agent lives in the voiceai engine's
                # Numbers UI and is looked up per call (Redis-cached). Env map
                # stays as emergency override and wins when set.
                # Fail only if the engine also has no mapping (fail-closed).
                # Cache the agent on ctx so fast-path / outbound fast-path /
                # Step 4b / session reuse it without extra Redis round trips.
                # Dynamic DB-miss already fetched it above — reuse, don't refetch.
                voiceai_agent = prefetched_voiceai_agent or await self._aresolve_voiceai_agent_id_for_did(
                    ctx.did_number
                )
                if voiceai_agent is None:
                    raise ValueError(f"DID {ctx.did_number} is ai_agent but agent_bot_id is missing")
                ctx.voiceai_agent_id = voiceai_agent
                self.__logger.info(
                    f"[PSTN][DID] voiceai-mapped DID {ctx.did_number} agent={voiceai_agent} — cached on ctx"
                )
            else:
                ctx.makunai_agent_id = agent_bot_id
        else:
            if not agent_id:
                raise ValueError(f"DID {ctx.did_number} is normal but agent_id is missing")
            ctx.makunai_agent_id = agent_id

        ctx.partner_id = partner_id
        ctx.vendor_config_id = vendor_config_id

        self.__logger.info(
            f"[PSTN][DID] ✅ Resolved partner_id={ctx.partner_id} makunai_agent_id={ctx.makunai_agent_id}"
        )
        return ctx

    @staticmethod
    def _voiceai_configured() -> bool:
        """True when the voiceai trunk env (WS + ticket API) is provisioned."""
        return bool(TalkoENV.VOICEAI_WS_BASE_URL and TalkoENV.VOICEAI_API_KEY)

    @staticmethod
    def _voiceai_resolve_configured() -> bool:
        """True when the engine DID-resolve API can be called."""
        return bool(TalkoENV.VOICEAI_API_BASE_URL and TalkoENV.VOICEAI_API_KEY)

    @staticmethod
    def _normalize_voiceai_did_digits(did_number: str) -> str:
        """Normalize a DID to engine-lookup digits (no '+', spaces, dashes).

        Same normalization as Talko's DID store: ``normalize_phone_number(...,
        with_plus=False)`` gives ``91XXXXXXXXXX`` for Indian numbers, so
        ``+9179…``, ``9179…``, ``91 79-…`` and 10-digit variants all map to
        the same key. Falls back to digits-only on unexpected input.
        """
        try:
            normalized = normalize_phone_number(did_number or "", with_plus=False)
            if normalized:
                return normalized
        except Exception:
            pass
        return "".join(ch for ch in (did_number or "") if ch.isdigit())

    async def _resolve_voiceai_agent_id(self, ctx: TalkoCallContext) -> str | None:
        """Resolve the voiceai agent for this call, if it is voiceai-routed.

        Outbound: ``context_data.voiceai_agent_id`` (set by voiceai's
        talko_api_server via POST /call context_data).
        Inbound: env override -> Redis -> engine ``/phone-numbers/resolve``.
        Returns None for makun-ai / human calls (normal path unchanged).

        Prefers the Step-2 cached ``ctx.voiceai_agent_id`` so one call pays
        one Redis lookup max — critical when Redis p99 is high.
        """
        agent_id = (ctx.context_data or {}).get(VOICEAI_AGENT_ID_KEY)
        if agent_id:
            return str(agent_id)
        if getattr(ctx, "voiceai_agent_id", None):
            return str(ctx.voiceai_agent_id)
        return await self._aresolve_voiceai_agent_id_for_did(ctx.did_number)

    def _resolve_voiceai_agent_id_sync(self, ctx: TalkoCallContext) -> str | None:
        """Sync env-only fast check (kept for backward compat / tests)."""
        agent_id = (ctx.context_data or {}).get(VOICEAI_AGENT_ID_KEY)
        if agent_id:
            return str(agent_id)
        return self._resolve_voiceai_agent_id_for_did(ctx.did_number)

    def _resolve_voiceai_agent_id_for_did(self, did_number: str) -> str | None:
        """Inbound lookup only, env override: DID -> voiceai agent id.

        Tolerant of leading '+' (Tata sends +9179…, maps may store 9179…),
        spaces/dashes and 10-vs-12-digit variants via normalized digits.
        This is the emergency override — it always wins when set.
        """
        try:
            mapping = json.loads(TalkoENV.VOICEAI_INBOUND_AGENT_MAP or "{}")
        except (json.JSONDecodeError, TypeError) as e:
            self.__logger.warning(f"[PSTN][VOICEAI] Ignoring invalid VOICEAI_INBOUND_AGENT_MAP: {e}")
            return None
        if not isinstance(mapping, dict):
            return None
        candidates = [did_number, (did_number or "").lstrip("+")]
        try:
            normalized = self._normalize_voiceai_did_digits(did_number or "")
            if normalized and normalized not in candidates:
                candidates.append(normalized)
        except Exception:
            pass
        for candidate in candidates:
            agent_id = mapping.get(candidate)
            if agent_id:
                return str(agent_id)
        return None

    async def _get_cached_voiceai_agent(self, digits: str) -> tuple[bool, str | None]:
        """Redis lookup for engine DID mapping.

        Returns (found, agent_id): found=False means cache miss (or Redis
        down — treated as a miss so calls still route via direct engine
        call). found=True with agent_id=None means cached 404 (negative hit).
        """
        key = VOICEAI_DID_CACHE_KEY.format(digits=digits)
        try:
            redis = await self._get_redis()
            raw = await redis.get(key)
            if raw is None:
                return False, None
            if isinstance(raw, bytes):
                raw = raw.decode()
            if not raw:
                self.__logger.debug(f"[PSTN][VOICEAI][CACHE] NEGATIVE HIT digits={digits}")
                return True, None
            self.__logger.debug(f"[PSTN][VOICEAI][CACHE] HIT digits={digits}")
            return True, str(raw)
        except Exception as exc:
            self.__logger.warning(f"[PSTN][VOICEAI][CACHE] GET ERROR digits={digits} error={exc} — treating as miss")
            return False, None

    async def _set_cached_voiceai_agent(self, digits: str, agent_id: str | None) -> None:
        """Cache engine answer: positives 60s, 404 misses 10s (self-heals)."""
        key = VOICEAI_DID_CACHE_KEY.format(digits=digits)
        try:
            redis = await self._get_redis()
            if agent_id:
                ttl = int(getattr(TalkoENV, "VOICEAI_DID_CACHE_TTL_SECONDS", 60) or 60)
                await redis.set(key, str(agent_id), ex=ttl)
            else:
                ttl = int(getattr(TalkoENV, "VOICEAI_DID_NEGATIVE_CACHE_TTL_SECONDS", 10) or 10)
                await redis.set(key, "", ex=ttl)
        except Exception as exc:
            self.__logger.warning(f"[PSTN][VOICEAI][CACHE] SET ERROR digits={digits} error={exc}")

    async def _fetch_voiceai_resolution_from_engine(
        self, did_number: str, digits: str
    ) -> tuple[bool, str | None, int | None, str | None]:
        """Direct engine call. Returns (completed, agent_id, partner_id, vendor_config_id).

        completed=False means transport error/timeout — caller must NOT cache
        it (fail-closed reject, retry next call). completed=True with
        agent_id=None means engine 404 (cache as negative hit). partner_id /
        vendor_config_id come from the engine Numbers UI (single-entry
        dynamic inbound); legacy rows without them return None there.
        """
        base = (TalkoENV.VOICEAI_API_BASE_URL or "").rstrip("/")
        if not base or not TalkoENV.VOICEAI_API_KEY:
            return True, None, None, None
        url = f"{base}/phone-numbers/resolve"
        timeout = float(getattr(TalkoENV, "VOICEAI_DID_RESOLVE_TIMEOUT_SECONDS", 0.3) or 0.3)
        try:
            resp = await self.__http_client.get(
                url,
                params={"number": did_number},
                headers={"Authorization": f"Bearer {TalkoENV.VOICEAI_API_KEY}"},
                timeout=timeout,
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                data = data or {}
                agent_id = data.get("agent_id")
                partner_id: int | None = None
                try:
                    raw_partner = data.get("talko_partner_id")
                    if raw_partner is not None and str(raw_partner).strip() != "":
                        partner_id = int(raw_partner)
                except (TypeError, ValueError):
                    partner_id = None
                vendor_config_id = data.get("talko_vendor_config_id")
                vendor_config_id = str(vendor_config_id) if vendor_config_id else None
                return (
                    True,
                    str(agent_id) if agent_id else None,
                    partner_id,
                    vendor_config_id,
                )
            if resp.status_code == 404:
                return True, None, None, None
            self.__logger.warning(f"[PSTN][VOICEAI][ENGINE] Unexpected status={resp.status_code} digits={digits}")
            return False, None, None, None
        except Exception as exc:
            self.__logger.warning(f"[PSTN][VOICEAI][ENGINE] Lookup failed digits={digits} error={exc} — fail-closed")
            return False, None, None, None

    async def _fetch_voiceai_agent_from_engine(self, did_number: str, digits: str) -> tuple[bool, str | None]:
        """Backward-compat wrapper: agent only (partner ignored)."""
        completed, agent_id, _, _ = await self._fetch_voiceai_resolution_from_engine(did_number, digits)
        return completed, agent_id

    async def _aresolve_voiceai_resolution_for_did(self, did_number: str) -> dict[str, Any] | None:
        """Full inbound resolution: env override -> Redis -> engine HTTP.

        Returns {"agent_id", "partner_id", "vendor_config_id"} or None.
        Env always wins for agent (break-glass) but partner still comes
        from the engine — DB-miss dynamic inbound needs both, so it must
        hit the engine even when env provides the agent.
        """
        digits = self._normalize_voiceai_did_digits(did_number or "")
        if not digits:
            return None
        env_hit = self._resolve_voiceai_agent_id_for_did(did_number)
        if not self._voiceai_resolve_configured():
            # Env-only mode (local dev / tests): partner unknown here —
            # callers with a Talko DID row use env_hit via the agent-only
            # helper; DB-miss dynamic needs engine, so return None.
            return None
        # Direct engine call (source of truth for partner). Agent cache is
        # intentionally not used here — partner isn't cached there, and this
        # runs only on Talko DB-miss (then synthetic DID cache covers the
        # next 60s; steady-state calls use the agent-only helper, no HTTP).
        completed, agent_id, partner_id, vendor_config_id = await self._fetch_voiceai_resolution_from_engine(
            did_number, digits
        )
        if not completed:
            return None
        await self._set_cached_voiceai_agent(digits, agent_id)
        if not agent_id:
            return None
        # Env wins for agent selection; partner always from engine.
        return {
            "agent_id": env_hit or agent_id,
            "partner_id": partner_id,
            "vendor_config_id": vendor_config_id,
        }

    async def _aresolve_voiceai_agent_id_for_did(self, did_number: str) -> str | None:
        """Full inbound lookup: env override -> Redis -> engine HTTP.

        Env always wins (break-glass). Redis holds positives 60s and 404
        misses 10s. Redis down/flushed is treated as a miss and falls back
        to a direct engine call (~300ms timeout, pooled client) — truth
        lives in Mongo + engine, never Redis, so it self-heals in one call
        per DID. Engine timeout -> None (caller rejects, fail-closed).
        """
        # 1. Emergency override first — zero I/O, behavior unchanged on cutover.
        env_hit = self._resolve_voiceai_agent_id_for_did(did_number)
        if env_hit:
            return env_hit
        # 2. No engine configured (local dev / tests) — env-only mode.
        if not self._voiceai_resolve_configured():
            return None
        digits = self._normalize_voiceai_did_digits(did_number or "")
        if not digits:
            return None
        # 3. Redis cache.
        found, cached = await self._get_cached_voiceai_agent(digits)
        if found:
            return cached
        # 4. Direct engine call.
        completed, agent_id = await self._fetch_voiceai_agent_from_engine(did_number, digits)
        if not completed:
            return None
        await self._set_cached_voiceai_agent(digits, agent_id)
        return agent_id

    async def _run_voiceai_relay(self, ws, provider, ctx, event, raw_events, voiceai_agent_id: str) -> None:
        """Run one voiceai relay leg. Shared by the Step-2 fast path (inbound
        voiceai DIDs) and Step 4b (outbound AI-bridge after context attach).
        Returns normally either way; the caller breaks out to cleanup."""
        try:
            relay = TalkoVoiceaiRelay(
                ws_base_url=TalkoENV.VOICEAI_WS_BASE_URL,
                api_base_url=TalkoENV.VOICEAI_API_BASE_URL,
                api_key=TalkoENV.VOICEAI_API_KEY,
                logger=self.__logger,
                ticket_timeout_seconds=TalkoENV.VOICEAI_WS_TICKET_TIMEOUT_SECONDS,
                connect_timeout_seconds=TalkoENV.VOICEAI_WS_CONNECT_TIMEOUT_SECONDS,
            )
            await relay.run(
                ws,
                provider,
                ctx,
                event,
                raw_events,
                voiceai_agent_id,
            )
        except Exception as e:
            self.__logger.error(
                f"[PSTN][CALL] ❌ voiceai relay FAILED sid={ctx.call_sid} error={e} traceback={traceback.format_exc()}"
            )

    async def _attach_pending_context(self, ctx: TalkoCallContext, event: dict[str, Any]) -> TalkoCallContext:
        """
        Attach pre-stored call context to ctx.

        Changes vs original:
        1. Uses TalkoCallRedisHelper.fetch_and_delete_context() which pipelines
           GET context + DELETE both keys into 2 round trips instead of 4
           sequential calls (get_store_key → get_context → delete_context
           → delete_index = 4 round trips).
        2. _set_stream_context is fired as a background task — it is not
           needed before _create_session so there is no reason to await it
           on the critical path. Saves ~30-80ms per call.
        """
        self.__logger.info(f"[PSTN][CTX] ===== ATTACH PENDING CONTEXT ===== call_sid={ctx.call_sid}")

        try:
            start: dict[str, Any] = event.get("start", {}) if isinstance(event, dict) else {}
            to_number_raw = start.get("to", "")
            to_number = to_number_raw.lstrip("+")

            self.__logger.info(f"[PSTN][CTX] to_number={to_number} raw={to_number_raw}")

            if not to_number:
                self.__logger.warning("[PSTN][CTX] to_number missing in start event")
                return ctx

            # Replaces 4 sequential Redis round trips with 2
            # (1 GET for index, 1 pipeline for GET+DELETE+DELETE)
            pending = await self.__call_redis_helper.fetch_and_delete_context(to_number)

            self.__logger.info(f"[PSTN][CTX] pending context found={pending is not None} to_number={to_number}")

            if not pending:
                self.__logger.warning(f"[PSTN][CTX] ❌ No context found for to_number={to_number}")
                return ctx

            ctx.context_data = pending.get("context_data") or {}
            ctx.pending_context_found = True
            ctx.vendor_call_id = start.get("callSid") or start.get("callId") or start.get("callid") or ctx.call_sid

            self.__logger.info(f"[PSTN][CTX] vendor_call_id={ctx.vendor_call_id} context_data={ctx.context_data}")

            # Fire-and-forget — stream context is used for observability/debugging
            # only and is NOT needed before session creation or LiveKit connect.
            asyncio.create_task(
                self._set_stream_context(
                    ctx.stream_sid,
                    {
                        "stream_sid": ctx.stream_sid,
                        "call_sid": ctx.call_sid,
                        "vendor_call_id": ctx.vendor_call_id,
                        "partner_id": pending.get("partner_id"),
                        "from_number": pending.get("from_number"),
                        "to_number": pending.get("to_number"),
                        "context_data": ctx.context_data,
                    },
                ),
                name=f"stream_ctx_{ctx.call_sid}",
            )

            self.__logger.info(f"[PSTN][CTX] ✅ Context attached call_sid={ctx.call_sid}")
            return ctx

        except Exception as exc:
            self.__logger.error(f"[PSTN][CTX] ❌ error={exc} traceback={traceback.format_exc()}")
            return ctx

    async def _create_session(self, ctx: TalkoCallContext) -> TalkoCallContext:
        self.__logger.info(
            f"[PSTN][SESSION] Creating session call_sid={ctx.call_sid} partner_id={ctx.partner_id} agent_id={ctx.makunai_agent_id}"
        )
        if (ctx.context_data or {}).get(VOICEAI_AGENT_ID_KEY):
            # voiceai-routed call — no makun-ai session; handle_call() runs
            # the voiceai relay instead (see Step 4b below).
            self.__logger.info(
                f"[PSTN][SESSION] voiceai-routed call sid={ctx.call_sid} agent={ctx.context_data.get(VOICEAI_AGENT_ID_KEY)} — "
                "skipping makun-ai session"
            )
            return ctx
        if (await self._resolve_voiceai_agent_id(ctx)) is not None:
            # VoiceAI call (context marker or DID mapping, Step-2 cached) —
            # skip on the cached value first so this costs zero Redis trips
            # on the hot path. Without this, _create_session would attempt
            # the makun-ai path (incl. a gRPC API-key fetch) and kill the
            # call before Step 4b ever runs.
            self.__logger.info(f"[PSTN][SESSION] voiceai-mapped DID sid={ctx.call_sid} — skipping makun-ai session")
            return ctx
        try:
            api_key: str = await self._resolve_partner_api_key(ctx.partner_id)
            headers = {"API-Key": api_key, "Content-Type": "application/json"}
            # call_sid is the vendor's own call identifier (Tata callSid) — already
            # known here for both inbound and the outbound fallback path, so it can
            # go straight into context_data for makun-ai's tool-call auto-injection
            # (see tools/executor.py). Our value wins over any caller-supplied one.
            session_context_data: dict[str, Any] = {
                **(ctx.context_data or {}),
                "call_id": ctx.call_sid,
            }
            payload = {
                "agent_id": ctx.makunai_agent_id,
                "partner_id": ctx.partner_id,
                "session_id": ctx.call_sid,
                "medium": "voice",
                "caller_did": ctx.did_number,
                "external_call_sid": ctx.call_sid,
                "caller_phone": ctx.caller_number,
                "context_data": session_context_data,
                "skip_greeting_audio": True,
            }
            self.__logger.info(
                f"[PSTN][SESSION] Sending to MAKUNAI_SESSION_URL={TalkoENV.MAKUNAI_SESSION_URL} payload={json.dumps(payload, default=str)}"
            )
            resp = await self.__http_client.post(
                TalkoENV.MAKUNAI_SESSION_URL,
                headers=headers,
                json=payload,
                timeout=MAKUNAI_SESSION_TIMEOUT_SECONDS,
            )
            self.__logger.info(f"[PSTN][SESSION] Response status={resp.status_code}")
            resp.raise_for_status()
            data = resp.json()["data"]
            ctx.livekit_url = data["livekit_url"]
            ctx.caller_token = data["caller_token"]
            ctx.room_name = data["room_name"]
            ctx.greeting_audio = data.get("greeting_audio")  # NEW
            self.__logger.info(f"[PSTN][SESSION] ✅ Session created call_sid={ctx.call_sid} room={ctx.room_name}")
            return ctx
        except Exception as e:
            self.__logger.error(
                f"[PSTN][SESSION] ❌ FAILED call_sid={ctx.call_sid} error={e} traceback={traceback.format_exc()}"
            )
            raise

    async def _backfill_real_vendor_call_id(self, ctx: TalkoCallContext, room: rtc.Room) -> None:
        """
        Best-effort background task: resolve Tata's real vendor call_id (not
        ctx.call_sid) via the live_calls poll and republish it over the
        LiveKit data channel, so makun-ai's context_data["call_id"] ends up
        holding a value that TalkoTataTeleCallHandler.hangup_call() can actually
        use — not just the WS callSid that the unconditional Step 6 publish
        sends.

        AI-bridge's click_to_call_support never returns call_id synchronously
        (see TalkoTataTeleCallHandler.find_live_call_id docstring), and the
        pre-warm path's own bounded 1.5s poll (TalkoCallService._pre_create_session)
        can still miss. This is a second, decoupled attempt that runs off the
        critical path — it must never delay track publish/greeting playback,
        so it is always fired via asyncio.create_task, never awaited inline.

        Never raises — any failure just means context_data keeps whatever
        call_id it already had (ctx.call_sid), exactly as before this method
        existed.
        """
        try:
            self.__logger.info(
                f"[PSTN][CALL_ID] Backfilling real vendor call_id call_sid={ctx.call_sid} room={room.name}, call_context={ctx.context_data}"
            )
            partner_config = await self.__call_repository.get_partner_config_by_partner_id(ctx.partner_id)
            if not partner_config:
                return

            self.__logger.info(
                f"[PSTN][CALL_ID] Backfilling real vendor call_id call_sid={ctx.call_sid} room={room.name}, partner_config={partner_config}"
            )

            vendor_id: str | None = partner_config.get("vendor_id")
            vendor_config_id: str | None = partner_config.get("ai_vendor_config_id") or partner_config.get(
                "vendor_config_id"
            )
            if not vendor_id or not vendor_config_id:
                return

            self.__logger.info(
                f"[PSTN][CALL_ID] Backfilling real vendor call_id call_sid={ctx.call_sid} room={room.name}, vendor_id={vendor_id} vendor_config_id={vendor_config_id}"
            )

            vendor_config = await self.__call_repository.get_vendor_config(vendor_id, vendor_config_id)
            if not vendor_config:
                return

            self.__logger.info(
                f"[PSTN][CALL_ID] Backfilling real vendor call_id call_sid={ctx.call_sid} room={room.name}, vendor_config={vendor_config}"
            )

            handler = TalkoTataTeleCallHandler(vendor_config, self.__logger, vendor_config.get("vendor_type"))

            self.__logger.info(
                f"[PSTN][CALL_ID] Backfilling real vendor call_id call_sid={ctx.call_sid} room={room.name}, handler={handler}"
            )
            resolved_call_id = await handler.find_live_call_id(
                did_number=ctx.did_number, customer_number=ctx.caller_number
            )
            self.__logger.info(
                f"[PSTN][CALL_ID] Backfilling real vendor call_id call_sid={ctx.call_sid} room={room.name}, resolved_call_id={resolved_call_id}"
            )

            if resolved_call_id:
                await room.local_participant.publish_data(
                    payload=json.dumps({"type": "call_id", "call_id": resolved_call_id}).encode("utf-8"),
                    reliable=True,
                )
                self.__logger.info(
                    f"[PSTN][CALL_ID] ✅ Backfilled real vendor call_id={resolved_call_id} call_sid={ctx.call_sid} room={room.name}"
                )
            else:
                # live_calls poll found nothing (call already progressed
                # past ringing, or Tata's poll window missed it) — ctx.call_sid
                # is still a genuine Tata call identifier (parsed off the WS
                # start event, already published unconditionally in Step 6),
                # so use it as the TalkoCDR fallback rather than leaving the TalkoCDR's
                # call_id empty forever just because this specific poll missed.
                self.__logger.info(
                    "[PSTN][CALL_ID] No live_calls match — falling back to "
                    f"ctx.call_sid={ctx.call_sid} for TalkoCDR update"
                )

            # Fix up Talko's own TalkoCDR row (inserted at initiate_call time
            # with call_id="" for AI-bridge calls, since Tata's click-to-call
            # API never returns it synchronously) in BOTH cases above — a
            # resolved live_calls id is preferred, ctx.call_sid otherwise.
            # Without this, Tata's later dialer webhook can never match this
            # row via get_cdr_by_call_id_or_uuid (empty call_id, and Talko's
            # own self-generated call_uuid doesn't match Tata's), so it
            # creates an orphan duplicate TalkoCDR instead of enriching this one.
            final_call_id = resolved_call_id or ctx.call_sid
            cdr_id = (ctx.context_data or {}).get("cdr_id")
            if cdr_id and final_call_id:
                try:
                    self.__logger.info(
                        f"[PSTN][CALL_ID] Backfilling real vendor call_id call_sid={ctx.call_sid} room={room.name}, cdr_id={cdr_id}"
                    )
                    await self.__call_repository.update_cdr(cdr_id, {"call_id": final_call_id})
                    self.__logger.info(
                        f"[PSTN][CALL_ID] ✅ Updated TalkoCDR cdr_id={cdr_id} with call_id={final_call_id}"
                    )
                except Exception as exc:
                    self.__logger.warning(
                        f"[PSTN][CALL_ID] Failed to update TalkoCDR cdr_id={cdr_id} with call_id={final_call_id}: {exc}"
                    )
        except Exception as e:
            self.__logger.warning(
                f"[PSTN][CALL_ID] Background vendor call_id backfill failed call_sid={ctx.call_sid}: {e}"
            )

    # ── NEW: greeting playback idempotency + direct playback ─────────────────

    async def _claim_greeting_playback(self, call_sid: str) -> bool:
        """
        Atomically claims the right to play the greeting for this call_sid.

        Returns True the first time this is called for a given call_sid —
        caller should play it. Returns False on every subsequent call for the
        same call_sid (e.g. a Tata WS reconnect re-running handle_call(), or a
        duplicate "start" event) — caller should skip playback.
        """
        key = GREETING_PLAYED_KEY.format(call_sid=call_sid)
        try:
            redis = await self._get_redis()
            claimed = await redis.set(key, "1", nx=True, ex=GREETING_PLAYED_TTL_SECONDS)
            return bool(claimed)
        except Exception as e:
            self.__logger.warning(
                f"[PSTN][GREETING] Idempotency check failed call_sid={call_sid}: {e} — playing anyway"
            )
            return True

    async def _play_cached_greeting(
        self,
        ws,
        provider: TalkoAbstractPSTNProvider,
        stream_sid: str,
        greeting_audio_b64: str,
        bridge: TalkoAudioBridge,
        pending_marks: dict[str, asyncio.Event],
        mark_sent_at: dict[str, float],
        delay_seconds: float = 0.0,
    ) -> None:
        """
        Plays a pre-rendered greeting directly over the Tata WebSocket,
        bypassing the LiveKit agent entirely for the first utterance.

        greeting_audio_b64 is raw PCM16 mono 48000Hz, base64-encoded — exactly
        what TalkoAudioBridge.outbound() expects, so this reuses the SAME
        conversion + chunking + send path _outbound_audio() already uses for
        live agent speech, just with a different audio source. Uses a
        "greeting_" label prefix (vs "chunk_") so its marks can't collide
        with _outbound_audio()'s marks in the shared pending_marks dict.

        delay_seconds, when set, waits before starting playback — used for
        inbound calls only, to give a brief natural pause right after the
        line connects rather than starting the greeting the instant Step 6
        finishes. Runs inside this background task, so it never blocks the
        main receive loop processing the caller's incoming audio.
        """
        chunk_num = 0
        try:
            if delay_seconds > 0:
                self.__logger.info(
                    f"[PSTN][GREETING] Delaying greeting playback by {delay_seconds:.1f}s stream_sid={stream_sid}"
                )
                await asyncio.sleep(delay_seconds)

            pcm_48k = base64.b64decode(greeting_audio_b64)
            mulaw_8k = bridge.outbound(pcm_48k)
            chunks, _ = TalkoAudioBridge.align_chunks(mulaw_8k)

            self.__logger.info(f"[PSTN][GREETING] Playing cached greeting stream_sid={stream_sid} chunks={len(chunks)}")

            for chunk in chunks:
                while len(pending_marks) >= MAX_PENDING_MARKS:
                    oldest_label = next(iter(pending_marks))
                    try:
                        await asyncio.wait_for(pending_marks[oldest_label].wait(), timeout=ACK_WAIT_SECONDS)
                    except TimeoutError:
                        self.__logger.warning(
                            f"[PSTN][GREETING] Ack timeout label={oldest_label} pending={len(pending_marks)}"
                        )
                    finally:
                        pending_marks.pop(oldest_label, None)
                        mark_sent_at.pop(oldest_label, None)

                chunk_num += 1
                label = f"greeting_{chunk_num:06d}"
                pending_marks[label] = asyncio.Event()
                mark_sent_at[label] = time.perf_counter()
                await provider.send_audio(ws, chunk, label, stream_sid=stream_sid, chunk=chunk_num)

            self.__logger.info(f"[PSTN][GREETING] Cached greeting sent chunks={chunk_num} stream_sid={stream_sid}")
        except Exception as e:
            self.__logger.warning(f"[PSTN][GREETING] Cached greeting playback failed stream_sid={stream_sid}: {e}")

    async def _run_outbound_with_greeting(
        self,
        greeting_task,
        room,
        ws,
        provider,
        pending_marks,
        mark_sent_at,
        stream_sid,
        bridge,
    ) -> None:
        """
        Ensures the agent's live speech never starts streaming to Tata until
        the cached greeting (if any) has fully finished — preserving correct
        audio ordering on the line — while both run as background tasks so
        the main receive loop in handle_call() is never blocked by either.
        """
        if greeting_task is not None:
            try:
                await greeting_task
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # greeting failure already logged inside _play_cached_greeting
        await self._outbound_audio(room, ws, provider, pending_marks, mark_sent_at, stream_sid, bridge)

    # ─────────────────────────────────────────────────────────────────────────

    async def handle_call(self, ws, provider: TalkoAbstractPSTNProvider, raw_events) -> None:
        self.__logger.info("[PSTN][CALL] ===== HANDLE CALL STARTED =====")
        ctx: TalkoCallContext | None = None
        room: rtc.Room | None = None
        audio_source: rtc.AudioSource | None = None
        pending_marks: dict[str, asyncio.Event] = {}
        mark_sent_at: dict[str, float] = {}
        media_frame_count: int = 0
        outbound_task: asyncio.Task | None = None
        greeting_task: asyncio.Task | None = None
        bridge = TalkoAudioBridge()

        try:
            async for raw in raw_events:
                try:
                    event: dict[str, Any] = json.loads(raw)
                except json.JSONDecodeError as e:
                    self.__logger.warning(f"[PSTN][CALL] Invalid JSON: {e}")
                    continue

                etype: str | None = event.get("event")
                self.__logger.debug("[PSTN][CALL] Event type={} sid={}".format(etype, ctx.call_sid if ctx else "?"))

                if etype == "connected":
                    await ws.send_text(json.dumps({"event": "connected"}))
                    self.__logger.info("[PSTN][CALL] WebSocket connected ack sent")

                elif etype == "start":
                    self.__logger.info(f"[PSTN][CALL] ===== START EVENT ===== raw={str(event)[:500]}")
                    try:
                        t0 = time.perf_counter()

                        # ── Step 1: Parse ─────────────────────────────────────
                        self.__logger.info("[PSTN][CALL] Step 1: Parsing start event")
                        ctx = await provider.parse_start_event(event)
                        self.__logger.info(
                            f"[PSTN][CALL] Step 1 done: call_sid={ctx.call_sid} did={ctx.did_number} caller={ctx.caller_number} stream_sid={ctx.stream_sid}"
                        )

                        # ── Step 2: DID resolve ───────────────────────────────
                        self.__logger.info(f"[PSTN][CALL] Step 2: Resolving DID={ctx.did_number}")
                        ctx = await self._resolve_did(ctx)
                        self.__logger.info(
                            f"[PSTN][CALL] Step 2 done: partner_id={ctx.partner_id} agent_id={ctx.makunai_agent_id}"
                        )

                        # ── Fast path: voiceai DIDs skip room/session ──
                        #
                        # Inbound: everything Steps 3-4 do (room selection,
                        # pending context attach, makun-ai session) is for the
                        # LiveKit path — agent resolves from the DID map and
                        # the relay needs only ws/provider/ctx/event.
                        # Outbound voiceai: same — voiceai never pre-warms a
                        # room (call_management skips makun-ai pre-session for
                        # voiceai), so the outbound_room retry loop below is a
                        # guaranteed ~400ms miss, and _create_session would
                        # just re-check the same DID agent and return. Attach
                        # pending context (per-call agent/variables) then relay
                        # directly. Context timeout still bounds slow Redis —
                        # relay falls back to the DID agent.
                        # ─────────────────────────────────────────────────────
                        start_dir = (event.get("start", {}) or {}).get("direction", "inbound")
                        # Step-2 cached — zero Redis trips on the hot path.
                        fast_voiceai_agent = getattr(ctx, "voiceai_agent_id", None)
                        if fast_voiceai_agent is None:
                            fast_voiceai_agent = await self._aresolve_voiceai_agent_id_for_did(ctx.did_number)
                            if fast_voiceai_agent:
                                ctx.voiceai_agent_id = fast_voiceai_agent
                        if fast_voiceai_agent and self._voiceai_configured():
                            if start_dir != "outbound":
                                self.__logger.info(
                                    f"[PSTN][CALL] Fast path: inbound voiceai sid={ctx.call_sid} "
                                    f"agent={fast_voiceai_agent} — skipping Steps 3-4"
                                )
                                # Preserve what _attach_pending_context would have
                                # set and cleanup/observability may read (the call
                                # has no pending context on the inbound leg).
                                start_obj = event.get("start", {}) or {}
                                ctx.vendor_call_id = (
                                    start_obj.get("callSid")
                                    or start_obj.get("callId")
                                    or start_obj.get("callid")
                                    or ctx.call_sid
                                )
                                await self._run_voiceai_relay(
                                    ws,
                                    provider,
                                    ctx,
                                    event,
                                    raw_events,
                                    fast_voiceai_agent,
                                )
                                break
                            # Outbound voiceai: attach per-call context, skip
                            # room selection + session entirely.
                            self.__logger.info(
                                f"[PSTN][CALL] Fast path: outbound voiceai sid={ctx.call_sid} "
                                f"did_agent={fast_voiceai_agent} — attaching ctx, skipping room/session"
                            )
                            t_ctx = time.perf_counter()
                            try:
                                ctx = await asyncio.wait_for(
                                    asyncio.shield(
                                        asyncio.create_task(
                                            self._attach_pending_context(ctx, event),
                                            name=f"ctx_attach_{ctx.call_sid}",
                                        )
                                    ),
                                    timeout=0.4,
                                )
                            except TimeoutError:
                                self.__logger.warning(
                                    "[PSTN][CALL] Fast path ctx timeout (400ms) — "
                                    f"relaying with DID agent call_sid={ctx.call_sid}"
                                )
                            self.__logger.info(
                                "[PSTN][CALL] Fast path ctx done: pending_found={} elapsed={:.0f}ms".format(
                                    getattr(ctx, "pending_context_found", False),
                                    (time.perf_counter() - t_ctx) * 1000,
                                )
                            )
                            voiceai_agent_id = (ctx.context_data or {}).get(VOICEAI_AGENT_ID_KEY) or fast_voiceai_agent
                            if not ctx.vendor_call_id:
                                start_obj = event.get("start", {}) or {}
                                ctx.vendor_call_id = (
                                    start_obj.get("callSid")
                                    or start_obj.get("callId")
                                    or start_obj.get("callid")
                                    or ctx.call_sid
                                )
                            await self._run_voiceai_relay(
                                ws,
                                provider,
                                ctx,
                                event,
                                raw_events,
                                str(voiceai_agent_id),
                            )
                            break

                        # ── Step 3: Room selection ────────────────────────────
                        #
                        # For outbound AI-bridge calls, TalkoCallService._pre_create_session
                        # pre-created a makun-ai session during the ringing window and
                        # stored it in Redis under outbound_room:<to_number>.
                        #
                        # If found: skip _attach_pending_context and _create_session
                        # entirely — the room and worker are already warm. This is what
                        # makes outbound latency match web (~400ms vs 8-10s).
                        #
                        # If not found (pre-session failed / timed out / inbound call):
                        # fall back to the existing parallel context+session path, which
                        # is unchanged and safe for all call types.
                        # ─────────────────────────────────────────────────────
                        start_data: dict[str, Any] = event.get("start", {})
                        direction: str = start_data.get("direction", "inbound")
                        # Must match the normalization _pre_create_session uses when
                        # storing outbound_room:<to_number> (call_management/services.py)
                        # — plain .lstrip("+") let a leading zero / missing country
                        # code / spaces produce a different key on this side and
                        # miss deterministically even when timing lined up fine.
                        to_number: str = normalize_phone_number(start_data.get("to", ""), with_plus=False)

                        self.__logger.info(
                            f"[PSTN][CALL] Step 3: Room selection direction={direction} to_number={to_number}"
                        )

                        if direction == "outbound" and to_number:
                            outbound_room = await self.__call_redis_helper.fetch_and_delete_outbound_room_with_retry(
                                to_number
                            )
                        else:
                            outbound_room = None

                        if outbound_room:
                            # ── Fast path: pre-warmed room ────────────────────
                            age = time.time() - outbound_room.get("created_at", time.time())
                            self.__logger.info(
                                "[PSTN][CALL] Step 3: 🔥 Pre-warmed room HIT "
                                "to_number={} room={} age={:.1f}s — "
                                "skipping session creation".format(
                                    to_number,
                                    outbound_room.get("room_name"),
                                    age,
                                )
                            )
                            ctx.room_name = outbound_room["room_name"]
                            ctx.caller_token = outbound_room["caller_token"]
                            ctx.livekit_url = outbound_room["livekit_url"]
                            ctx.pre_warmed = True
                            # carries cdr_id — see TalkoCallService._pre_create_session
                            # Step 4 (call_management/services.py) — needed by
                            # _backfill_real_vendor_call_id below to update the
                            # original TalkoCDR row once the real call_id resolves.
                            ctx.context_data = outbound_room.get("context_data") or {}
                            ctx.greeting_audio = outbound_room.get("greeting_audio")  # NEW

                            # Stream context write is observability only — fire-and-forget
                            asyncio.create_task(
                                self._set_stream_context(
                                    ctx.stream_sid,
                                    {
                                        "stream_sid": ctx.stream_sid,
                                        "call_sid": ctx.call_sid,
                                        "room_name": ctx.room_name,
                                        "direction": direction,
                                        "pre_warmed": True,
                                    },
                                ),
                                name=f"stream_ctx_{ctx.call_sid}",
                            )

                        else:
                            # ── Fallback / inbound path: context then session ──
                            #
                            # Runs for:
                            #   - All inbound calls
                            #   - Outbound calls where pre-session failed/timed out
                            #   - Non-AI-bridge outbound calls
                            #
                            # session_task must not start until context_task has
                            # written ctx.context_data — _create_session reads it
                            # after only one Redis round trip, so running them
                            # concurrently let it win the race and send
                            # call_id-only context_data to makun-ai. 400ms timeout
                            # on context still bounds Redis slowness.
                            # ──────────────────────────────────────────────────
                            if outbound_room is None and direction == "outbound":
                                self.__logger.info(
                                    "[PSTN][CALL] Step 3: No pre-warmed room for outbound "
                                    f"to_number={to_number} — falling back to on-demand session"
                                )
                            else:
                                self.__logger.info(
                                    f"[PSTN][CALL] Step 3: Inbound call to_number={to_number} — using on-demand session"
                                )

                            self.__logger.info(
                                "[PSTN][CALL] Steps 3+4: Context attach + Session create "
                                f"(parallel) call_sid={ctx.call_sid}"
                            )
                            t_parallel = time.perf_counter()

                            context_task = asyncio.create_task(
                                self._attach_pending_context(ctx, event),
                                name=f"ctx_attach_{ctx.call_sid}",
                            )

                            try:
                                ctx = await asyncio.wait_for(asyncio.shield(context_task), timeout=0.4)
                                self.__logger.info(
                                    "[PSTN][CALL] Step 3 done: pending_found={} "
                                    "context_data={} elapsed={:.0f}ms".format(
                                        getattr(ctx, "pending_context_found", False),
                                        ctx.context_data,
                                        (time.perf_counter() - t_parallel) * 1000,
                                    )
                                )
                            except TimeoutError:
                                self.__logger.warning(
                                    "[PSTN][CALL] Step 3 timeout (400ms) — proceeding "
                                    f"without context call_sid={ctx.call_sid}"
                                )
                                context_task.cancel()

                            # _create_session reads ctx.context_data synchronously
                            # after a single Redis round trip — it must not start
                            # until context_task has actually written that field,
                            # or it races ahead and sends call_id-only context_data
                            # to makun-ai (see PSTN/CALL_ID comment history above).
                            session_task = asyncio.create_task(
                                self._create_session(ctx),
                                name=f"session_create_{ctx.call_sid}",
                            )
                            ctx = await session_task
                            self.__logger.info(
                                f"[PSTN][CALL] Step 4 done: room={ctx.room_name} livekit_url={ctx.livekit_url} "
                                f"parallel_elapsed={(time.perf_counter() - t_parallel) * 1000:.0f}ms"
                            )
                        # ── End room selection ────────────────────────────────

                        # ── Step 4b: voiceai route ────────────────────────────
                        #
                        # Calls carrying context_data.voiceai_agent_id (outbound
                        # calls placed via voiceai's talko_api_server) or whose
                        # DID is mapped (env override or cached engine lookup)
                        # bypass the makun-ai LiveKit path entirely: relay Tata
                        # media to the voiceai agent socket instead, then break
                        # out to the normal cleanup below (room is None there).
                        # ─────────────────────────────────────────────────────
                        voiceai_agent_id = await self._resolve_voiceai_agent_id(ctx)
                        if voiceai_agent_id and self._voiceai_configured():
                            self.__logger.info(
                                f"[PSTN][CALL] Step 4b: voiceai relay sid={ctx.call_sid} agent={voiceai_agent_id}"
                            )
                            await self._run_voiceai_relay(
                                ws,
                                provider,
                                ctx,
                                event,
                                raw_events,
                                voiceai_agent_id,
                            )
                            break

                        # ── Step 5: LiveKit connect ───────────────────────────
                        self.__logger.info(f"[PSTN][CALL] Step 5: Connecting LiveKit room={ctx.room_name}")
                        room = rtc.Room()
                        await room.connect(
                            ctx.livekit_url,
                            ctx.caller_token,
                            rtc.RoomOptions(auto_subscribe=True),
                        )
                        self.__logger.info(f"[PSTN][CALL] Step 5 done: LiveKit connected room={ctx.room_name}")

                        # ── Step 6: Publish audio track ───────────────────────
                        self.__logger.info("[PSTN][CALL] Step 6: Publishing audio track")
                        audio_source = rtc.AudioSource(sample_rate=48000, num_channels=1)
                        track = rtc.LocalAudioTrack.create_audio_track("pstn-in", audio_source)
                        publish_options = rtc.TrackPublishOptions()
                        publish_options.source = rtc.TrackSource.SOURCE_MICROPHONE
                        await room.local_participant.publish_track(track, publish_options)
                        self.__logger.info("[PSTN][CALL] Step 6 done: Track published")

                        # ── Backfill call_id over the data channel ────────────
                        # The outbound pre-warm path creates the makun-ai session
                        # before Tata assigns a real callSid (it comes back as the
                        # string "None" at that point), so that session's
                        # context_data never got a usable call_id. ctx.call_sid is
                        # always real by here though (parsed off the start event
                        # for every call type), so send it now — the agent worker
                        # merges it into its in-memory context_data on receipt.
                        # Sent unconditionally (cheap) — for inbound/fallback
                        # calls context_data already has it, so this is a no-op
                        # confirmation there.
                        try:
                            await room.local_participant.publish_data(
                                payload=json.dumps({"type": "call_id", "call_id": ctx.call_sid}).encode("utf-8"),
                                reliable=True,
                            )
                        except Exception as e:
                            self.__logger.warning(
                                f"[PSTN][CALL] Failed to publish call_id to room={ctx.room_name}: {e}"
                            )

                        # ── Best-effort second pass: resolve + republish the real
                        # vendor call_id (not just ctx.call_sid) for hangup/transfer.
                        # Fully decoupled background task — never awaited here, so
                        # it cannot add latency to call setup or greeting playback.
                        asyncio.create_task(
                            self._backfill_real_vendor_call_id(ctx, room),
                            name=f"vendor_call_id_{ctx.call_sid}",
                        )

                        # ── NEW: play cached greeting directly, bypassing the agent ──
                        if getattr(ctx, "greeting_audio", None):
                            should_play = await self._claim_greeting_playback(ctx.call_sid)
                            if should_play:
                                # Signal the agent BEFORE playback starts, not after — greeting
                                # length varies, but this fires within milliseconds of publish_track,
                                # so the agent's short wait below reliably catches it.
                                try:
                                    await room.local_participant.publish_data(
                                        payload=b'{"type":"greeting_played"}',
                                        reliable=True,
                                    )
                                except Exception as e:
                                    self.__logger.warning(f"[PSTN][GREETING] Failed to signal agent: {e}")

                                greeting_task = asyncio.create_task(
                                    self._play_cached_greeting(
                                        ws,
                                        provider,
                                        ctx.stream_sid,
                                        ctx.greeting_audio,
                                        bridge,
                                        pending_marks,
                                        mark_sent_at,
                                        delay_seconds=(
                                            INBOUND_GREETING_DELAY_SECONDS if direction == "inbound" else 0.0
                                        ),
                                    ),
                                    name=f"greeting_{ctx.call_sid}",
                                )
                            else:
                                self.__logger.info(
                                    f"[PSTN][GREETING] Skipping — already played for call_sid={ctx.call_sid}"
                                )

                        outbound_task = asyncio.create_task(
                            self._run_outbound_with_greeting(
                                greeting_task,
                                room,
                                ws,
                                provider,
                                pending_marks,
                                mark_sent_at,
                                ctx.stream_sid,
                                bridge,
                            ),
                            name=f"outbound_{ctx.call_sid}",
                        )

                        self.__logger.info(
                            "[PSTN][CALL] ✅ Call LIVE total_setup={:.0f}ms sid={} "
                            "room={} agent_id={} pre_warmed={}".format(
                                (time.perf_counter() - t0) * 1000,
                                ctx.call_sid,
                                ctx.room_name,
                                ctx.makunai_agent_id,
                                getattr(ctx, "pre_warmed", False),
                            )
                        )
                    except Exception as e:
                        self.__logger.error(f"[PSTN][CALL] ❌ Setup FAILED: {e} traceback={traceback.format_exc()}")
                        break

                elif provider.is_media_event(event) and audio_source:
                    if media_frame_count == 0:
                        self.__logger.info(
                            f"[PSTN][CALL] First inbound media frame received {(time.perf_counter() - t0) * 1000:.0f}ms after Step 6 sid={ctx.call_sid}"
                        )
                    media_frame_count += 1
                    if media_frame_count % 100 == 0:
                        self.__logger.debug(
                            "[PSTN][CALL] Inbound frames={} sid={}".format(
                                media_frame_count, ctx.call_sid if ctx else "?"
                            )
                        )
                    try:
                        pcm_48k = bridge.inbound(provider.get_audio_payload(event))
                        await audio_source.capture_frame(
                            rtc.AudioFrame(
                                data=pcm_48k,
                                sample_rate=48000,
                                num_channels=1,
                                samples_per_channel=len(pcm_48k) // 2,
                            )
                        )
                    except Exception as e:
                        self.__logger.warning(
                            "[PSTN][CALL] Inbound audio error sid={}: {}".format(ctx.call_sid if ctx else "?", e)
                        )

                elif provider.is_media_event(event) and not audio_source:
                    self.__logger.warning(
                        "[PSTN][CALL] Media event but audio_source=None sid={}".format(ctx.call_sid if ctx else "?")
                    )

                elif provider.is_mark_ack(event):
                    label = provider.get_mark_label(event)
                    if label in pending_marks:
                        pending_marks[label].set()

                elif etype == "clear":
                    self.__logger.info("[PSTN][CALL] Clear event sid={}".format(ctx.call_sid if ctx else "?"))
                    for ev in pending_marks.values():
                        ev.set()
                    pending_marks.clear()
                    mark_sent_at.clear()
                    await provider.send_clear(ws, stream_sid=ctx.stream_sid if ctx else "")

                elif provider.is_stop_event(event):
                    self.__logger.info(
                        "[PSTN][CALL] Call ended sid={} frames={}".format(
                            ctx.call_sid if ctx else "?", media_frame_count
                        )
                    )
                    break

                else:
                    self.__logger.debug(
                        "[PSTN][CALL] Unhandled event type={} sid={}".format(etype, ctx.call_sid if ctx else "?")
                    )

        except Exception as e:
            self.__logger.error(
                "[PSTN][CALL] ❌ Unexpected error: sid={} error={} traceback={}".format(
                    ctx.call_sid if ctx else "?", e, traceback.format_exc()
                )
            )
        finally:
            self.__logger.info(
                "[PSTN][CALL] ===== CLEANUP ===== sid={} frames={}".format(
                    ctx.call_sid if ctx else "?", media_frame_count
                )
            )
            if greeting_task and not greeting_task.done():
                greeting_task.cancel()
                try:
                    await greeting_task
                except asyncio.CancelledError:
                    pass
            if outbound_task and not outbound_task.done():
                outbound_task.cancel()
                try:
                    await outbound_task
                except asyncio.CancelledError:
                    pass
            if room:
                try:
                    await room.disconnect()
                    self.__logger.info("[PSTN][CALL] LiveKit disconnected sid={}".format(ctx.call_sid if ctx else "?"))
                except Exception as e:
                    self.__logger.error(
                        "[PSTN][CALL] LiveKit disconnect failed sid={}: {}".format(ctx.call_sid if ctx else "?", e)
                    )

    async def _outbound_audio(self, room, ws, provider, pending_marks, mark_sent_at, stream_sid, bridge) -> None:
        self.__logger.info(f"[PSTN][OUT] ===== OUTBOUND AUDIO STARTED ===== stream_sid={stream_sid}")
        buffer: bytes = b""
        chunk_num: int = 0
        audio_stream_queue: asyncio.Queue = asyncio.Queue()

        def on_track_subscribed(track, publication, participant):
            if isinstance(track, rtc.RemoteAudioTrack):
                self.__logger.info(
                    f"[PSTN][OUT] Remote audio track subscribed participant={participant.identity} track_id={track.sid}"
                )
                stream = rtc.AudioStream(track, sample_rate=48000, num_channels=1)
                asyncio.ensure_future(audio_stream_queue.put(stream))

        room.on("track_subscribed", on_track_subscribed)

        try:
            existing_count = 0
            for participant in room.remote_participants.values():
                for publication in participant.track_publications.values():
                    if publication.track is not None and isinstance(publication.track, rtc.RemoteAudioTrack):
                        existing_count += 1
                        stream = rtc.AudioStream(publication.track, sample_rate=48000, num_channels=1)
                        audio_stream_queue.put_nowait(stream)
            self.__logger.info(f"[PSTN][OUT] Pre-existing tracks found={existing_count} stream_sid={stream_sid}")

            try:
                self.__logger.info(f"[PSTN][OUT] Waiting for audio stream (timeout=15s) stream_sid={stream_sid}")
                audio_stream = await asyncio.wait_for(audio_stream_queue.get(), timeout=15.0)
                self.__logger.info(f"[PSTN][OUT] Audio stream ready stream_sid={stream_sid}")
            except TimeoutError:
                self.__logger.error(f"[PSTN][OUT] ❌ Timed out waiting for remote audio track stream_sid={stream_sid}")
                return

            async for audio_event in audio_stream:
                try:
                    ws_state = ws.client_state.name
                    if ws_state == "DISCONNECTED":
                        self.__logger.info(f"[PSTN][OUT] WebSocket disconnected stopping stream_sid={stream_sid}")
                        return
                except Exception:
                    pass

                try:
                    frame = audio_event.frame
                    buffer += bridge.outbound(bytes(frame.data))
                    chunks, buffer = TalkoAudioBridge.align_chunks(buffer, chunk_size=CHUNK_SIZE)

                    for chunk in chunks:
                        while len(pending_marks) >= MAX_PENDING_MARKS:
                            oldest_label = next(iter(pending_marks))
                            try:
                                await asyncio.wait_for(
                                    pending_marks[oldest_label].wait(),
                                    timeout=ACK_WAIT_SECONDS,
                                )
                            except TimeoutError:
                                self.__logger.warning(
                                    f"[PSTN][OUT] Ack timeout label={oldest_label} pending={len(pending_marks)}"
                                )
                            finally:
                                pending_marks.pop(oldest_label, None)
                                mark_sent_at.pop(oldest_label, None)

                        chunk_num += 1
                        label = f"chunk_{chunk_num:06d}"
                        pending_marks[label] = asyncio.Event()
                        mark_sent_at[label] = time.perf_counter()
                        await provider.send_audio(ws, chunk, label, stream_sid=stream_sid, chunk=chunk_num)

                        if chunk_num % 100 == 0:
                            self.__logger.info(
                                f"[PSTN][OUT] chunks_sent={chunk_num} pending={len(pending_marks)} stream_sid={stream_sid}"
                            )

                except Exception as e:
                    err_str = str(e)
                    if "close message has been sent" in err_str or "DISCONNECTED" in err_str:
                        self.__logger.info(f"[PSTN][OUT] WebSocket closed stopping stream_sid={stream_sid}")
                        return
                    self.__logger.warning(f"[PSTN][OUT] Frame error chunk={chunk_num} error={e}")
                    continue

        except asyncio.CancelledError:
            self.__logger.info(f"[PSTN][OUT] Task cancelled stream_sid={stream_sid}")
        except Exception as e:
            self.__logger.error(
                f"[PSTN][OUT] ❌ Task error stream_sid={stream_sid} error={e} traceback={traceback.format_exc()}"
            )
        finally:
            room.off("track_subscribed", on_track_subscribed)
            self.__logger.info(f"[PSTN][OUT] Done total_chunks={chunk_num} stream_sid={stream_sid}")
