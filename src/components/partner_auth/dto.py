from typing import Optional

from pydantic import BaseModel


class TalkoContract:
    class ApiKeyCreate(BaseModel):
        partner_id: int
        label: Optional[str] = None

    class ApiKeyCreateResponse(BaseModel):
        id: str
        key: str  # raw key — shown exactly once, never retrievable again
        key_prefix: str
        partner_id: int
        label: Optional[str] = None
        created_at: int

    class ApiKeyListItem(BaseModel):
        id: str
        key_prefix: str
        partner_id: int
        label: Optional[str] = None
        is_active: bool
        created_at: int
        last_used_at: Optional[int] = None
        revoked_at: Optional[int] = None

    class ApiKeyRevokeResponse(BaseModel):
        id: str
        is_active: bool
        revoked_at: int
