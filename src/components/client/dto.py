from pydantic import BaseModel


class TalkoContract:
    class ClientCreate(BaseModel):
        partner_id: int
        name: str
        contact_name: str | None = None
        email: str | None = None
        phone: str | None = None
        external_ref: str | None = None
        notes: str | None = None
        tags: list[str] | None = None

    class ClientUpdate(BaseModel):
        name: str | None = None
        contact_name: str | None = None
        email: str | None = None
        phone: str | None = None
        external_ref: str | None = None
        notes: str | None = None
        tags: list[str] | None = None
        is_active: bool | None = None

    class ClientResponse(BaseModel):
        id: str
        partner_id: int
        name: str
        contact_name: str | None = None
        email: str | None = None
        phone: str | None = None
        external_ref: str | None = None
        notes: str | None = None
        tags: list[str] = []
        is_active: bool = True
        created_at: int | None = None
        updated_at: int | None = None

    class ClientCreateResponse(BaseModel):
        id: str
        message: str
