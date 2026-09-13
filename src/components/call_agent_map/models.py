from typing import List, Optional

from bson import ObjectId
from pydantic import ConfigDict

from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoAgentDidMappingModel(TalkoTimestampedModel):
    partner_id: Optional[int] = None  # ID of the partner
    agent_id: Optional[int] = None  # ID of the agent
    did: Optional[List[str]] = None  # Direct Inward Dialing number from vendor
    is_active: bool  # Active status

    class CollectionName:
        AGENT_DID_MAPPING = "agent_did_mapping"  # Collection name

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)


class TalkoAgentWorkspaceMappingModel(TalkoTimestampedModel):
    partner_id: Optional[int] = None  # Partner identifier
    workspace_id: int  # Workspace identifier
    agent_id: int  # Agent identifier
    agent_number: Optional[str] = None  # Agent's phone number
    is_active: bool = True  # Active status of the mapping

    class CollectionName:
        AGENT_WORKSPACE_MAPPING = "agent_workspace_mapping"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)
