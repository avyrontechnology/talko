from pydantic import BaseModel


class TalkoContract:
    class ClientCreate(BaseModel):
        partner_id: int
        name: str
        workspace_ids: list[int] | None = None

    class ClientUpdate(BaseModel):
        name: str | None = None
        workspace_ids: list[int] | None = None
        is_active: bool | None = None

    class ClientResponse(BaseModel):
        id: str
        partner_id: int
        name: str
        workspace_ids: list[int] = []
        is_active: bool = True
        created_at: int | None = None
        updated_at: int | None = None

    class ClientCreateResponse(BaseModel):
        id: str
        message: str
