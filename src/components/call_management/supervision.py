import json
from typing import Any

from src.components.cache.redis_client import get_redis_client
from src.components.inbound_call_events.publisher import TalkoInboundCallEventPublisher
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil

SUPERVISE_KEY = "supervise:{call_id}"
SUPERVISE_TTL_SECONDS = 4 * 3600

ATTENDED_KEY = "attended:{call_id}"
ATTENDED_TTL_SECONDS = 4 * 3600

SUPERVISE_MODES = frozenset({"listen", "whisper", "barge"})

SUPERVISOR_INVITE_EVENT = "supervisor_invite"
SUPERVISOR_LEAVE_EVENT = "supervisor_leave"
ATTENDED_EVENT = "attended_transfer"


class TalkoSupervisionService:
    """Supervisor barge-in sessions + attended (warm) transfer orchestration.

    Media-plane note: LiveKit rooms/tokens are minted by makun-ai (talko only
    joins via caller_token) — talko has no LiveKit API keys. This service
    therefore owns the signalling plane: session registry (Redis), role/mode
    validation, and real-time invites over the existing inbound-call WS
    broker. The supervisor client joins the same LiveKit room the invite
    names (token via the engine/makun-ai path) with publish rights per mode:
    listen = subscribe-only, whisper = talk to agent, barge = talk to all.
    """

    def __init__(
        self,
        logger: TalkoServiceLogger,
        event_publisher: TalkoInboundCallEventPublisher | None = None,
    ) -> None:
        self.__logger = logger
        self.__publisher = event_publisher

    def _supervise_key(self, call_id: str) -> str:
        return SUPERVISE_KEY.format(call_id=call_id)

    def _attended_key(self, call_id: str) -> str:
        return ATTENDED_KEY.format(call_id=call_id)

    @staticmethod
    def modes() -> list[str]:
        return sorted(SUPERVISE_MODES)

    async def start_supervise(
        self,
        call_id: str,
        partner_id: int,
        supervisor_id: str,
        mode: str,
        room_name: str | None = None,
    ) -> dict[str, Any]:
        mode = (mode or "").lower()
        if mode not in SUPERVISE_MODES:
            raise TalkoBadRequestError(f"Invalid mode '{mode}'. Supported: {sorted(SUPERVISE_MODES)}")
        if not call_id or not supervisor_id:
            raise TalkoBadRequestError("call_id and supervisor_id are required")
        redis = await get_redis_client()
        key = self._supervise_key(call_id)
        existing_raw = await redis.get(key)
        if existing_raw is not None:
            raise TalkoBadRequestError(f"Call {call_id} is already supervised")
        now = TalkoDateTimeUtil.get_current_time()
        session = {
            "call_id": call_id,
            "partner_id": partner_id,
            "supervisor_id": supervisor_id,
            "mode": mode,
            "room_name": room_name or "",
            "status": "active",
            "started_at": now,
        }
        await redis.set(key, json.dumps(session), ex=SUPERVISE_TTL_SECONDS)
        self.__logger.info(f"Supervisor {supervisor_id} started {mode} on call {call_id}")
        if self.__publisher is not None:
            try:
                await self.__publisher.publish_supervisor_event(
                    event=SUPERVISOR_INVITE_EVENT,
                    partner_id=partner_id,
                    call_id=call_id,
                    supervisor_id=supervisor_id,
                    mode=mode,
                    room_name=room_name or "",
                )
            except Exception as e:
                self.__logger.error(f"Failed to publish supervisor invite: {e}")
        return session

    async def stop_supervise(self, call_id: str, partner_id: int = 0) -> dict[str, Any]:
        redis = await get_redis_client()
        key = self._supervise_key(call_id)
        raw = await redis.get(key)
        if raw is None:
            raise TalkoResourceNotFound(f"No active supervision for call {call_id}")
        session = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        await redis.delete(key)
        self.__logger.info(f"Supervisor session ended for call {call_id}")
        if self.__publisher is not None:
            try:
                await self.__publisher.publish_supervisor_event(
                    event=SUPERVISOR_LEAVE_EVENT,
                    partner_id=partner_id or session.get("partner_id", 0),
                    call_id=call_id,
                    supervisor_id=session.get("supervisor_id", ""),
                    mode=session.get("mode", ""),
                    room_name=session.get("room_name", ""),
                )
            except Exception as e:
                self.__logger.error(f"Failed to publish supervisor leave: {e}")
        session["status"] = "ended"
        return session

    async def get_supervise(self, call_id: str) -> dict[str, Any] | None:
        redis = await get_redis_client()
        raw = await redis.get(self._supervise_key(call_id))
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)

    async def start_attended(self, call_id: str, partner_id: int, target_number: str) -> dict[str, Any]:
        """Stage 1 of warm transfer: park intent + consult leg metadata."""
        if not call_id or not target_number:
            raise TalkoBadRequestError("call_id and target_number are required")
        redis = await get_redis_client()
        key = self._attended_key(call_id)
        if await redis.get(key) is not None:
            raise TalkoBadRequestError(f"Attended transfer already staged for call {call_id}")
        now = TalkoDateTimeUtil.get_current_time()
        staged = {
            "call_id": call_id,
            "partner_id": partner_id,
            "target_number": target_number,
            "status": "consult",
            "staged_at": now,
        }
        await redis.set(key, json.dumps(staged), ex=ATTENDED_TTL_SECONDS)
        self.__logger.info(f"Attended transfer staged call_id={call_id} target={target_number}")
        if self.__publisher is not None:
            try:
                await self.__publisher.publish_supervisor_event(
                    event=ATTENDED_EVENT,
                    partner_id=partner_id,
                    call_id=call_id,
                    supervisor_id="",
                    mode="consult",
                    room_name="",
                    extra={"target_number": target_number, "status": "consult"},
                )
            except Exception as e:
                self.__logger.error(f"Failed to publish attended event: {e}")
        return staged

    async def complete_attended(self, call_id: str, partner_id: int = 0) -> dict[str, Any]:
        """Stage 2 of warm transfer: caller completes → blind-transfer leg runs."""
        redis = await get_redis_client()
        key = self._attended_key(call_id)
        raw = await redis.get(key)
        if raw is None:
            raise TalkoResourceNotFound(f"No staged attended transfer for call {call_id}")
        staged = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        staged["status"] = "completed"
        staged["completed_at"] = TalkoDateTimeUtil.get_current_time()
        await redis.delete(key)
        if self.__publisher is not None:
            try:
                await self.__publisher.publish_supervisor_event(
                    event=ATTENDED_EVENT,
                    partner_id=partner_id or staged.get("partner_id", 0),
                    call_id=call_id,
                    supervisor_id="",
                    mode="completed",
                    room_name="",
                    extra={"target_number": staged.get("target_number"), "status": "completed"},
                )
            except Exception as e:
                self.__logger.error(f"Failed to publish attended event: {e}")
        return staged
