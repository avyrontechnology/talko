from fastapi import APIRouter, Depends, WebSocket

from src.components.pstn.providers.tata_tele.handler import TataTeleProvider
from src.components.pstn.services import PSTNBridgeService
from src.core.container import Container
from src.loggers.holler_service_logger import HollerServiceLogger

logger = HollerServiceLogger.get_logger()

_tata_provider: TataTeleProvider = TataTeleProvider()
router: APIRouter = APIRouter()


def _get_bridge() -> PSTNBridgeService:
    return Container.pstn_bridge_service()


@router.websocket("/tata/stream")
async def tata_stream(
    ws: WebSocket,
    bridge: PSTNBridgeService = Depends(_get_bridge),
) -> None:
    await ws.accept()
    logger.info("[PSTN] websocket accepted")
    logger.info("[PSTN] bridge type={}".format(type(bridge).__name__))

    async def raw_events():
        while True:
            try:
                msg = await ws.receive_text()
                logger.info("[PSTN] received raw msg={}".format(msg[:120]))
                yield msg
            except Exception as e:
                logger.exception("[PSTN] raw_events failed: {}".format(e))
                break

    await bridge.handle_call(ws, _tata_provider, raw_events())


class PSTNAgentController:
    router: APIRouter = router
