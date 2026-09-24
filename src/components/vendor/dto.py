from pydantic import BaseModel

from src.utils.enums import TalkoVendorType


class TalkoContract:
    class VendorCreate(BaseModel):
        name: str
        vendor_type: TalkoVendorType

    class VendorResponse(BaseModel):
        id: str
        message: str

    class GetAllVendorData(BaseModel):
        id: str
        name: str
        slug: str | None = None
        is_active: bool = True
        # str (not enum) on purpose: legacy docs carry values outside
        # TalkoVendorType and a single bad doc must not 500 the whole list.
        vendor_type: str | None = None
        created_at: int | None = None
        updated_at: int | None = None

    class GetVendorDataOnTheBasisOfId(BaseModel):
        id: str
        name: str
        slug: str
        is_active: bool
        vendor_type: TalkoVendorType
        created_at: int | None = None
        updated_at: int | None = None
