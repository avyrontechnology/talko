from typing import Any, Dict, List, Optional

from bson import ObjectId

from src.components.partner_config.repository import PartnerConfigRepository
from src.components.vendor_config.repository import VendorConfigRepository
from src.loggers.holler_service_logger import HollerServiceLogger


class DidValidator:
    """
    Validator class for DID-related operations.
    """

    def __init__(
        self,
        vendor_config_repository: VendorConfigRepository,
        partner_config_repository: PartnerConfigRepository,
        logger: HollerServiceLogger,
    ) -> None:
        """
        Initialize the validator with necessary dependencies.

        :param vendor_config_repository: Repository for vendor config operations.
        :param partner_config_repository: Repository for partner config operations.
        :param logger: Logger instance for logging validation actions.
        """
        self.vendor_config_repository: VendorConfigRepository = vendor_config_repository
        self.partner_config_repository: PartnerConfigRepository = (
            partner_config_repository
        )
        self.logger: HollerServiceLogger = logger

    async def validate_did_assignment(self, did_data: Dict[str, Any]) -> None:
        """
        Validate the data for assigning a DID.

        :param did_data: Dictionary containing DID assignment details.
            Expected keys: "vendor_id" (str), "partner_id" (int), "did_number" (str)
        :raises ValueError: If validation fails.
        """
        try:
            self.logger.info(
                "Validating DID assignment for DID: {}".format(
                    did_data.get("did_number")
                )
            )

            # Validate vendor_id
            try:
                vendor_id: ObjectId = ObjectId(did_data["vendor_id"])
            except Exception:
                raise ValueError("Invalid vendor_id format.")

            # Check if vendor config exists
            vendor_configs: List[Dict[str, Any]] = (
                await self.vendor_config_repository.find_configs_by_vendor_id(vendor_id)
            )
            if not vendor_configs:
                raise ValueError(
                    "Vendor config not found for vendor_id: {}".format(
                        did_data["vendor_id"]
                    )
                )

            # Check if partner config exists (optional for default assignment)
            partner_id: int = did_data.get("partner_id", 0)
            if partner_id != 0:  # Allow placeholder partner_id=0 for default
                partner_config: Optional[Dict[str, Any]] = (
                    await self.partner_config_repository.find_partner_config_by_id(
                        partner_id
                    )
                )
                if not partner_config:
                    raise ValueError(
                        "Partner config not found for partner_id: {}".format(partner_id)
                    )

            self.logger.info(
                "DID assignment validation successful for DID: {}".format(
                    did_data.get("did_number")
                )
            )
        except Exception as e:
            self.logger.error("Failed to validate DID assignment: {}".format(str(e)))
            raise
