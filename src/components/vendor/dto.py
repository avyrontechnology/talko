from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from src.utils.enums import VendorType


class Contract:
    class VendorCreate(BaseModel):
        name: str
        vendor_type: VendorType

    class VendorResponse(BaseModel):
        id: str
        message: str

    class GetAllVendorData(BaseModel):
        id: str
        name: str

    class GetVendorDataOnTheBasisOfId(BaseModel):
        id: str
        name: str
        slug: str
        is_active: bool
        vendor_type: VendorType
        created_at: Optional[int] = None
        updated_at: Optional[int] = None
