from fastapi import APIRouter, Depends, WebSocket
from starlette.websockets import WebSocketDisconnect

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
    logger.info(f"[PSTN] bridge type={type(bridge).__name__}")

    async def raw_events():
        while True:
            try:
                msg = await ws.receive_text()
                # Media frames arrive every 20 ms — INFO per frame buries the
                # signal (hundreds of lines per call). Control events
                # (start/stop/mark/clear) stay at INFO.
                if '"event":"media"' in msg:
                    logger.debug(f"[PSTN] received raw msg={msg[:120]}")
                else:
                    logger.info(f"[PSTN] received raw msg={msg[:120]}")
                yield msg
            except WebSocketDisconnect as e:
                # Normal hangup (code 1000) or provider-side close — routine
                # end of call, not a failure. No traceback.
                logger.info(f"[PSTN] Tata websocket closed code={e.code} reason={e.reason!r}")
                break
            except Exception as e:
                logger.exception(f"[PSTN] raw_events failed: {e}")
                break

    await bridge.handle_call(ws, _tata_provider, raw_events())


class TalkoPSTNAgentController:
    router: APIRouter = router
