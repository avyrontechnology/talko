from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoChannelPoolConfig(BaseModel):
    """Channel pooling limits for a vendor config.

    None / absent = unlimited (backward compat for existing configs).
    """

    max_channels: int | None = Field(default=None, ge=1, description="Max concurrent calls; None = unlimited")
    reserved_channels: int = Field(default=0, ge=0, description="Channels held back from general pool")


class TalkoVendorConfigModel(TalkoTimestampedModel):
    name: str  # Name of the vendor configuration
    vendor_id: ObjectId  # Vendor identifier
    generic_url_handler: dict[str, Any]  # Config for generic URL handling
    cdr_url_handler: dict[str, Any] | None = Field(
        None, description="Config for TalkoCDR API endpoint"
    )  # TalkoCDR URL handler config
    dialer_url_handler: dict[str, Any] | None = Field(None, description="Config for dialer APIs")
    c2c_support_url_handler: dict[str, Any] | None = Field(
        None,
        description="Tata Tele Click-to-Call Support API config (endpoint, api_key, payload)",
    )
    hangup_url_handler: dict[str, Any] | None = Field(
        None,
        description="Config for vendor call hangup API endpoint (endpoint, auth_type, auth_credentials, headers)",
    )
    transfer_url_handler: dict[str, Any] | None = Field(
        None,
        description="Config for call transfer API endpoint",
    )
    live_calls_url_handler: dict[str, Any] | None = Field(
        None,
        description="Config for vendor live/active calls lookup API endpoint",
    )
    channel_pool: TalkoChannelPoolConfig | None = Field(
        default=None,
        description="Channel pooling limits; None = unlimited (legacy behavior)",
    )

    class CollectionName:
        VENDOR_CONFIG = "vendor_config"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)
