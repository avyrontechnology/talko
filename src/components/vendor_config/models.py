from typing import Any, Dict, Optional

from bson import ObjectId
from pydantic import ConfigDict, Field

from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoVendorConfigModel(TalkoTimestampedModel):
    name: str  # Name of the vendor configuration
    vendor_id: ObjectId  # Vendor identifier
    generic_url_handler: Dict[str, Any]  # Config for generic URL handling
    cdr_url_handler: Optional[Dict[str, Any]] = Field(
        None, description="Config for TalkoCDR API endpoint"
    )  # TalkoCDR URL handler config
    dialer_url_handler: Optional[Dict[str, Any]] = Field(
        None, description="Config for dialer APIs"
    )
    c2c_support_url_handler: Optional[Dict[str, Any]] = Field(
        None,
        description="Tata Tele Click-to-Call Support API config (endpoint, api_key, payload)",
    )
    hangup_url_handler: Optional[Dict[str, Any]] = Field(
        None,
        description="Config for vendor call hangup API endpoint (endpoint, auth_type, auth_credentials, headers)",
    )
    transfer_url_handler: Optional[Dict[str, Any]] = Field(
        None,
        description="Config for call transfer API endpoint",
    )
    live_calls_url_handler: Optional[Dict[str, Any]] = Field(
        None,
        description="Config for vendor live/active calls lookup API endpoint",
    )

    class CollectionName:
        VENDOR_CONFIG = "vendor_config"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)
