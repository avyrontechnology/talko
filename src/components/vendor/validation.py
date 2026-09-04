from src.components.vendor.dto import Contract
from src.components.vendor.repository import VendorRepository
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.common_validation import validate_required_fields


class VendorValidator:
    """
    Validator class for validating vendor-related input data.
    Ensures that required fields are present and business rules are enforced.
    """

    def __init__(self, repository: VendorRepository, logger: HollerServiceLogger):
        """
        Initialize the VendorValidator.

        Args:
            repository (VendorRepository): Repository for checking existing vendor records.
            logger (HollerServiceLogger): Logger instance for logging validation activities.
        """
        self.repository = repository
        self.logger = logger

    async def validate_vendor_create(self, vendor: Contract.VendorCreate):
        """Validate VendorCreate data."""
        # Check required fields
        required_fields = ["name", "vendor_type"]
        validate_required_fields(vendor.model_dump(), required_fields, self.logger)

        # Check for duplicate vendor_type
        existing_vendor_type = await self.repository.find_vendor_by_type(
            vendor.vendor_type.value, vendor.name
        )
        if existing_vendor_type:
            self.logger.error(
                "Vendor with type {} and name {} already exists.".format(
                    vendor.vendor_type.value, vendor.name
                )
            )
            raise ValueError("Vendor already exists.")
