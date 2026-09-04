from abc import ABC, abstractmethod

from src.components.pstn.dto import CallContext


class AbstractPSTNProvider(ABC):
    """
    Abstract base class for all PSTN provider implementations.

    Each provider (Tata Tele, Twilio, Exotel, etc.) implements this interface
    to adapt its WebSocket protocol to the provider-agnostic PSTNBridgeService.

    Audio contract:
        - All inbound audio (provider → us) is μ-law 8kHz mono, base64-encoded.
        - All outbound audio (us → provider) must be μ-law 8kHz mono, 160 bytes
          per chunk (20 ms), base64-encoded.
        - stream_sid is extracted from the start event and must be passed to
          send_audio and send_clear for providers that require it (e.g. Tata Tele).
        - chunk is a monotonically increasing counter required by some providers
          (e.g. Tata Tele) for sequencing outbound media events.
    """

    @abstractmethod
    async def parse_start_event(self, raw_event: dict) -> CallContext:
        """
        Parse a provider-specific 'start' WebSocket event into a CallContext.

        Must populate at minimum:
            call_sid, stream_sid, did_number, caller_number, direction.

        Args:
            raw_event: Raw parsed JSON dict of the start event from the provider.

        Returns:
            Fully populated CallContext for this call.
        """
        ...

    @abstractmethod
    async def send_audio(
        self,
        ws,
        audio_bytes: bytes,
        label: str,
        stream_sid: str = "",
        chunk: int = 1,
    ) -> None:
        """
        Send one μ-law audio chunk to the caller via the provider's protocol.

        Implementations should send the audio payload and a mark event
        (if supported by the provider) so playback acknowledgements can be tracked.

        Args:
            ws:          WebSocket connection to the provider.
            audio_bytes: 160 bytes of μ-law 8kHz audio (20 ms per chunk).
            label:       Unique mark label for this chunk (e.g. "chunk_000001").
            stream_sid:  Stream identifier from the start event.
                         Required by Tata Tele — omitting causes silent discard.
            chunk:       Monotonically increasing chunk counter (1-based).
                         Required by Tata Tele for sequencing.
        """
        ...

    @abstractmethod
    async def send_clear(self, ws, stream_sid: str = "") -> None:
        """
        Flush the provider's outbound audio buffer on barge-in / interruption.

        Called when an inbound 'clear' event is received to immediately stop
        playback of the current agent audio on the caller's end.

        Args:
            ws:         WebSocket connection to the provider.
            stream_sid: Stream identifier from the start event.
                        Required by Tata Tele — omitting causes silent discard.
        """
        ...

    @abstractmethod
    def is_media_event(self, event: dict) -> bool:
        """
        Return True if the event carries inbound audio from the caller.

        Args:
            event: Parsed event dict from the provider.
        """
        ...

    @abstractmethod
    def get_audio_payload(self, event: dict) -> bytes:
        """
        Extract and decode raw μ-law audio bytes from an inbound media event.

        Args:
            event: Parsed media event dict from the provider.

        Returns:
            Raw μ-law 8kHz bytes.
        """
        ...

    @abstractmethod
    def is_stop_event(self, event: dict) -> bool:
        """
        Return True if the event signals call termination.

        Args:
            event: Parsed event dict from the provider.
        """
        ...

    @abstractmethod
    def get_stop_reason(self, event: dict) -> str:
        """
        Extract the stop reason from a stop event.

        Args:
            event: Parsed stop event dict from the provider.

        Returns:
            Reason string (e.g. "hangup", "timeout"), or "unknown" if absent.
        """
        ...

    @abstractmethod
    def is_mark_ack(self, event: dict) -> bool:
        """
        Return True if the event is a playback acknowledgement for a mark.

        Args:
            event: Parsed event dict from the provider.
        """
        ...

    @abstractmethod
    def get_mark_label(self, event: dict) -> str:
        """
        Extract the mark label from an inbound mark acknowledgement event.

        Args:
            event: Parsed mark event dict from the provider.

        Returns:
            Label string matching the one sent in the outbound mark event.
        """
        ...
