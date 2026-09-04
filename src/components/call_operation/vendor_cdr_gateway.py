from typing import Any, Dict, Optional

from src.components.call_operation.cdr_update import CDRUpdateTask
from src.exceptions import BadRequestError
from src.loggers.holler_service_logger import HollerServiceLogger


class VendorCDRGateway:
    """
    Vendor CDR Gateway - Central dispatcher for fetching call details.

    This gateway makes the system extensible:
    - When a new vendor is added in future, create a new *CDRUpdateTask class
      and register it here. No changes needed in controller or API.
    """

    def __init__(
        self,
        cdr_update_task: CDRUpdateTask,
        logger: HollerServiceLogger,
    ):
        self.__cdr_update_task = cdr_update_task
        self.__logger = logger

        # Registry for different vendors
        self._handlers = {
            "tata_tele": self._handle_tata_tele,
            # Future vendors can be added here:
            # "acefone": self._handle_acefone,
            # "new_vendor": self._handle_new_vendor,
        }

    async def fetch_call_details(
        self,
        call_id: Optional[str],
        call_uuid: Optional[str],
        vendor_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Main entry point for the API.

        Args:
            call_id: (easy to extend) Call ID from vendor
            vendor_config: Full vendor config fetched using vendor_config_id

        Returns:
            Standardized response with raw_payload and processed_result
        """
        try:
            vendor_type: str = vendor_config.get("vendor_type")
            if not vendor_type:
                self.__logger.error("vendor_type missing in vendor_config")
                raise BadRequestError("vendor_type missing in vendor configuration")

            cdr_config: Dict[str, Any] = vendor_config.get("cdr_url_handler", {})
            if not cdr_config:
                self.__logger.error(
                    "cdr_url_handler missing for vendor_type: {}".format(vendor_type)
                )
                raise BadRequestError("CDR configuration missing")

            self.__logger.info(
                "Routing call details request for call_id={}, call_uuid={} to vendor_type={}".format(
                    call_id, call_uuid, vendor_type
                )
            )

            # Route to appropriate handler
            handler = self._handlers.get(vendor_type)
            if not handler:
                self.__logger.error("Unsupported vendor_type: {}".format(vendor_type))
                raise BadRequestError("Unsupported vendor: {}".format(vendor_type))

            return await handler(call_id, call_uuid, cdr_config, vendor_type)

        except Exception as e:
            self.__logger.error("Error in VendorCDRGateway: {}".format(str(e)))
            raise

    # Vendor Specific Handlers

    async def _handle_tata_tele(
        self,
        call_id: Optional[str],
        call_uuid: Optional[str],
        cdr_config: Dict[str, Any],
        vendor_type: str,
    ) -> Dict[str, Any]:
        """Handle Tata Tele using existing CDRUpdateTask"""
        self.__logger.debug("Using TataTele handler via CDRUpdateTask")

        return await self.__cdr_update_task.fetch_single_cdr(
            call_id=call_id,
            call_uuid=call_uuid,
            cdr_config=cdr_config,
            vendor_type=vendor_type,
        )

    # Future vendor handlers can be added here like this:
    # async def _handle_acefone(self, call_id: str, cdr_config: Dict, vendor_type: str):
    #     return await self.acefone_task.fetch_single_cdr(...)
