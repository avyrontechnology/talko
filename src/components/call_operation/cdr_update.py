from typing import Any, Dict, List, Optional

import aiohttp
from bson import ObjectId

from src.components.call_management.repository import TalkoCallRepository
from src.components.call_management.tata_tele.call_webhook import TalkoTataTeleWebhookHandler
from src.components.cdr.repository import TalkoCDRRepository
from src.components.vendor_config.repository import TalkoVendorConfigRepository
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil


class TalkoCDRUpdateTask:
    """
    Encapsulates logic for updating incomplete CDRs for a specific vendor.
    """

    def __init__(
        self,
        cdr_repository: TalkoCDRRepository,
        vendor_config_repository: TalkoVendorConfigRepository,
        call_repository: TalkoCallRepository,
        logger: TalkoServiceLogger,
    ) -> None:
        """
        Initialize the TalkoCDR update task.

        Args:
            cdr_repository: Repository for accessing TalkoCDR records.
            vendor_config_repository: Repository for accessing vendor config.
            call_repository: Repository for accessing call records.
            logger: Logger instance for logging task details.
        """
        self.__cdr_repository: TalkoCDRRepository = cdr_repository
        self.__vendor_config_repository: TalkoVendorConfigRepository = (
            vendor_config_repository
        )
        self.__call_repository: TalkoCallRepository = call_repository
        self.__logger: TalkoServiceLogger = logger
        self.__datetime_util: TalkoDateTimeUtil = TalkoDateTimeUtil
        self.__vendor_type: str = ""

    # Config fetching

    async def fetch_vendor_config(self) -> Dict[str, Any]:
        """
        Fetch vendor configuration from the repository using self.__vendor_type.

        Returns:
            Dict[str, Any]: The first matching vendor configuration document.

        Raises:
            TalkoResourceNotFound: If no vendor config is found.
        """
        self.__logger.info(
            "Fetching vendor config for cdr update task: {}".format(self.__vendor_type)
        )
        vendor_config: List[Dict[str, Any]] = (
            await self.__vendor_config_repository.get_vendor_config_by_vendor_type(
                vendor_type=self.__vendor_type
            )
        )
        self.__logger.debug(
            "Vendor config fetched for cdr update task: {}".format(vendor_config)
        )
        if not vendor_config:
            self.__logger.error(
                "Vendor config not found for vendor_type: {}".format(self.__vendor_type)
            )
            raise TalkoResourceNotFound(
                "Vendor config not found for vendor_type: {}".format(self.__vendor_type)
            )
        return vendor_config[0]

    async def fetch_vendor_config_by_id(self, vendor_config_id: str) -> Dict[str, Any]:
        """
        Fetch a single vendor configuration document by its ID.

        Args:
            vendor_config_id: The document _id of the vendor config.

        Returns:
            Dict[str, Any]: The vendor configuration document.

        Raises:
            TalkoResourceNotFound: If the vendor config is not found.
        """
        self.__logger.info("Fetching vendor config by id: {}".format(vendor_config_id))
        vendor_config: Optional[Dict[str, Any]] = (
            await self.__vendor_config_repository.find_config_by_id(
                ObjectId(vendor_config_id)
            )
        )
        if not vendor_config:
            self.__logger.error(
                "Vendor config not found for id: {}".format(vendor_config_id)
            )
            raise TalkoResourceNotFound(
                "Vendor config not found for id: {}".format(vendor_config_id)
            )
        return vendor_config

    # TalkoCDR fetching (from vendor API)
    async def fetch_cdr_data(
        self, identifier: str, cdr_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fetch TalkoCDR data from the vendor's API.

        Args:
            identifier: Call ID or UUID for the TalkoCDR.
            cdr_config: TalkoCDR API configuration from vendor_config.

        Returns:
            Dict[str, Any]: API response payload.

        Raises:
            TalkoBadRequestError: If the API request fails or config is invalid.
        """
        self.__logger.info(
            "Fetch cdr data in task started for identifier: {}".format(identifier)
        )
        cdr_api_url: Optional[str] = cdr_config.get("endpoint")
        auth_type: Optional[str] = cdr_config.get("auth_type")
        auth_credentials: Dict[str, str] = cdr_config.get("auth_credentials", {})
        headers: Dict[str, str] = cdr_config.get("headers", {})
        param_key: str = cdr_config.get("param_key", "call_id")

        if not cdr_api_url or not auth_credentials.get("token"):
            self.__logger.error("Missing TalkoCDR API URL or auth token in vendor config")
            raise TalkoBadRequestError("Invalid vendor config")

        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {auth_credentials['token']}"

        params: Dict[str, str] = {param_key: identifier}

        self.__logger.debug("Task fetch cdr data params: {}".format(params))
        async with aiohttp.ClientSession() as session:
            async with session.get(
                cdr_api_url, params=params, headers=headers
            ) as response:
                if response.status != 200:
                    self.__logger.error(
                        "API fetch failed for {}: status={}".format(
                            identifier, response.status
                        )
                    )
                    raise TalkoBadRequestError(
                        "Failed to fetch TalkoCDR for {}".format(identifier)
                    )
                payload: Dict[str, Any] = await response.json()
                self.__logger.info(
                    "Fetched TalkoCDR data for {}: {}".format(identifier, response)
                )
                return payload

    # TalkoCDR DB queries
    async def get_incomplete_cdrs(self, vendor_type: str) -> List[Dict[str, Any]]:
        """
        Fetch incomplete CDRs across all configs for a vendor_type.

        Args:
            vendor_type: Vendor identifier (e.g., 'tata_tele').

        Returns:
            List[Dict[str, Any]]: List of incomplete TalkoCDR documents.
        """
        self.__logger.info(
            "Get incomplete cdr records for vendor_type: {}".format(vendor_type)
        )
        query: Dict[str, Any] = {
            "$or": [{"call_status": {"$in": ["initiated"]}}],
        }
        cdrs: List[Dict[str, Any]] = await self.__cdr_repository.get_cdrs_by_criteria(
            query
        )
        return cdrs

    async def get_incomplete_cdrs_for_config(
        self, vendor_config_id: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch incomplete CDRs scoped to a specific vendor_config_id.

        This ensures that when multiple vendor configs exist for the same
        vendor_type, each worker only processes its own CDRs without overlap.

        Args:
            vendor_config_id: The specific vendor config document ID.

        Returns:
            List[Dict[str, Any]]: List of incomplete TalkoCDR documents for this config.
        """
        self.__logger.info(
            "Get incomplete cdrs for vendor_config_id: {}".format(vendor_config_id)
        )
        query: Dict[str, Any] = {
            "vendor_config_id": vendor_config_id,
            "$or": [{"call_status": {"$in": ["initiated"]}}],
        }
        cdrs: List[Dict[str, Any]] = await self.__cdr_repository.get_cdrs_by_criteria(
            query
        )
        return cdrs

    # Execute methods
    async def execute_for_config(
        self,
        vendor_config_id: str,
        vendor_type: str,
        chunk_size: int = 20,
    ) -> str:
        """
        Process all incomplete CDRs for a single vendor_config_id, in chunks.

        This is the primary execution path used by the Celery worker task.
        CDRs are fetched and processed in batches of `chunk_size` to keep
        each task short-lived and prevent worker timeout crashes.

        Multi-config support: scoping by vendor_config_id ensures that when
        one vendor_type maps to multiple vendor configs, each worker processes
        only its own records without cross-config duplication or skipping.

        Args:
            vendor_config_id: The specific vendor config document ID.
            vendor_type: Vendor identifier, used for handler initialization.
            chunk_size: Number of CDRs to process per iteration.

        Returns:
            str: Summary of updated TalkoCDR count vs total.
        """
        self.__vendor_type = vendor_type
        self.__logger.info(
            "execute_for_config started: vendor_config_id={}, vendor_type={}, chunk_size={}".format(
                vendor_config_id, vendor_type, chunk_size
            )
        )

        # Fetch the specific config by ID — avoids any [0] ambiguity
        vendor_config: Dict[str, Any] = await self.fetch_vendor_config_by_id(
            vendor_config_id
        )

        cdr_config: Dict[str, Any] = vendor_config.get("cdr_url_handler", {})
        if not cdr_config:
            self.__logger.error(
                "cdr_url_handler missing in vendor_config: {}".format(vendor_config_id)
            )
            raise TalkoBadRequestError(
                "TalkoCDR config missing in vendor_config: {}".format(vendor_config_id)
            )

        self.__logger.debug(
            "TalkoCDR config for vendor_config_id {}: {}".format(
                vendor_config_id, cdr_config
            )
        )

        # Fetch CDRs scoped strictly to this vendor_config_id
        cdrs: List[Dict[str, Any]] = await self.get_incomplete_cdrs_for_config(
            vendor_config_id
        )
        if not cdrs:
            self.__logger.info(
                "No incomplete CDRs for vendor_config_id: {}".format(vendor_config_id)
            )
            return "No updates needed"

        total: int = len(cdrs)
        self.__logger.info(
            "Found {} incomplete TalkoCDR(s) for vendor_config_id: {}".format(
                total, vendor_config_id
            )
        )

        handler: TalkoTataTeleWebhookHandler = TalkoTataTeleWebhookHandler(
            logger=self.__logger,
            call_repository=self.__call_repository,
            vendor_type=vendor_type,
        )
        updated_count: int = 0

        # Process in chunks to keep the task short-lived
        for chunk_start in range(0, total, chunk_size):
            chunk: List[Dict[str, Any]] = cdrs[chunk_start : chunk_start + chunk_size]
            self.__logger.info(
                "Processing chunk {}/{} ({} CDRs) for vendor_config_id: {}".format(
                    chunk_start // chunk_size + 1,
                    (total + chunk_size - 1) // chunk_size,
                    len(chunk),
                    vendor_config_id,
                )
            )
            for cdr in chunk:
                call_id: Optional[str] = cdr.get("call_id")
                uuid_val: Optional[str] = cdr.get("call_uuid")

                if not call_id:
                    self.__logger.warning(
                        "Skipping TalkoCDR with no call_id: {}".format(cdr)
                    )
                    continue

                try:
                    payload: Dict[str, Any] = await self.fetch_cdr_data(
                        call_id, cdr_config
                    )
                    self.__logger.debug(
                        "Payload for call_id {}: {}".format(call_id, payload)
                    )
                    result: Dict[str, Any] = await handler.process_cdr_api_payload(
                        payload, call_id, uuid_val
                    )
                    if result.get("status") == "success":
                        updated_count += 1
                        self.__logger.info(
                            "Updated TalkoCDR for call_id: {}".format(result.get("call_id"))
                        )
                except Exception as e:
                    self.__logger.error(
                        "Failed to update TalkoCDR for call_id {}: {}".format(
                            call_id, str(e)
                        )
                    )

        self.__logger.info(
            "execute_for_config completed: {}/{} CDRs updated for vendor_config_id: {}".format(
                updated_count, total, vendor_config_id
            )
        )
        return "Updated {}/{} CDRs".format(updated_count, total)

    async def execute(self, vendor_type: str) -> str:
        """
        Execute the TalkoCDR update task for the specified vendor.

        Args:
            vendor_type: Vendor identifier (e.g., 'tata_tele').

        Returns:
            str: Task completion message.
        """
        try:
            self.__vendor_type = vendor_type
            self.__logger.info(
                "Starting TalkoCDR update task (legacy execute) for vendor_type: {}".format(
                    self.__vendor_type
                )
            )

            # Fetch vendor config
            # when multiple configs exist for the same vendor_type)
            vendor_config: Dict[str, Any] = await self.fetch_vendor_config()
            cdr_config: Dict[str, Any] = vendor_config.get("cdr_url_handler", {})

            if not cdr_config:
                self.__logger.error(
                    "TalkoCDR config missing in vendor config for vendor_type: {}".format(
                        self.__vendor_type
                    )
                )
                raise TalkoBadRequestError(
                    "TalkoCDR config missing in vendor config for vendor_type: {}".format(
                        self.__vendor_type
                    )
                )

            self.__logger.debug("TalkoCDR Config cdr update task: {}".format(cdr_config))

            # Fetch incomplete CDRs (unscoped — all configs for this vendor_type)
            cdrs: List[Dict[str, Any]] = await self.get_incomplete_cdrs(vendor_type)
            if not cdrs:
                self.__logger.info("No incomplete CDRs found")
                return "No updates needed"

            self.__logger.debug("Incomplete CDRs found: {}".format(len(cdrs)))

            handler: TalkoTataTeleWebhookHandler = TalkoTataTeleWebhookHandler(
                logger=self.__logger,
                call_repository=self.__call_repository,
                vendor_type=vendor_type,
            )
            updated_count: int = 0

            for cdr in cdrs:
                self.__logger.debug("Processing TalkoCDR: {}".format(cdr))
                call_id: Optional[str] = cdr.get("call_id")
                uuid_val: Optional[str] = cdr.get("call_uuid")
                identifier: Optional[str] = call_id if call_id else None
                try:
                    payload: Dict[str, Any] = await self.fetch_cdr_data(
                        identifier, cdr_config
                    )
                    self.__logger.debug(
                        "Payload for processing TalkoCDR: {}".format(payload)
                    )
                    result: Dict[str, Any] = await handler.process_cdr_api_payload(
                        payload, call_id, uuid_val
                    )
                    if result.get("status") == "success":
                        updated_count += 1
                        self.__logger.info(
                            "Updated TalkoCDR for call_id: {}".format(result.get("call_id"))
                        )
                except Exception as e:
                    self.__logger.error(
                        "Failed to update TalkoCDR {}: {}".format(identifier, str(e))
                    )

            self.__logger.info(
                "Task completed: Updated {}/{} CDRs".format(updated_count, len(cdrs))
            )
            return "Updated {} CDRs".format(updated_count)

        except Exception as e:
            self.__logger.error(
                "Error in TalkoCDR update task for vendor_type {}: {}".format(
                    self.__vendor_type, str(e)
                )
            )
            raise

    # Single TalkoCDR fetch (API path)
    async def fetch_single_cdr(
        self,
        call_id: Optional[str] = None,
        call_uuid: Optional[str] = None,
        cdr_config: Optional[Dict[str, Any]] = None,
        vendor_type: str = "tata_tele",
    ) -> Dict[str, Any]:
        """
        Fetch and process a single TalkoCDR by call_id, call_uuid.

        Designed for the API path (using vendor_config_id lookup) while
        maintaining full backward compatibility with the cron job path.

        If cdr_config is provided (from a vendor_config_id lookup), it is
        used directly. Otherwise falls back to fetching config via vendor_type.

        Args:
            call_id: The call ID to fetch and process.
            cdr_config: Optional pre-fetched TalkoCDR config from vendor_config_id
                        lookup. If None, config is fetched by vendor_type.
            vendor_type: Vendor identifier, used when cdr_config is None and
                         for handler initialization.

        Returns:
            Dict[str, Any]: Result containing status, raw payload, and processed result.
        """
        try:
            self.__logger.info(
                "Fetch single TalkoCDR called with call_id: {}, call_uuid: {}, vendor_type: {}".format(
                    call_id, call_uuid, vendor_type
                )
            )
            # If no pre-fetched config is passed, fetch it (cron job path)
            if cdr_config is None:
                self.__vendor_type = vendor_type
                self.__logger.info(
                    "Fetching vendor config for single TalkoCDR (vendor_type: {})".format(
                        vendor_type
                    )
                )
                vendor_config: Dict[str, Any] = await self.fetch_vendor_config()
                cdr_config = vendor_config.get("cdr_url_handler", {})

            if not cdr_config:
                self.__logger.error("TalkoCDR config missing in vendor config")
                raise TalkoBadRequestError("TalkoCDR config missing in vendor config")

            identifier: str = call_uuid if call_uuid is not None else call_id
            identifier_type: str = "call_uuid" if call_uuid is not None else "call_id"

            self.__logger.info(
                "Fetching single TalkoCDR using {}: {}".format(identifier_type, identifier)
            )

            payload: Dict[str, Any] = await self.fetch_cdr_data(
                identifier=identifier,
                cdr_config={
                    **cdr_config,
                    "param_key": identifier_type,
                },
            )
            self.__logger.debug("Raw TalkoCDR payload received: {}".format(payload))

            # Process using the same handler as the cron job
            handler: TalkoTataTeleWebhookHandler = TalkoTataTeleWebhookHandler(
                logger=self.__logger,
                call_repository=self.__call_repository,
                vendor_type=vendor_type,
            )

            result: Dict[str, Any] = await handler.process_cdr_api_payload(
                payload, call_id, call_uuid
            )

            return {
                "status": "success",
                "call_id": call_id,
                "call_uuid": call_uuid,
                "lookup_by": identifier_type,
                "raw_payload": payload,
                "processed_result": result,
                "message": "TalkoCDR fetched and processed successfully",
            }

        except Exception as e:
            self.__logger.error(
                "Failed to fetch single TalkoCDR for call_id {}, call_uuid {}: {}".format(
                    call_id, call_uuid, str(e)
                )
            )
            raise
