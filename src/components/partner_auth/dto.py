from pydantic import BaseModel


class TalkoContract:
    class ApiKeyCreate(BaseModel):
        partner_id: int
        label: str | None = None

    class ApiKeyCreateResponse(BaseModel):
        id: str
        key: str  # raw key — shown exactly once, never retrievable again
        key_prefix: str
        partner_id: int
        label: str | None = None
        created_at: int

    class ApiKeyListItem(BaseModel):
        id: str
        key_prefix: str
        partner_id: int
        label: str | None = None
        is_active: bool
        created_at: int
        last_used_at: int | None = None
        revoked_at: int | None = None

    class ApiKeyRevokeResponse(BaseModel):
        id: str
        is_active: bool
        revoked_at: int
