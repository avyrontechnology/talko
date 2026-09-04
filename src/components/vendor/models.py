from src.utils.enums import VendorType
from src.utils.timestamped_model import TimestampedModel


class VendorModel(TimestampedModel):
    name: str  # Vendor name
    slug: str  # Unique vendor slug
    is_active: bool  # Active status
    vendor_type: VendorType  # Type of vendor

    class CollectionName:
        VENDOR = "vendor"  # Collection name
