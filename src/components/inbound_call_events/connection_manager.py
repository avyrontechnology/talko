import asyncio
import json
from collections import defaultdict
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket
from starlette_context import request_cycle_context

from src.components.inbound_call_events.constants import INBOUND_CALL_EVENTS_CHANNEL
from src.loggers.holler_service_logger import HollerServiceLogger

SEND_TIMEOUT_SECONDS = 5
_LISTENER_RETRY_DELAY_SECONDS = 2


class InboundCallEventBroker:
    """
    Fans out inbound-call events to websocket clients, scoped per partner_id.

    This service runs multiple pods, and a client's websocket only ever lives
    in the memory of the one pod that accepted it. publish() therefore
    doesn't deliver locally — it publishes to Redis (INBOUND_CALL_EVENTS_CHANNEL),
    and every pod runs its own subscriber loop (start()) that re-delivers each
    message to whatever sockets are registered locally on that pod. That way
    an event published from any pod reaches clients connected to any pod.

    Must be resolved the same way everywhere (via the wired container
    instance — Depends(Provide[Container.inbound_call_event_broker]) in
    controllers, container.inbound_call_event_broker() in main.py) so the
    listener started at app startup and the connections registered by the
    websocket route are the same singleton. A bare class-level
    Container.inbound_call_event_broker() call resolves to a different
    instance (dependency_injector deep-copies providers on Container()
    instantiation) — see git history on this file for what that broke.
    """

    def __init__(self, redis_pool, logger: HollerServiceLogger):
        self.__redis_pool = redis_pool
        self.__logger = logger
        self.__connections: Dict[int, Set[WebSocket]] = defaultdict(set)
        self.__listener_task: Optional[asyncio.Task] = None

    async def register(self, partner_id: int, websocket: WebSocket) -> None:
        self.__connections[partner_id].add(websocket)
        self.__logger.info(
            "Registered inbound call ws for partner {} (active={})".format(
                partner_id, len(self.__connections[partner_id])
            )
        )

    def unregister(self, partner_id: int, websocket: WebSocket) -> None:
        self.__connections.get(partner_id, set()).discard(websocket)

    async def publish(self, data: Dict[str, Any]) -> None:
        await self.__redis_pool.publish(INBOUND_CALL_EVENTS_CHANNEL, json.dumps(data))

    async def start(self) -> None:
        if self.__listener_task is None:
            self.__listener_task = asyncio.create_task(self.__listen())
            self.__logger.info("Inbound call event broker listener started")

    async def stop(self) -> None:
        if self.__listener_task is not None:
            self.__listener_task.cancel()
            self.__listener_task = None

    async def __listen(self) -> None:
        while True:
            try:
                pubsub = self.__redis_pool.pubsub()
                await pubsub.subscribe(INBOUND_CALL_EVENTS_CHANNEL)
                self.__logger.info(
                    "Subscribed to {}".format(INBOUND_CALL_EVENTS_CHANNEL)
                )
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    await self.__dispatch(message.get("data"))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.__logger.error(
                    "Inbound call event listener error, retrying: {}".format(str(e))
                )
                await asyncio.sleep(_LISTENER_RETRY_DELAY_SECONDS)

    async def __dispatch(self, raw_message: Any) -> None:
        try:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")
            data = json.loads(raw_message)
        except Exception as e:
            self.__logger.error(
                "Failed to parse inbound call event message: {}".format(str(e))
            )
            return

        partner_id = data.get("partner_id")
        sockets = list(self.__connections.get(partner_id, set()))

        await asyncio.gather(
            *(self.__send(partner_id, websocket, data) for websocket in sockets)
        )

    async def __send(self, partner_id: int, websocket: WebSocket, data: Dict[str, Any]) -> None:
        try:
            # ContextMiddleware wraps every websocket's send() to attach a
            # request-id, which reads starlette_context's ContextVar. This
            # runs on the broker's own background listener task (created at
            # app startup), not inside the request cycle that originally
            # accepted the websocket, so that ContextVar is otherwise unset —
            # request_cycle_context() gives it something to read.
            with request_cycle_context():
                await asyncio.wait_for(
                    websocket.send_json(data), timeout=SEND_TIMEOUT_SECONDS
                )
        except Exception as e:
            self.__logger.error(
                "Failed to send inbound call event to a socket for partner {}: {}".format(
                    partner_id, str(e)
                )
            )
            self.__connections[partner_id].discard(websocket)
            try:
                await websocket.close()
            except Exception:
                pass
