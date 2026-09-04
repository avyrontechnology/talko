from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Contract:
    class VendorConfigCreate(BaseModel):
        name: Optional[str] = None
        vendor_id: str
        available_did: List[str]
        generic_url_handler: Dict[str, Any]
        cdr_url_handler: Optional[Dict[str, Any]] = None
        dialer_url_handler: Optional[Dict[str, Any]] = None
        transfer_url_handler: Optional[Dict[str, Any]] = None

    class GetAllVendorConfigData(BaseModel):
        id: str
        vendor_name: str

    class VendorConfigUpdate(BaseModel):
        generic_url_handler: Optional[Dict[str, Any]] = None
        available_did: Optional[List[str]] = None
        cdr_url_handler: Optional[Dict[str, Any]] = None
        dialer_url_handler: Optional[Dict[str, Any]] = None
        transfer_url_handler: Optional[Dict[str, Any]] = None

    class VendorConfigCreationUpdationResponse(BaseModel):
        id: str
        message: str

    class VendorConfigResponse(BaseModel):
        id: str
        vendor_id: str
        name: str
        vendor_name: str
        available_did: List[str]
        assigned_did: List[str]
        generic_url_handler: Dict[str, Any]
        cdr_url_handler: Optional[Dict[str, Any]] = None
        dialer_url_handler: Optional[Dict[str, Any]] = None
        transfer_url_handler: Optional[Dict[str, Any]] = None
        created_at: Optional[int]
        updated_at: Optional[int]
