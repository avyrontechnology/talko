from typing import Any, Dict, List, Optional

from src.components.call_agent_map.dto import TalkoContract
from src.components.call_agent_map.messages import (
    AGENT_NOT_MAPPED_TO_SERVICE_BOARD,
    AGENT_SERVICE_BOARD_MAPPING_CREATED_SUCCESS,
    MAX_AGENT_MAPPING_LIMIT,
    MAPPING_CREATE_SUCCESS,
    NO_AGENT_MAPPING_FOUND,
    NO_DIDs_TO_MAP,
    NO_MAPPING_FOR_SB_AND_PARTNER,
)
from src.components.call_agent_map.models import (
    TalkoAgentDidMappingModel,
    TalkoAgentServiceBoardMappingModel,
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

    async def get_assigned_did(
        self, agent_id: int, partner_id: int, active_did_pool: list
    ) -> str:
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
        mapping: Optional[Dict[str, Any]] = await self.repository.get_agent_did_mapping(
            agent_id, partner_id
        )
        if mapping and mapping.get("did") in active_did_pool:
            self.logger.debug(
                "Assigned DID from mapping for agent {}: {}".format(
                    agent_id, mapping.get("did")
                )
            )
            return mapping.get("did")

        self.logger.debug(
            "No valid mapping for agent {}, falling back to key-based round-robin".format(
                agent_id
            )
        )
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
            partner_config: Optional[Dict[str, Any]] = (
                await self.partner_config_repository.find_partner_config_by_partner_id(
                    partner_id
                )
            )
            if not partner_config:
                self.logger.error(
                    "Partner config for partner_id {} not found".format(partner_id)
                )
                raise TalkoResourceNotFound(PARTNER_CONFIG_MISSING)

            # Get available DIDs from agent_mapping_dids
            agent_mapping_dids: List[str] = partner_config.get("agent_mapping_dids", [])
            if not agent_mapping_dids:
                self.logger.error(
                    "No agent_mapping_dids available for partner {}".format(partner_id)
                )
                raise TalkoBadRequestError(NO_DIDs_TO_MAP)

            # Check the number of existing active agent mappings
            await self.validation.validate_agent_not_already_mapped(agent_id)
            existing_mappings_count: int = (
                await self.repository.count_active_agent_mappings(partner_id)
            )
            if existing_mappings_count >= len(agent_mapping_dids):
                self.logger.error(
                    "Agent mapping limit reached for partner {}. Maximum {} mappings allowed.".format(
                        partner_id, len(agent_mapping_dids)
                    )
                )
                raise TalkoBadRequestError(
                    MAX_AGENT_MAPPING_LIMIT.format(
                        len(agent_mapping_dids), partner_id
                    )
                )

            assigned_did: str = await self.repository.get_unassigned_did(
                partner_id, agent_mapping_dids
            )

            mapping_dict: Dict[str, Any] = {
                "agent_id": agent_id,
                "did": [assigned_did],
                "partner_id": partner_id,
                "is_active": True,
                "created_at": self.datetime_util.get_current_time(),
                "updated_at": self.datetime_util.get_current_time(),
            }
            agent_mapping_dict: Optional[dict] = TalkoAgentDidMappingModel(
                **mapping_dict
            ).model_dump()
            mapping_id: int = await self.repository.insert_agent_did_mapping(
                agent_mapping_dict
            )
            self.logger.info(
                "Created agent DID mapping for agent {}: {}".format(
                    agent_id, mapping_id
                )
            )
            return TalkoContract.AgentDidMappingCreationResponse(
                id=str(mapping_id), message=MAPPING_CREATE_SUCCESS
            )
        except Exception as e:
            self.logger.error("Error creating partner config: {}".format(str(e)))
            raise

    async def get_all_agent_did_mapping(self) -> TalkoContract.AgentDidMappingResponse:
        try:
            # Check agent mapping
            mappings: List[Dict[str, Any]] = (
                await self.repository.get_all_agent_mapping()
            )
            if not mappings:
                self.logger.debug("No valid mapping for agent.")
                raise TalkoResourceNotFound(NO_AGENT_MAPPING_FOUND)

            self.logger.debug(
                "Retrieved agent did mapping from the database. data: {}".format(
                    mappings
                )
            )

            mapping_responses: List[TalkoContract.AgentDidMappingResponse] = []
            for item in mappings:
                item["id"] = str(item["_id"])
                del item["_id"]
                mapping_responses.append(TalkoContract.AgentDidMappingResponse(**item))

            self.logger.debug(
                "Converted agent did mapping to response format. data: {}".format(
                    mapping_responses
                )
            )
            self.logger.info("Retrieved all agent did mapping data successfully.")
            return mapping_responses

        except Exception as e:
            self.logger.error(
                "Failed to retrieve agent did mapping data: {}".format(str(e))
            )
            raise
    
    async def create_agent_service_board_mapping(
        self,
        partner_id: int,
        service_board_id: int,
        agent_id: int,
        agent_number: Optional[str] = None,
    ) -> TalkoContract.AgentServiceBoardMappingCreationResponse:
        """
        Creates a new Agent–Service Board mapping.

        Args:
            partner_id (int): The partner's identifier.
            service_board_id (int): The service board's identifier.
            agent_id (int): The agent's identifier.
            agent_number (Optional[str]): The agent's phone number.

        Returns:
            AgentServiceBoardMappingCreationResponse: The ID and message of the created mapping.

        Raises:
            HTTPException: If partner config not found or agent already mapped to same service board.
        """
        try:
            self.logger.info("Starting creation of agent service board mapping for partner_id {}, service_board_id {}, agent_id {} and agent_number {}".format(partner_id, service_board_id, agent_id, agent_number))
            partner_config: Optional[Dict[str, Any]] = (
                await self.partner_config_repository.find_partner_config_by_partner_id(partner_id)
            )
            if not partner_config:
                self.logger.error("Partner config not found for partner_id {}".format(partner_id))
                raise TalkoResourceNotFound(PARTNER_CONFIG_MISSING)

            mapping_dict: Dict[str, Any] = {
                "partner_id": partner_id,
                "service_board_id": service_board_id,
                "agent_id": agent_id,
                "agent_number": agent_number,
                "is_active": True,
                "created_at": self.datetime_util.get_current_time(),
                "updated_at": self.datetime_util.get_current_time(),
            }

            mapping_data: dict = TalkoAgentServiceBoardMappingModel(**mapping_dict).model_dump()
            self.logger.info("Mapping data for Insertion: {}".format(mapping_data))
            mapping_id: str = await self.repository.insert_agent_service_board_mapping(mapping_data)

            self.logger.info(
                "Created Agent–Service Board mapping | Service Board: {}, Agent: {}, Mapping ID: {}".format(
                    service_board_id, agent_id, mapping_id
                )
            )

            return TalkoContract.AgentServiceBoardMappingCreationResponse(
                id=str(mapping_id),
                message=AGENT_SERVICE_BOARD_MAPPING_CREATED_SUCCESS,
            )

        except Exception as e:
            self.logger.error("Error creating Agent–Service Board mapping: {}".format(str(e)))
            raise
        
    async def get_agents_by_service_board(self, service_board_id: int, partner_id: int) -> List[TalkoContract.AgentServiceBoardMappingResponse]:
        """
        Fetch all agents mapped to a given service board and partner.
        """
        try:
            agents: List[Dict[str, Any]] = await self.repository.get_agents_by_service_board_id_and_partner_id(
                service_board_id, partner_id
            )

            if not agents:
                self.logger.debug(
                    "No agents found for service_board_id {} and partner_id {}".format(service_board_id, partner_id)
                )
                raise TalkoResourceNotFound(AGENT_NOT_MAPPED_TO_SERVICE_BOARD)

            self.logger.debug(
                "Retrieved agent–service board mapping from DB. data: {}".format(agents)
            )

            response_list: List[TalkoContract.AgentServiceBoardMappingResponse] = []
            for item in agents:
                item["id"] = str(item["_id"])
                del item["_id"]
                response_list.append(TalkoContract.AgentServiceBoardMappingResponse(**item))

            self.logger.debug(
                "Converted agent–service board mapping to response format. data: {}".format(response_list)
            )
            self.logger.info(
                "Retrieved all agents for service_board_id {} successfully.".format(service_board_id)
            )

            return response_list

        except Exception as e:
            self.logger.error(
                "Failed to retrieve agent–service board mapping data for service_board_id {} and partner_id {}: {}".format(service_board_id, partner_id, str(e))
            )
            raise

    async def update_is_active_by_service_board_and_partner_id(self, partner_id: int, service_board_id: int, is_active: bool) -> int:
        """
        Update active/inactive for a given service board and partner.
        Raises TalkoResourceNotFound if no mappings exist.
        """
        try:
            self.logger.info("Updating agent mapping status for service_board_id={}and partner_id={}".format(service_board_id, partner_id))
            updated_count = await self.repository.update_is_active_by_service_board_and_partner_id(partner_id, service_board_id, is_active)
            if updated_count == 0:
                self.logger.warning("No mappings found for service_board_id={} and partner_id={}".format(service_board_id, partner_id))
                raise TalkoResourceNotFound(NO_MAPPING_FOR_SB_AND_PARTNER.format(service_board_id, partner_id))
            return updated_count
        except Exception as e:
            self.logger.error(
                "Failed to delete agent–service board mapping data: {}".format(str(e))
            )
            raise
