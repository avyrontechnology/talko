from src.utils.enums import TalkoVendorType
from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoVendorModel(TalkoTimestampedModel):
    name: str  # Vendor name
    slug: str  # Unique vendor slug
    is_active: bool  # Active status
    vendor_type: TalkoVendorType  # Type of vendor

    class CollectionName:
        VENDOR = "vendor"  # Collection name
