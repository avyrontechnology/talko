from typing import Any

import httpx
from bson import ObjectId

from src.components.dialer import messages as dialer_messages
from src.components.dialer.dto import TalkoContract
from src.components.partner_config.repository import TalkoPartnerConfigRepository
from src.components.vendor_config.repository import TalkoVendorConfigRepository
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoDialerService:
    """
    Service layer responsible for interfacing with external Dialer vendors (e.g., Tata Tele).
    Handles configuration retrieval, authentication, and lead management.
    """

    def __init__(
        self,
        partner_config_repository: TalkoPartnerConfigRepository,
        vendor_config_repository: TalkoVendorConfigRepository,
        logger: TalkoServiceLogger,
    ):
        """
        Initializes the TalkoDialerService with required repositories and logger.

        Args:
            partner_config_repository: Repo for partner-specific settings.
            vendor_config_repository: Repo for global vendor API configurations.
            logger: Specialized logger for the Talko service.
        """
        self.__partner_config_repository: TalkoPartnerConfigRepository = partner_config_repository
        self.__vendor_config_repository: TalkoVendorConfigRepository = vendor_config_repository
        self.__logger: TalkoServiceLogger = logger
        self.client = httpx.AsyncClient(
            timeout=15.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    async def fetch_lead_lists(self, partner_id: int) -> dict[str, Any]:
        """
        Fetches available lead lists from the dialer vendor for a specific partner.

        Logic Flow:
        1. Validate partner's dialer status.
        2. Fetch vendor API credentials and endpoints.
        3. Execute GET request to vendor API.
        4. Validate and clean the response using TalkoContract DTOs.

        Args:
            partner_id (int): The unique ID of the partner.

        Returns:
            List[Dict]: A list of validated lead list objects.

        Raises:
            TalkoBadRequestError: If dialer is disabled, config is missing, or API fails.
            TalkoResourceNotFound: If vendor configuration does not exist.
        """
        self.__logger.info("Fetch lead list service method started.")

        partner_config: (
            dict[str, Any] | None
        ) = await self.__partner_config_repository.find_partner_config_by_partner_id(partner_id)
        if not partner_config or not partner_config.get("dialer_enabled", False):
            raise TalkoBadRequestError(dialer_messages.DIALER_NOT_ENABLED)

        self.__logger.debug(f"Partner config found for partner_id {partner_id}")
        vendor_config_id_str: str | None = partner_config.get("vendor_config_id")
        if not vendor_config_id_str:
            self.__logger.error(f"No vendor_config_id found for partner {partner_id}")
            raise TalkoBadRequestError(dialer_messages.NO_VENDOR_CONFIGURATION_LINKED_PARTNER)

        try:
            vendor_config_id: ObjectId = ObjectId(vendor_config_id_str)
        except Exception as e:
            self.__logger.error(f"Invalid vendor_config_id format: {vendor_config_id_str} - {str(e)}")
            raise TalkoBadRequestError(dialer_messages.INVALID_VENDOR_CONFIGURATION_ID_FORMAT)

        vendor_config: dict[str, Any] | None = await self.__vendor_config_repository.find_config_by_id(vendor_config_id)
        if not vendor_config:
            self.__logger.error(f"Vendor config not found for ID: {vendor_config_id}")
            raise TalkoResourceNotFound(dialer_messages.VENDOR_CONFIGURATION_NOT_FOUND)

        self.__logger.debug(f"Fetch lead list vendor config data: {vendor_config}")
        dialer_handler: dict[str, Any] = vendor_config.get("dialer_url_handler", {})
        if not dialer_handler:
            self.__logger.error(f"No dialer_url_handler in vendor config {vendor_config_id}")
            raise TalkoBadRequestError(dialer_messages.DIALER_URL_HANDLER_CONFIGURATION_MISSING)

        handler: dict[str, Any] | None = dialer_handler.get("lead_lists_fetch")
        if not handler:
            self.__logger.error("No 'lead_lists_fetch' handler found in dialer_url_handler")
            raise TalkoBadRequestError(dialer_messages.LEAD_LISTS_FETCH_CONFIGURATION_NOT_FOUND)

        url: str | None = handler.get("endpoint")
        if not url:
            self.__logger.error("fetch lead list url missing")
            raise TalkoBadRequestError(dialer_messages.MISSING_ENDPOINT_IN_LEAD_LISTS_FETCH_CONFIGURATION)

        headers: dict[str, str] = handler.get("headers", {}).copy()
        if handler.get("auth_type") == "bearer":
            token: str | None = handler.get("auth_credentials", {}).get("token")
            if token:
                headers["Authorization"] = f"Bearer {token}"
            else:
                self.__logger.error("Fetch lead list missing bearer token.")
                raise TalkoBadRequestError(dialer_messages.MISSING_BEARER_TOKEN_IN_VENDOR_CONFIG_CREDENTIALS)

        try:
            self.__logger.info(f"Calling Tata API: GET {url}")
            response: httpx.Response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            raw_data: dict = response.json()

            validated_lists: list[dict[str, Any]] = []
            for item in raw_data:
                cleaned_item: dict[str, Any] = {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "field_map": item.get("field_map", []),
                }

                validated_item: TalkoContract.LeadListItem = TalkoContract.LeadListItem(**cleaned_item)
                validated_lists.append(validated_item.model_dump())

            self.__logger.info(f"Successfully validated {len(validated_lists)} lead lists")
            return validated_lists

        except httpx.HTTPError as e:
            self.__logger.error(f"Tata API error (fetch lists): {str(e)} - URL: {url}")
            raise TalkoBadRequestError(dialer_messages.FAILED_TO_FETCH_LEAD_LISTS_FROM_TATA.format(str(e)))
        except Exception as e:
            self.__logger.error(
                f"Unexpected error processing lead lists: {str(e)}",
            )
            raise TalkoBadRequestError(dialer_messages.INTERNAL_ERROR_WHILE_PROCESSING_LEAD_LISTS.format(str(e)))

    async def bulk_create_leads(self, partner_id: int, list_id: str, payload: dict) -> dict[str, Any]:
        """
        Uploads multiple leads to a specific lead list on the dialer platform.

        Args:
            partner_id (int): ID of the partner performing the upload.
            list_id (str): The vendor-side ID of the list to add leads to.
            payload (Dict): Dictionary containing 'data' key with a list of lead objects.

        Returns:
            Dict: The JSON response from the vendor API.

        Raises:
            TalkoBadRequestError: If input data is invalid or the API call fails.
        """
        try:
            self.__logger.info("Bulk create leads in the specified lead list service method started.")
            partner_config: (
                dict[str, Any] | None
            ) = await self.__partner_config_repository.find_partner_config_by_partner_id(partner_id)
            if not partner_config or not partner_config.get("dialer_enabled", False):
                self.__logger.error(f"Dialer is not enabled for this partner: {partner_id}")
                raise TalkoBadRequestError(dialer_messages.DIALER_NOT_ENABLED)

            self.__logger.debug(f"Bulk create leads partner config data: {partner_config}")

            vendor_config_id: ObjectId = ObjectId(partner_config["vendor_config_id"])
            vendor_config: dict[str, Any] | None = await self.__vendor_config_repository.find_config_by_id(
                vendor_config_id
            )
            dialer_handler: dict[str, Any] = vendor_config.get("dialer_url_handler", {})
            if not dialer_handler:
                self.__logger.error(f"No dialer_url_handler in vendor config {vendor_config_id}")
                raise TalkoBadRequestError(dialer_messages.DIALER_URL_HANDLER_CONFIGURATION_MISSING)

            self.__logger.debug(
                f"Bulk create leads vendor config id: {vendor_config_id}, vendor config: {vendor_config}, dialer handler: {dialer_handler}"
            )

            handler: dict[str, Any] | None = dialer_handler.get("bulk_leads_create")
            if not handler:
                self.__logger.error("No 'bulk_leads_create' handler found in dialer_url_handler")
                raise TalkoBadRequestError(dialer_messages.BULK_LEADS_CREATION_CONFIGURATION_NOT_FOUND)

            url: str = handler["endpoint"].format(id=list_id)
            headers: dict[str, str] = handler.get("headers", {}).copy()
            if handler.get("auth_type") == "bearer":
                token: str | None = handler["auth_credentials"].get("token")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                else:
                    raise TalkoBadRequestError("Missing bearer token in vendor config credentials.")

            # Validate payload structure (extra safety)
            if "data" not in payload or not payload["data"]:
                self.__logger.error(f"Data array is required and cannot be empty, data: {payload}")
                raise TalkoBadRequestError(dialer_messages.NO_DATA_PROVIDED_FOR_BULK_CREATE)

            # Validate each lead individually
            for index, lead in enumerate(payload["data"]):
                if not isinstance(lead, dict):
                    raise TalkoBadRequestError(f"Lead at index {index} must be an object (dictionary).")

                if "field_0" not in lead or not isinstance(lead["field_0"], str) or not lead["field_0"].strip():
                    raise TalkoBadRequestError(dialer_messages.EACH_LEAD_MUST_CONTAIN_FIELD_0)

            # Optional: Validate duplicate_option early
            duplicate_option: str = payload.get("duplicate_option", "skip")
            allowed_options: set = {"skip", "overwrite", "clone"}
            if duplicate_option not in allowed_options:
                raise TalkoBadRequestError(
                    f"Invalid 'duplicate_option': '{duplicate_option}'. "
                    + "Must be one of: {}".format(", ".join(allowed_options))
                )

            self.__logger.debug(f"Bulk create leads payload prepared: {payload}")

            try:
                response: httpx.Response = await self.client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result: dict = response.json()
                self.__logger.debug(f"Bulk create leads service method ended successfully, data: {response.json()}")

                result: dict[str, Any] = response.json()
                self.__logger.info("Bulk create leads service method ended successfully")

                return result
            except httpx.HTTPError as e:
                self.__logger.error(f"Tata bulk leads error: {str(e)} - payload: {payload}")
                raise TalkoBadRequestError(dialer_messages.FAILED_TO_CREATE_BULK_LEADS.format(str(e)))

        except Exception as e:
            self.__logger.error(
                f"Unexpected error processing in bulk lead upload: {str(e)}",
            )
            raise TalkoBadRequestError(dialer_messages.INTERNAL_ERROR_WHILE_PROCESSING_BULK_LEADS.format(str(e)))
