from abc import ABC, abstractmethod
from typing import Union

from src.loggers.holler_service_logger import HollerServiceLogger


class VendorCallHandler(ABC):
    """
    Base class for vendor call handlers.

    Handles config setup and defines the interface for making calls.
    """

    def __init__(self, config: dict, logger: HollerServiceLogger, vendor_type: str):
        self.vendor_config: dict = config
        self.config: dict = config.get("generic_url_handler", {}).get("call_api", {})
        self.logger: HollerServiceLogger = logger
        self.vendor_type: str = vendor_type

    @abstractmethod
    async def make_call(
        self,
        to_number: str,
        from_number: str,
        call_url: Union[str, None],
        agent_number: Union[str, None],
    ) -> dict:
        """
        Make a call using the vendor's API.

        Args:
            to_number: Number to call.
            from_number: Caller ID.
            call_url: Optional IVR/call flow URL.
            agent_number: Optional agent number.

        Returns:
            dict: Vendor API response.
        """
        pass  # pragma: no cover

    @abstractmethod
    async def hangup_call(self, call_id: str) -> dict:
        """
        Hang up an ongoing call using the vendor's API.

        Args:
            call_id: Vendor's identifier for the call to hang up.

        Returns:
            dict: Vendor API response.
        """
        pass  # pragma: no cover

    @abstractmethod
    async def transfer_call(self, call_id: str, destination_number: str) -> dict:
        """
        Transfer an in-progress call using the vendor's API.

        Args:
            call_id: Vendor's identifier for the in-progress call.
            destination_number: Number to transfer the call to.

        Returns:
            dict: Vendor API response.
        """
        pass  # pragma: no cover
