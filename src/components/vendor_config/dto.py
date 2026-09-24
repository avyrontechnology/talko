from typing import Any, Optional

from pydantic import BaseModel


class TalkoContract:
    class ChannelPoolConfig(BaseModel):
        max_channels: int | None = None
        reserved_channels: int = 0

    class VendorConfigCreate(BaseModel):
        name: str | None = None
        vendor_id: str
        available_did: list[str]
        generic_url_handler: dict[str, Any]
        cdr_url_handler: dict[str, Any] | None = None
        dialer_url_handler: dict[str, Any] | None = None
        transfer_url_handler: dict[str, Any] | None = None
        channel_pool: Optional["TalkoContract.ChannelPoolConfig"] = None

    class GetAllVendorConfigData(BaseModel):
        id: str
        vendor_id: str | None = None
        name: str | None = None
        vendor_name: str
        generic_url_handler: dict[str, Any] | None = None
        available_did: list[str] | None = None

    class VendorConfigUpdate(BaseModel):
        generic_url_handler: dict[str, Any] | None = None
        available_did: list[str] | None = None
        cdr_url_handler: dict[str, Any] | None = None
        dialer_url_handler: dict[str, Any] | None = None
        transfer_url_handler: dict[str, Any] | None = None
        channel_pool: Optional["TalkoContract.ChannelPoolConfig"] = None

    class VendorConfigCreationUpdationResponse(BaseModel):
        id: str
        message: str

    class VendorConfigResponse(BaseModel):
        id: str
        vendor_id: str
        name: str
        vendor_name: str
        available_did: list[str]
        assigned_did: list[str]
        generic_url_handler: dict[str, Any]
        cdr_url_handler: dict[str, Any] | None = None
        dialer_url_handler: dict[str, Any] | None = None
        transfer_url_handler: dict[str, Any] | None = None
        channel_pool: Optional["TalkoContract.ChannelPoolConfig"] = None
        created_at: int | None
        updated_at: int | None

    class ChannelPoolUpdate(BaseModel):
        max_channels: int | None = None
        reserved_channels: int = 0

    class ChannelPoolStatus(BaseModel):
        vendor_config_id: str
        max_channels: int | None = None
        reserved_channels: int = 0
        in_use: int = 0
        available: int | None = None
