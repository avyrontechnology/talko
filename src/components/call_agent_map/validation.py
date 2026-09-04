from src.components.call_agent_map.dto import Contract
from src.components.call_agent_map.repository import AgentMappingRepository
from src.loggers.holler_service_logger import HollerServiceLogger


class AgentMapperValidator:
    """
    Validator class for checking agent mapping constraints,
    such as ensuring an agent is not already mapped to another partner.
    """

    def __init__(self, repository: AgentMappingRepository, logger: HollerServiceLogger):
        """
        Initialize the AgentMapperValidator.

        Args:
            repository (AgentMappingRepository): Repository for accessing agent mapping records.
            logger (HollerServiceLogger): Logger instance for logging validation activities.
        """
        self.repository = repository
        self.logger = logger

    async def validate_agent_not_already_mapped(self, agent_id: int):
        """
        Validates whether the agent is already mapped to another partner and is active.

        Args:
            agent (Contract.AgentDidMappingCreate): Agent mapping input data.

        Raises:
            ValueError: If the agent is already mapped to another partner.
        """
        existing_agent_mapping = await self.repository.get_agent_did_mapping(agent_id)
        if existing_agent_mapping:
            self.logger.error(
                "Agent ID {} is already mapped to another partner. Existing data: {}".format(
                    agent_id, existing_agent_mapping
                )
            )
            raise ValueError("Agent ID is already mapped to another partner.")
