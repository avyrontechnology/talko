from typing import Any, Dict, List, Optional

from pymongo.results import InsertOneResult, UpdateResult

from src.components.call_agent_map.models import (
    TalkoAgentDidMappingModel,
    TalkoAgentServiceBoardMappingModel,
)
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.exceptions import TalkoBadRequestError
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoAgentMappingRepository:
    """
    Repository for managing call-related data operations in the database.
    """

    def __init__(
        self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger
    ) -> None:
        """
        Initialize the repository.

        Args:
            db_manager: MongoDB session manager.
            logger: Logger for capturing logs.
        """
        self.db_manager: TalkoDocDatabaseSessionManager = db_manager
        self.logger: TalkoServiceLogger = logger

    async def get_all_agent_mapping(self) -> Optional[Dict[str, Any]]:
        """
        Fetches the agent DID mapping.
        Returns:
            Optional[Dict[str, Any]]: Agent DID mapping or None if not found.
        """
        try:
            async with self.db_manager.collection(
                TalkoAgentDidMappingModel.CollectionName.AGENT_DID_MAPPING
            ) as collection:
                document: Optional[Dict[str, Any]] = await collection.find(
                    {"is_active": True}
                ).to_list(length=None)
                self.logger.debug("Fetched agent DID mapping {}".format(document))
                return document
        except Exception as e:
            self.logger.error("Error fetching agent DID mapping {}".format(str(e)))
            raise

    async def get_agent_did_mapping(
        self, agent_id: int, partner_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches the agent DID mapping for a given agent_id and partner_id.

        Args:
            agent_id (str): The agent's identifier.
            partner_id (int): The partner's identifier.

        Returns:
            Optional[Dict[str, Any]]: Agent DID mapping or None if not found.
        """
        try:
            query: Dict[str, Any] = {"is_active": True}
            if agent_id is not None:
                query["agent_id"] = agent_id
            if partner_id is not None:
                query["partner_id"] = partner_id

            self.logger.debug("Get agent did mapping final query: {}".format(query))
            async with self.db_manager.collection(
                TalkoAgentDidMappingModel.CollectionName.AGENT_DID_MAPPING
            ) as collection:
                document: Optional[Dict[str, Any]] = await collection.find_one(query)
                self.logger.debug(
                    "Fetched agent DID mapping for agent_id {} and partner_id {}: {}".format(
                        agent_id, partner_id, document
                    )
                )
                return document
        except Exception as e:
            self.logger.error(
                "Error fetching agent DID mapping for agent_id {} and partner_id {}: {}".format(
                    agent_id, partner_id, str(e)
                )
            )
            raise

    async def insert_agent_did_mapping(self, mapping_dict: Dict[str, Any]) -> str:
        """
        Inserts a new agent DID mapping into the database.

        Args:
            mapping_dict (Dict[str, Any]): The mapping data to insert.

        Returns:
            str: The ID of the inserted mapping.
        """
        try:
            self.logger.debug("Inserting agent did mapping data: ".format(mapping_dict))
            async with self.db_manager.collection(
                TalkoAgentDidMappingModel.CollectionName.AGENT_DID_MAPPING
            ) as collection:
                result: InsertOneResult = await collection.insert_one(mapping_dict)
                inserted_id: str = str(result.inserted_id)
                self.logger.debug(
                    "Inserted agent DID mapping with id: {}".format(inserted_id)
                )
                return inserted_id
        except Exception as e:
            self.logger.error(f"Error inserting agent DID mapping: {str(e)}")
            raise

    async def update_agent_did_mapping(
        self, agent_id: str, partner_id: int, updates: Dict[str, Any]
    ) -> bool:
        """
        Updates an existing agent DID mapping.

        Args:
            agent_id (str): The agent's identifier.
            partner_id (int): The partner's identifier.
            updates (Dict[str, Any]): The fields to update.

        Returns:
            bool: True if update was successful.
        """
        try:
            async with self.db_manager.collection(
                TalkoAgentDidMappingModel.CollectionName.AGENT_DID_MAPPING
            ) as collection:
                result: UpdateResult = await collection.update_one(
                    {"agent_id": agent_id, "partner_id": partner_id, "is_active": True},
                    {"$set": updates},
                )
                self.logger.debug(
                    "Updated agent DID mapping for agent_id {} and partner_id {}: {}".format(
                        agent_id, partner_id, result.modified_count
                    )
                )
                return result.modified_count > 0
        except Exception as e:
            self.logger.error(
                "Error updating agent DID mapping for agent_id {} and partner_id {}: {}".format(
                    agent_id, partner_id, str(e)
                )
            )
            raise

    async def bulk_insert_agent_did_mappings(
        self, mappings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Inserts multiple agent DID mappings into the database

        Args:
            mappings (List[Dict[str, Any]]): List of mapping dictionaries to insert.

        Returns:
            List[Dict[str, Any]]: List of results with IDs or error details.
        """
        try:
            results: List[Dict[str, Any]] = []
            async with self.db_manager.collection(
                TalkoAgentDidMappingModel.CollectionName.AGENT_DID_MAPPING
            ) as collection:
                for mapping in mappings:
                    try:
                        result: InsertOneResult = await collection.insert_one(mapping)
                        results.append(
                            {
                                "agent_id": mapping["agent_id"],
                                "id": str(result.inserted_id),
                                "status": "success",
                            }
                        )
                        self.logger.info(
                            "Inserted agent DID mapping for agent_id {} with id: {}".format(
                                mapping["agent_id"], str(result.inserted_id)
                            )
                        )
                    except Exception as e:
                        results.append(
                            {
                                "agent_id": mapping["agent_id"],
                                "status": "failed",
                                "error": str(e),
                            }
                        )
                        self.logger.error(
                            "Failed to insert agent DID mapping for agent_id {}: {}".format(
                                mapping["agent_id"], str(e)
                            )
                        )
            return results
        except Exception as e:
            self.logger.error(
                "Error in bulk insert of agent DID mappings: {}".format(str(e))
            )
            raise

    async def count_active_agent_mappings(self, partner_id: int) -> int:
        """
        Counts the number of active agent mappings for a given partner_id.

        Args:
            partner_id (int): The partner's identifier.

        Returns:
            int: The number of active mappings.
        """
        try:
            async with self.db_manager.collection(
                TalkoAgentDidMappingModel.CollectionName.AGENT_DID_MAPPING
            ) as collection:
                count: int = await collection.count_documents(
                    {"partner_id": partner_id, "is_active": True}
                )
                self.logger.debug(
                    "Counted {} active agent mappings for partner_id {}".format(
                        count, partner_id
                    )
                )
                return count
        except Exception as e:
            self.logger.error(
                "Error counting active agent mappings for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise

    async def get_unassigned_did(
        self, partner_id: int, agent_mapping_dids: List[str]
    ) -> str:
        """
        Retrieves an unassigned DID from the agent_mapping_dids pool for a given partner.

        Args:
            partner_id (int): The partner's identifier.
            agent_mapping_dids (List[str]): List of DIDs available for agent mapping.

        Returns:
            str: An unassigned DID.

        Raises:
            TalkoBadRequestError: If no unassigned DID is available.
        """
        try:
            async with self.db_manager.collection(
                TalkoAgentDidMappingModel.CollectionName.AGENT_DID_MAPPING
            ) as collection:
                # Get all currently assigned DIDs for this partner
                assigned_dids: List[str] = await collection.distinct(
                    "did", {"partner_id": partner_id, "is_active": True}
                )
                # Find an unassigned DID
                available_dids: List[str] = [
                    did for did in agent_mapping_dids if did not in assigned_dids
                ]
                if not available_dids:
                    raise TalkoBadRequestError("No available DIDs for agent mapping")
                return available_dids[
                    0
                ]  # Simple first-available; can be enhanced with round-robin
        except Exception as e:
            self.logger.error(
                "Error fetching unassigned DID for partner_id {}: {}".format(
                    partner_id, str(e)
                )
            )
            raise

    async def insert_agent_service_board_mapping(self, mapping_dict: Dict[str, Any]) -> str:
        """
        Inserts a new Agent–Service Board mapping into the database.

        Args:
            mapping_dict (Dict[str, Any]): The mapping data to insert.

        Returns:
            str: The ID of the inserted mapping.
        """
        try:
            self.logger.debug("Inserting mapping data: ".format(mapping_dict))
            async with self.db_manager.collection(
                TalkoAgentServiceBoardMappingModel.CollectionName.AGENT_SERVICE_BOARD_MAPPING
            ) as collection:
                result: InsertOneResult = await collection.insert_one(mapping_dict)
                inserted_id: str = str(result.inserted_id)
                self.logger.debug(
                    "Inserted Agent–Service Board mapping with id: {}".format(inserted_id)
                )
                return inserted_id
        except Exception as e:
            self.logger.error("Error inserting Agent–Service Board mapping: {}".format(str(e)))
            raise

    async def get_agents_by_service_board_id_and_partner_id(self, service_board_id: int, partner_id: int) -> List[Dict[str, Any]]:
        """
        Fetch all agents mapped to a given service board id and partner_id
        """
        try:
            async with self.db_manager.collection(
                TalkoAgentServiceBoardMappingModel.CollectionName.AGENT_SERVICE_BOARD_MAPPING
            ) as collection:
                agents: List[Dict[str, Any]] = await collection.find(
                    {"service_board_id": service_board_id, "partner_id":partner_id, "is_active": True}
                ).to_list(length=None)
                self.logger.debug(
                    "Fetched agents for service_board_id {} and partner_id {}: {}".format(service_board_id, partner_id, agents)
                )
                return agents
        except Exception as e:
            self.logger.error("Error fetching agents for service_board_id {} and partner_id {}: {}".format(service_board_id, partner_id, str(e)))
            raise

    async def update_is_active_by_service_board_and_partner_id(
        self, partner_id: int, service_board_id: int, is_active: bool
    ) -> int:
        """
        Update active/inactive status for all agent-service-board mappings for a given service_board_id and partner_id

        Returns:
            int: Number of updated records
        """
        try:
            async with self.db_manager.collection(
                TalkoAgentServiceBoardMappingModel.CollectionName.AGENT_SERVICE_BOARD_MAPPING
            ) as collection:
                result = await collection.update_many(
                    {"service_board_id": service_board_id, "partner_id": partner_id},
                    {"$set": {"is_active": is_active}},
                )
                self.logger.info(
                    "Updated 'is_active'={} for {} mappings (service_board_id={}, partner_id={})".format(
                        is_active, result.modified_count, service_board_id, partner_id
                    )
                )
                return result.modified_count
        except Exception as e:
            self.logger.error("Failed to update status of mappings for service_board_id={} and partner_id={}: {}".format(service_board_id, partner_id, str(e)))
            raise