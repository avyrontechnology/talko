from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.components.inbound_call_events.connection_manager import TalkoInboundCallEventBroker
from src.core.container import TalkoContainer
from src.loggers.talko_service_logger import TalkoServiceLogger

logger = TalkoServiceLogger.get_logger()

router: APIRouter = APIRouter()


@router.websocket("/ws/inbound-calls/{partner_id}")
@inject
async def inbound_call_events_stream(
    websocket: WebSocket,
    partner_id: int,
    broker: TalkoInboundCallEventBroker = Depends(Provide[TalkoContainer.inbound_call_event_broker]),
) -> None:
    """
    Streams inbound-call agent-dialplan events (partner_id, workspace_id,
    dedicated_did, agent_id) to a client subscribed for a given partner.

    NOTE: no token/auth validation for now, by product decision — any client
    that knows a partner_id can subscribe. Reintroduce ?token= validation
    (Talko JWT / partner API key, see git history on this file) before
    exposing this to untrusted networks.

    The broker MUST come in via Provide[...] (wired against the actual container
    instance created in main.py) rather than a bare `TalkoContainer.inbound_call_event_broker()`
    class-level call — dependency_injector deep-copies providers on instantiation,
    so a class-level call resolves to a different singleton than the one whose Redis
    listener was started at app startup, and registrations on it would never receive
    anything. See TalkoInboundCallEventBroker's docstring for the multi-pod fanout design.
    """
    await websocket.accept()
    await broker.register(partner_id, websocket)
    logger.info(f"Inbound call ws connected for partner {partner_id}")

    try:
        while True:
            # Connection is push-only from the server; just block until disconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        broker.unregister(partner_id, websocket)
        logger.info(f"Inbound call ws disconnected for partner {partner_id}")


class TalkoInboundCallEventController:
    router: APIRouter = router
