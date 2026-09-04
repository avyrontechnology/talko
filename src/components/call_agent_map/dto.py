from typing import List, Optional

from pydantic import BaseModel


class Contract:
    class AgentDidMappingCreate(BaseModel):
        agent_id: int
        partner_id: int

    class AgentDidMappingUpdate(BaseModel):
        did: Optional[str] = None
        is_active: Optional[bool] = None

    class AgentDidMappingResponse(BaseModel):
        id: str
        agent_id: int
        did: Optional[List[str]] = None
        partner_id: int
        is_active: bool
        created_at: Optional[int] = None
        updated_at: Optional[int] = None

    class AgentDidMappingCreationResponse(BaseModel):
        id: str
        message: str

    # request response schemas for agent service board mapping

    class AgentServiceBoardMappingCreate(BaseModel):
        partner_id: int
        service_board_id: int
        agent_id: int
        agent_number: Optional[str] = None
        is_active: Optional[bool] = True

    class AgentServiceBoardMappingUpdate(BaseModel):
        agent_number: Optional[str] = None
        is_active: Optional[bool] = None

    class AgentServiceBoardMappingResponse(BaseModel):
        id: str
        partner_id: int
        service_board_id: int
        agent_id: int
        agent_number: Optional[str] = None
        is_active: bool
        created_at: Optional[int] = None
        updated_at: Optional[int] = None

    class AgentServiceBoardMappingCreationResponse(BaseModel):
        id: str
        message: str    
