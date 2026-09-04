from src.components.vendor.dto import TalkoContract
from src.components.vendor.repository import TalkoVendorRepository
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.common_validation import validate_required_fields


class TalkoVendorValidator:
    """
    Validator class for validating vendor-related input data.
    Ensures that required fields are present and business rules are enforced.
    """

    def __init__(self, repository: TalkoVendorRepository, logger: TalkoServiceLogger):
        """
        Initialize the TalkoVendorValidator.

        Args:
            repository (TalkoVendorRepository): Repository for checking existing vendor records.
            logger (TalkoServiceLogger): Logger instance for logging validation activities.
        """
        self.repository = repository
        self.logger = logger

    async def validate_vendor_create(self, vendor: TalkoContract.VendorCreate):
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
