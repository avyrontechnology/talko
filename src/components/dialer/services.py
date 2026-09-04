from typing import Any, Dict, List, Optional

import httpx
from bson import ObjectId

from src.components.dialer import messages as dialer_messages
from src.components.dialer.dto import Contract
from src.components.partner_config.repository import PartnerConfigRepository
from src.components.vendor_config.repository import VendorConfigRepository
from src.exceptions import BadRequestError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger


class DialerService:
    """
    Service layer responsible for interfacing with external Dialer vendors (e.g., Tata Tele).
    Handles configuration retrieval, authentication, and lead management.
    """

    def __init__(
        self,
        partner_config_repository: PartnerConfigRepository,
        vendor_config_repository: VendorConfigRepository,
        logger: HollerServiceLogger,
    ):
        """
        Initializes the DialerService with required repositories and logger.

        Args:
            partner_config_repository: Repo for partner-specific settings.
            vendor_config_repository: Repo for global vendor API configurations.
            logger: Specialized logger for the Holler service.
        """
        self.__partner_config_repository: PartnerConfigRepository = (
            partner_config_repository
        )
        self.__vendor_config_repository: VendorConfigRepository = (
            vendor_config_repository
        )
        self.__logger: HollerServiceLogger = logger
        self.client = httpx.AsyncClient(
            timeout=15.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    async def fetch_lead_lists(self, partner_id: int) -> Dict[str, Any]:
        """
        Fetches available lead lists from the dialer vendor for a specific partner.

        Logic Flow:
        1. Validate partner's dialer status.
        2. Fetch vendor API credentials and endpoints.
        3. Execute GET request to vendor API.
        4. Validate and clean the response using Contract DTOs.

        Args:
            partner_id (int): The unique ID of the partner.

        Returns:
            List[Dict]: A list of validated lead list objects.

        Raises:
            BadRequestError: If dialer is disabled, config is missing, or API fails.
            ResourceNotFound: If vendor configuration does not exist.
        """
        self.__logger.info("Fetch lead list service method started.")

        partner_config: Optional[Dict[str, Any]] = (
            await self.__partner_config_repository.find_partner_config_by_partner_id(
                partner_id
            )
        )
        if not partner_config or not partner_config.get("dialer_enabled", False):
            raise BadRequestError(dialer_messages.DIALER_NOT_ENABLED)

        self.__logger.debug("Partner config found for partner_id {}".format(partner_id))
        vendor_config_id_str: Optional[str] = partner_config.get("vendor_config_id")
        if not vendor_config_id_str:
            self.__logger.error(
                "No vendor_config_id found for partner {}".format(partner_id)
            )
            raise BadRequestError(
                dialer_messages.NO_VENDOR_CONFIGURATION_LINKED_PARTNER
            )

        try:
            vendor_config_id: ObjectId = ObjectId(vendor_config_id_str)
        except Exception as e:
            self.__logger.error(
                "Invalid vendor_config_id format: {} - {}".format(
                    vendor_config_id_str, str(e)
                )
            )
            raise BadRequestError(
                dialer_messages.INVALID_VENDOR_CONFIGURATION_ID_FORMAT
            )

        vendor_config: Optional[Dict[str, Any]] = (
            await self.__vendor_config_repository.find_config_by_id(vendor_config_id)
        )
        if not vendor_config:
            self.__logger.error(
                "Vendor config not found for ID: {}".format(vendor_config_id)
            )
            raise ResourceNotFound(dialer_messages.VENDOR_CONFIGURATION_NOT_FOUND)

        self.__logger.debug(
            "Fetch lead list vendor config data: {}".format(vendor_config)
        )
        dialer_handler: Dict[str, Any] = vendor_config.get("dialer_url_handler", {})
        if not dialer_handler:
            self.__logger.error(
                "No dialer_url_handler in vendor config {}".format(vendor_config_id)
            )
            raise BadRequestError(
                dialer_messages.DIALER_URL_HANDLER_CONFIGURATION_MISSING
            )

        handler: Optional[Dict[str, Any]] = dialer_handler.get("lead_lists_fetch")
        if not handler:
            self.__logger.error(
                "No 'lead_lists_fetch' handler found in dialer_url_handler"
            )
            raise BadRequestError(
                dialer_messages.LEAD_LISTS_FETCH_CONFIGURATION_NOT_FOUND
            )

        url: Optional[str] = handler.get("endpoint")
        if not url:
            self.__logger.error("fetch lead list url missing")
            raise BadRequestError(
                dialer_messages.MISSING_ENDPOINT_IN_LEAD_LISTS_FETCH_CONFIGURATION
            )

        headers: Dict[str, str] = handler.get("headers", {}).copy()
        if handler.get("auth_type") == "bearer":
            token: Optional[str] = handler.get("auth_credentials", {}).get("token")
            if token:
                headers["Authorization"] = "Bearer {}".format(token)
            else:
                self.__logger.error("Fetch lead list missing bearer token.")
                raise BadRequestError(
                    dialer_messages.MISSING_BEARER_TOKEN_IN_VENDOR_CONFIG_CREDENTIALS
                )

        try:
            self.__logger.info("Calling Tata API: GET {}".format(url))
            response: httpx.Response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            raw_data: dict = response.json()

            validated_lists: List[Dict[str, Any]] = []
            for item in raw_data:
                cleaned_item: Dict[str, Any] = {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "field_map": item.get("field_map", []),
                }

                validated_item: Contract.LeadListItem = Contract.LeadListItem(
                    **cleaned_item
                )
                validated_lists.append(validated_item.model_dump())

            self.__logger.info(
                "Successfully validated {} lead lists".format(len(validated_lists))
            )
            return validated_lists

        except httpx.HTTPError as e:
            self.__logger.error(
                "Tata API error (fetch lists): {} - URL: {}".format(str(e), url)
            )
            raise BadRequestError(
                dialer_messages.FAILED_TO_FETCH_LEAD_LISTS_FROM_TATA.format(str(e))
            )
        except Exception as e:
            self.__logger.error(
                "Unexpected error processing lead lists: {}".format(str(e)),
            )
            raise BadRequestError(
                dialer_messages.INTERNAL_ERROR_WHILE_PROCESSING_LEAD_LISTS.format(
                    str(e)
                )
            )

    async def bulk_create_leads(
        self, partner_id: int, list_id: str, payload: Dict
    ) -> Dict[str, Any]:
        """
        Uploads multiple leads to a specific lead list on the dialer platform.

        Args:
            partner_id (int): ID of the partner performing the upload.
            list_id (str): The vendor-side ID of the list to add leads to.
            payload (Dict): Dictionary containing 'data' key with a list of lead objects.

        Returns:
            Dict: The JSON response from the vendor API.

        Raises:
            BadRequestError: If input data is invalid or the API call fails.
        """
        try:
            self.__logger.info(
                "Bulk create leads in the specified lead list service method started."
            )
            partner_config: Optional[Dict[str, Any]] = (
                await self.__partner_config_repository.find_partner_config_by_partner_id(
                    partner_id
                )
            )
            if not partner_config or not partner_config.get("dialer_enabled", False):
                self.__logger.error(
                    "Dialer is not enabled for this partner: {}".format(partner_id)
                )
                raise BadRequestError(dialer_messages.DIALER_NOT_ENABLED)

            self.__logger.debug(
                "Bulk create leads partner config data: {}".format(partner_config)
            )

            vendor_config_id: ObjectId = ObjectId(partner_config["vendor_config_id"])
            vendor_config: Optional[Dict[str, Any]] = (
                await self.__vendor_config_repository.find_config_by_id(
                    vendor_config_id
                )
            )
            dialer_handler: Dict[str, Any] = vendor_config.get("dialer_url_handler", {})
            if not dialer_handler:
                self.__logger.error(
                    "No dialer_url_handler in vendor config {}".format(vendor_config_id)
                )
                raise BadRequestError(
                    dialer_messages.DIALER_URL_HANDLER_CONFIGURATION_MISSING
                )

            self.__logger.debug(
                "Bulk create leads vendor config id: {}, vendor config: {}, dialer handler: {}".format(
                    vendor_config_id, vendor_config, dialer_handler
                )
            )

            handler: Optional[Dict[str, Any]] = dialer_handler.get("bulk_leads_create")
            if not handler:
                self.__logger.error(
                    "No 'bulk_leads_create' handler found in dialer_url_handler"
                )
                raise BadRequestError(
                    dialer_messages.BULK_LEADS_CREATION_CONFIGURATION_NOT_FOUND
                )

            url: str = handler["endpoint"].format(id=list_id)
            headers: Dict[str, str] = handler.get("headers", {}).copy()
            if handler.get("auth_type") == "bearer":
                token: Optional[str] = handler["auth_credentials"].get("token")
                if token:
                    headers["Authorization"] = "Bearer {}".format(token)
                else:
                    raise BadRequestError(
                        "Missing bearer token in vendor config credentials."
                    )

            # Validate payload structure (extra safety)
            if "data" not in payload or not payload["data"]:
                self.__logger.error(
                    "Data array is required and cannot be empty, data: {}".format(
                        payload
                    )
                )
                raise BadRequestError(dialer_messages.NO_DATA_PROVIDED_FOR_BULK_CREATE)

            # Validate each lead individually
            for index, lead in enumerate(payload["data"]):
                if not isinstance(lead, dict):
                    raise BadRequestError(
                        "Lead at index {} must be an object (dictionary).".format(index)
                    )

                if (
                    "field_0" not in lead
                    or not isinstance(lead["field_0"], str)
                    or not lead["field_0"].strip()
                ):
                    raise BadRequestError(
                        dialer_messages.EACH_LEAD_MUST_CONTAIN_FIELD_0
                    )

            # Optional: Validate duplicate_option early
            duplicate_option: str = payload.get("duplicate_option", "skip")
            allowed_options: set = {"skip", "overwrite", "clone"}
            if duplicate_option not in allowed_options:
                raise BadRequestError(
                    "Invalid 'duplicate_option': '{}'. ".format(duplicate_option)
                    + "Must be one of: {}".format(", ".join(allowed_options))
                )

            self.__logger.debug(
                "Bulk create leads payload prepared: {}".format(payload)
            )

            try:
                response: httpx.Response = await self.client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result: dict = response.json()
                self.__logger.debug(
                    "Bulk create leads service method ended successfully, data: {}".format(
                        response.json()
                    )
                )

                result: Dict[str, Any] = response.json()
                self.__logger.info(
                    "Bulk create leads service method ended successfully"
                )

                return result
            except httpx.HTTPError as e:
                self.__logger.error(
                    "Tata bulk leads error: {} - payload: {}".format(str(e), payload)
                )
                raise BadRequestError(
                    dialer_messages.FAILED_TO_CREATE_BULK_LEADS.format(str(e))
                )

        except Exception as e:
            self.__logger.error(
                "Unexpected error processing in bulk lead upload: {}".format(str(e)),
            )
            raise BadRequestError(
                dialer_messages.INTERNAL_ERROR_WHILE_PROCESSING_BULK_LEADS.format(
                    str(e)
                )
            )
