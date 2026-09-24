"""PSTN <-> LiveKit audio transcoding (mulaw 8k <-> PCM 48k).

Extracted from pstn/services.py — pure codec logic with no I/O, kept in its
own module so media changes don't require touching the bridge service.
"""

import audioop

from src.core.redis_constants import CHUNK_SIZE


class TalkoAudioBridge:
    def __init__(self) -> None:
        self._inbound_state: tuple[bytes, int] | None = None
        self._outbound_state: tuple[bytes, int] | None = None

    def inbound(self, mulaw_bytes: bytes) -> bytes:
        try:
            pcm_8k: bytes = audioop.ulaw2lin(mulaw_bytes, 2)
            pcm_48k, self._inbound_state = audioop.ratecv(pcm_8k, 2, 1, 8000, 48000, self._inbound_state)
            return pcm_48k
        except Exception as e:
            raise RuntimeError(f"TalkoAudioBridge.inbound conversion failed: {e}")

    def outbound(self, pcm_48k: bytes) -> bytes:
        try:
            pcm_8k, self._outbound_state = audioop.ratecv(pcm_48k, 2, 1, 48000, 8000, self._outbound_state)
            return audioop.lin2ulaw(pcm_8k, 2)
        except Exception as e:
            raise RuntimeError(f"TalkoAudioBridge.outbound conversion failed: {e}")

    @staticmethod
    def align_chunks(buffer: bytes, chunk_size: int = CHUNK_SIZE) -> tuple[list[bytes], bytes]:
        chunks: list[bytes] = []
        while len(buffer) >= chunk_size:
            chunks.append(buffer[:chunk_size])
            buffer = buffer[chunk_size:]
        return chunks, buffer
