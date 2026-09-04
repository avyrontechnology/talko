from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.components.inbound_call_events.connection_manager import InboundCallEventBroker
from src.core.container import Container
from src.loggers.holler_service_logger import HollerServiceLogger

logger = HollerServiceLogger.get_logger()

router: APIRouter = APIRouter()


@router.websocket("/ws/inbound-calls/{partner_id}")
@inject
async def inbound_call_events_stream(
    websocket: WebSocket,
    partner_id: int,
    broker: InboundCallEventBroker = Depends(
        Provide[Container.inbound_call_event_broker]
    ),
) -> None:
    """
    Streams inbound-call agent-dialplan events (partner_id, service_board_id,
    dedicated_did, agent_id) to a client subscribed for a given partner.

    TEMPORARY: auth is bypassed here (matches the pstn/tata/stream websocket) for
    testing. Must be restored (token query param + partner match, see git history
    on this file) before this ships anywhere real users can reach it.

    The broker MUST come in via Provide[...] (wired against the actual container
    instance created in main.py) rather than a bare `Container.inbound_call_event_broker()`
    class-level call — dependency_injector deep-copies providers on instantiation,
    so a class-level call resolves to a different singleton than the one whose Redis
    listener was started at app startup, and registrations on it would never receive
    anything. See InboundCallEventBroker's docstring for the multi-pod fanout design.
    """
    await websocket.accept()
    await broker.register(partner_id, websocket)
    logger.info("Inbound call ws connected for partner {}".format(partner_id))

    try:
        while True:
            # Connection is push-only from the server; just block until disconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        broker.unregister(partner_id, websocket)
        logger.info("Inbound call ws disconnected for partner {}".format(partner_id))


class InboundCallEventController:
    router: APIRouter = router
