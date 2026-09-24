from pydantic import BaseModel


class TalkoContract:
    class AgentDidMappingCreate(BaseModel):
        agent_id: int
        partner_id: int

    class AgentDidMappingUpdate(BaseModel):
        did: str | None = None
        is_active: bool | None = None

    class AgentDidMappingResponse(BaseModel):
        id: str
        agent_id: int
        did: list[str] | None = None
        partner_id: int
        is_active: bool
        created_at: int | None = None
        updated_at: int | None = None

    class AgentDidMappingCreationResponse(BaseModel):
        id: str
        message: str

    # request response schemas for agent workspace mapping

    class AgentWorkspaceMappingCreate(BaseModel):
        partner_id: int
        workspace_id: int
        agent_id: int
        agent_number: str | None = None
        is_active: bool | None = True

    class AgentWorkspaceMappingUpdate(BaseModel):
        agent_number: str | None = None
        is_active: bool | None = None

    class AgentWorkspaceMappingResponse(BaseModel):
        id: str
        partner_id: int
        workspace_id: int
        agent_id: int
        agent_number: str | None = None
        is_active: bool
        created_at: int | None = None
        updated_at: int | None = None

    class AgentWorkspaceMappingCreationResponse(BaseModel):
        id: str
        message: str
