from fastapi import APIRouter, Depends, WebSocket

from src.components.pstn.providers.tata_tele.handler import TalkoTataTeleProvider
from src.components.pstn.services import TalkoPSTNBridgeService
from src.core.container import TalkoContainer
from src.loggers.talko_service_logger import TalkoServiceLogger

logger = TalkoServiceLogger.get_logger()

_tata_provider: TalkoTataTeleProvider = TalkoTataTeleProvider()
router: APIRouter = APIRouter()


def _get_bridge() -> TalkoPSTNBridgeService:
    return TalkoContainer.pstn_bridge_service()


@router.websocket("/tata/stream")
async def tata_stream(
    ws: WebSocket,
    bridge: TalkoPSTNBridgeService = Depends(_get_bridge),
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


class TalkoPSTNAgentController:
    router: APIRouter = router
