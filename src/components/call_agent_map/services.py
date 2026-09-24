from typing import Any

from src.components.call_agent_map.dto import TalkoContract
from src.components.call_agent_map.messages import (
    AGENT_NOT_MAPPED_TO_WORKSPACE,
    AGENT_WORKSPACE_MAPPING_CREATED_SUCCESS,
    MAPPING_CREATE_SUCCESS,
    MAX_AGENT_MAPPING_LIMIT,
    NO_AGENT_MAPPING_FOUND,
    NO_MAPPING_FOR_SB_AND_PARTNER,
    NO_DIDs_TO_MAP,
)
from src.components.call_agent_map.models import (
    TalkoAgentDidMappingModel,
    TalkoAgentWorkspaceMappingModel,
)
from src.components.call_agent_map.repository import TalkoAgentMappingRepository
from src.components.call_agent_map.validation import TalkoAgentMapperValidator
from src.components.partner_config.message import PARTNER_CONFIG_MISSING
from src.components.partner_config.repository import TalkoPartnerConfigRepository
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil


class TalkoAgentMappingService:
    def __init__(
        self,
        repository: TalkoAgentMappingRepository,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
        partner_config_repository: TalkoPartnerConfigRepository,
        validation: TalkoAgentMapperValidator,
    ):
        self.repository = repository
        self.logger = logger
        self.datetime_util = datetime_util
        self.partner_config_repository = partner_config_repository
        self.validation = validation

    async def get_assigned_did(self, agent_id: int, partner_id: int, active_did_pool: list) -> str:
        """
        Retrieves the assigned DID for an agent, either from mapping or key-based round-robin.

        Args:
            agent_id (str): The agent's identifier (agent_number or user_id).
            active_did_pool (list): List of available DIDs for the partner.

        Returns:
            str: The assigned DID.

        Raises:
            TalkoResourceNotFound: If no valid DID is available.
        """
        # Check agent mapping
        mapping: dict[str, Any] | None = await self.repository.get_agent_did_mapping(agent_id, partner_id)
        if mapping and mapping.get("did") in active_did_pool:
            self.logger.debug("Assigned DID from mapping for agent {}: {}".format(agent_id, mapping.get("did")))
            return mapping.get("did")

        self.logger.debug(f"No valid mapping for agent {agent_id}, falling back to key-based round-robin")
        raise TalkoResourceNotFound("No valid DID found for agent")

    async def create_agent_did_mapping(
        self, agent_id: int, partner_id: int
    ) -> TalkoContract.AgentDidMappingCreationResponse:
        """
        Creates a new agent DID mapping.

        Args:
            agent_id (str): The agent's identifier.
            partner_id (int): The partner's identifier.
            did (str): The DID to assign.

        Returns:
            str: The ID of the created mapping.

        Raises:
            HTTPException: If the partner or DID is invalid, or the agent mapping limit is reached.
        """
        try:
            partner_config: (
                dict[str, Any] | None
            ) = await self.partner_config_repository.find_partner_config_by_partner_id(partner_id)
            if not partner_config:
                self.logger.error(f"Partner config for partner_id {partner_id} not found")
                raise TalkoResourceNotFound(f"{PARTNER_CONFIG_MISSING} for partner_id {partner_id}")

            # Get available DIDs from agent_mapping_dids
            agent_mapping_dids: list[str] = partner_config.get("agent_mapping_dids", [])
            if not agent_mapping_dids:
                self.logger.error(f"No agent_mapping_dids available for partner {partner_id}")
                raise TalkoBadRequestError(NO_DIDs_TO_MAP)

            # Check the number of existing active agent mappings
            await self.validation.validate_agent_not_already_mapped(agent_id)
            existing_mappings_count: int = await self.repository.count_active_agent_mappings(partner_id)
            if existing_mappings_count >= len(agent_mapping_dids):
                self.logger.error(
                    f"Agent mapping limit reached for partner {partner_id}. Maximum {len(agent_mapping_dids)} mappings allowed."
                )
                raise TalkoBadRequestError(MAX_AGENT_MAPPING_LIMIT.format(len(agent_mapping_dids), partner_id))

            assigned_did: str = await self.repository.get_unassigned_did(partner_id, agent_mapping_dids)

            mapping_dict: dict[str, Any] = {
                "agent_id": agent_id,
                "did": [assigned_did],
                "partner_id": partner_id,
                "is_active": True,
                "created_at": self.datetime_util.get_current_time(),
                "updated_at": self.datetime_util.get_current_time(),
            }
            agent_mapping_dict: dict | None = TalkoAgentDidMappingModel(**mapping_dict).model_dump()
            mapping_id: int = await self.repository.insert_agent_did_mapping(agent_mapping_dict)
            self.logger.info(f"Created agent DID mapping for agent {agent_id}: {mapping_id}")
            return TalkoContract.AgentDidMappingCreationResponse(id=str(mapping_id), message=MAPPING_CREATE_SUCCESS)
        except Exception as e:
            self.logger.error(f"Error creating partner config: {str(e)}")
            raise

    async def get_all_agent_did_mapping(self) -> TalkoContract.AgentDidMappingResponse:
        try:
            # Check agent mapping
            mappings: list[dict[str, Any]] = await self.repository.get_all_agent_mapping()
            if not mappings:
                self.logger.debug("No valid mapping for agent.")
                raise TalkoResourceNotFound(NO_AGENT_MAPPING_FOUND)

            self.logger.debug(f"Retrieved agent did mapping from the database. data: {mappings}")

            mapping_responses: list[TalkoContract.AgentDidMappingResponse] = []
            for item in mappings:
                item["id"] = str(item["_id"])
                del item["_id"]
                mapping_responses.append(TalkoContract.AgentDidMappingResponse(**item))

            self.logger.debug(f"Converted agent did mapping to response format. data: {mapping_responses}")
            self.logger.info("Retrieved all agent did mapping data successfully.")
            return mapping_responses

        except Exception as e:
            self.logger.error(f"Failed to retrieve agent did mapping data: {str(e)}")
            raise

    async def create_agent_workspace_mapping(
        self,
        partner_id: int,
        workspace_id: int,
        agent_id: int,
        agent_number: str | None = None,
    ) -> TalkoContract.AgentWorkspaceMappingCreationResponse:
        """
        Creates a new Agent–Workspace mapping.

        Args:
            partner_id (int): The partner's identifier.
            workspace_id (int): The workspace's identifier.
            agent_id (int): The agent's identifier.
            agent_number (Optional[str]): The agent's phone number.

        Returns:
            AgentWorkspaceMappingCreationResponse: The ID and message of the created mapping.

        Raises:
            HTTPException: If partner config not found or agent already mapped to same workspace.
        """
        try:
            self.logger.info(
                f"Starting creation of agent workspace mapping for partner_id {partner_id}, workspace_id {workspace_id}, agent_id {agent_id} and agent_number {agent_number}"
            )
            partner_config: (
                dict[str, Any] | None
            ) = await self.partner_config_repository.find_partner_config_by_partner_id(partner_id)
            if not partner_config:
                self.logger.error(f"Partner config not found for partner_id {partner_id}")
                raise TalkoResourceNotFound(f"{PARTNER_CONFIG_MISSING} for partner_id {partner_id}")

            mapping_dict: dict[str, Any] = {
                "partner_id": partner_id,
                "workspace_id": workspace_id,
                "agent_id": agent_id,
                "agent_number": agent_number,
                "is_active": True,
                "created_at": self.datetime_util.get_current_time(),
                "updated_at": self.datetime_util.get_current_time(),
            }

            mapping_data: dict = TalkoAgentWorkspaceMappingModel(**mapping_dict).model_dump()
            self.logger.info(f"Mapping data for Insertion: {mapping_data}")
            mapping_id: str = await self.repository.insert_agent_workspace_mapping(mapping_data)

            self.logger.info(
                f"Created Agent–Workspace mapping | Workspace: {workspace_id}, Agent: {agent_id}, Mapping ID: {mapping_id}"
            )

            return TalkoContract.AgentWorkspaceMappingCreationResponse(
                id=str(mapping_id),
                message=AGENT_WORKSPACE_MAPPING_CREATED_SUCCESS,
            )

        except Exception as e:
            self.logger.error(f"Error creating Agent–Workspace mapping: {str(e)}")
            raise

    async def get_agents_by_workspace(
        self, workspace_id: int, partner_id: int
    ) -> list[TalkoContract.AgentWorkspaceMappingResponse]:
        """
        Fetch all agents mapped to a given workspace and partner.
        """
        try:
            agents: list[dict[str, Any]] = await self.repository.get_agents_by_workspace_id_and_partner_id(
                workspace_id, partner_id
            )

            if not agents:
                self.logger.debug(f"No agents found for workspace_id {workspace_id} and partner_id {partner_id}")
                raise TalkoResourceNotFound(AGENT_NOT_MAPPED_TO_WORKSPACE)

            self.logger.debug(f"Retrieved agent–workspace mapping from DB. data: {agents}")

            response_list: list[TalkoContract.AgentWorkspaceMappingResponse] = []
            for item in agents:
                item["id"] = str(item["_id"])
                del item["_id"]
                response_list.append(TalkoContract.AgentWorkspaceMappingResponse(**item))

            self.logger.debug(f"Converted agent–workspace mapping to response format. data: {response_list}")
            self.logger.info(f"Retrieved all agents for workspace_id {workspace_id} successfully.")

            return response_list

        except Exception as e:
            self.logger.error(
                f"Failed to retrieve agent–workspace mapping data for workspace_id {workspace_id} and partner_id {partner_id}: {str(e)}"
            )
            raise

    async def update_is_active_by_workspace_and_partner_id(
        self, partner_id: int, workspace_id: int, is_active: bool
    ) -> int:
        """
        Update active/inactive for a given workspace and partner.
        Raises TalkoResourceNotFound if no mappings exist.
        """
        try:
            self.logger.info(
                f"Updating agent mapping status for workspace_id={workspace_id}and partner_id={partner_id}"
            )
            updated_count = await self.repository.update_is_active_by_workspace_and_partner_id(
                partner_id, workspace_id, is_active
            )
            if updated_count == 0:
                self.logger.warning(f"No mappings found for workspace_id={workspace_id} and partner_id={partner_id}")
                raise TalkoResourceNotFound(NO_MAPPING_FOR_SB_AND_PARTNER.format(workspace_id, partner_id))
            return updated_count
        except Exception as e:
            self.logger.error(f"Failed to delete agent–workspace mapping data: {str(e)}")
            raise
