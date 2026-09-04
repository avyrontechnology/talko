from unittest.mock import AsyncMock, MagicMock, call

import pytest, copy
from bson import ObjectId

from src.components.call_agent_map.dto import Contract
from src.components.call_agent_map.services import AgentMappingService
from src.exceptions import BadRequestError, ResourceNotFound


@pytest.mark.asyncio
class TestAgentMappingService:
    def setup_method(self):
        self.mock_repository = AsyncMock()
        self.mock_logger = MagicMock()
        self.mock_datetime_util = MagicMock()
        self.mock_partner_config_repo = AsyncMock()
        self.validation = AsyncMock()

        self.service = AgentMappingService(
            repository=self.mock_repository,
            logger=self.mock_logger,
            datetime_util=self.mock_datetime_util,
            partner_config_repository=self.mock_partner_config_repo,
            validation=self.validation,
        )

    async def test_get_assigned_did_success(self):
        agent_id = 1
        partner_id = 101
        active_did_pool = ["1001", "1002"]
        self.mock_repository.get_agent_did_mapping.return_value = {"did": "1001"}

        result = await self.service.get_assigned_did(
            agent_id, partner_id, active_did_pool
        )

        assert result == "1001"
        self.mock_logger.debug.assert_called()

    async def test_get_assigned_did_not_found(self):
        agent_id = "agent2"
        partner_id = 101
        active_did_pool = ["1001", "1002"]
        self.mock_repository.get_agent_did_mapping.return_value = {"did": "9999"}

        with pytest.raises(ResourceNotFound):
            await self.service.get_assigned_did(agent_id, partner_id, active_did_pool)

    async def test_create_agent_did_mapping_success(self):
        agent_id = 123
        partner_id = 456
        did_list = ["2001", "2002"]

        self.mock_partner_config_repo.find_partner_config_by_partner_id.return_value = {
            "agent_mapping_dids": did_list
        }
        self.mock_repository.count_active_agent_mappings.return_value = 1
        self.mock_repository.get_unassigned_did.return_value = "2002"
        self.mock_datetime_util.get_current_time.return_value = 12345678
        self.mock_repository.insert_agent_did_mapping.return_value = ObjectId(
            "64d8f395e24f7c7b45c8eac9"
        )

        result = await self.service.create_agent_did_mapping(agent_id, partner_id)

        assert isinstance(result, Contract.AgentDidMappingCreationResponse)
        assert result.message == "Agent mapping creation done."

    async def test_create_agent_did_mapping_partner_not_found(self):
        self.mock_partner_config_repo.find_partner_config_by_partner_id.return_value = (
            None
        )

        with pytest.raises(ResourceNotFound):
            await self.service.create_agent_did_mapping(agent_id=1, partner_id=999)

    async def test_create_agent_did_mapping_no_dids(self):
        self.mock_partner_config_repo.find_partner_config_by_partner_id.return_value = {
            "agent_mapping_dids": []
        }

        with pytest.raises(
            BadRequestError, match="No DIDs available for agent mapping"
        ):
            await self.service.create_agent_did_mapping(agent_id=1, partner_id=999)

    async def test_create_agent_did_mapping_limit_reached(self):
        self.mock_partner_config_repo.find_partner_config_by_partner_id.return_value = {
            "agent_mapping_dids": ["1001"]
        }
        self.mock_repository.count_active_agent_mappings.return_value = 1

        with pytest.raises(BadRequestError, match="Maximum agent mapping limit"):
            await self.service.create_agent_did_mapping(agent_id=1, partner_id=999)

    async def test_get_all_agent_did_mapping_empty(self):
        # Arrange
        self.mock_repository.get_all_agent_mapping = AsyncMock(return_value=[])

        # Act & Assert
        with pytest.raises(ResourceNotFound, match="No agent mapping found."):
            await self.service.get_all_agent_did_mapping()

        self.mock_logger.debug.assert_any_call("No valid mapping for agent.")

    async def test_get_all_agent_did_mapping_exception(self):
        # Arrange
        self.mock_repository.get_all_agent_mapping = AsyncMock(
            side_effect=Exception("Database error")
        )

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            await self.service.get_all_agent_did_mapping()

        self.mock_logger.error.assert_called_once_with(
            "Failed to retrieve agent did mapping data: Database error"
        )

    async def test_get_all_agent_did_mapping_success(self):
        # Arrange
        mock_repository = MagicMock()
        mock_logger = MagicMock()

        # Sample data returned from the DB
        mapping_data = [
            {
                "_id": ObjectId(),
                "partner_id": 1,
                "agent_id": 101,
                "did": ["1234567890"],  # <- Make this a list
                "is_active": True,
            },
            {
                "_id": ObjectId(),
                "partner_id": 2,
                "agent_id": 102,
                "did": ["0987654321"],  # <- Make this a list
                "is_active": True,
            },
        ]
        # Expected response list
        expected_response = [
            Contract.AgentDidMappingResponse(
                id=str(mapping["_id"]),
                partner_id=mapping["partner_id"],
                agent_id=mapping["agent_id"],
                did=mapping["did"],  # Already a list
                is_active=mapping["is_active"],
            )
            for mapping in mapping_data
        ]

        # Mock behavior
        self.mock_repository.get_all_agent_mapping.return_value = mapping_data

        # Act
        response = await self.service.get_all_agent_did_mapping()

        # Assert
        assert response == expected_response

    async def test_create_agent_service_board_mapping_success(self):
        # Arrange
        partner_id = 4
        service_board_id = 21
        agent_id = 12
        agent_number = "9000000000"

        # Partner config exists
        self.mock_partner_config_repo.find_partner_config_by_partner_id.return_value = {
            "partner_id": partner_id
        }

        # Mock datetime
        self.mock_datetime_util.get_current_time.return_value = 1696584000

        # Mock insert returns an ID
        self.mock_repository.insert_agent_service_board_mapping.return_value = "12345"

        # Act
        result = await self.service.create_agent_service_board_mapping(
            partner_id=partner_id,
            service_board_id=service_board_id,
            agent_id=agent_id,
            agent_number=agent_number,
        )

        # Assert
        assert isinstance(result, Contract.AgentServiceBoardMappingCreationResponse)
        assert result.id == "12345"
        assert result.message == "Agent–Service Board mapping created successfully."
        self.mock_partner_config_repo.find_partner_config_by_partner_id.assert_awaited_once_with(partner_id)
        self.mock_repository.insert_agent_service_board_mapping.assert_awaited_once()
        self.mock_logger.info.assert_called_once()

    async def test_create_agent_service_board_mapping_partner_not_found(self):
        # Arrange
        self.mock_partner_config_repo.find_partner_config_by_partner_id.return_value = None

        # Act & Assert
        with pytest.raises(ResourceNotFound, match=f"Partner config not found for partner_id 4"):
            await self.service.create_agent_service_board_mapping(
                partner_id=4,
                service_board_id=21,
                agent_id=12,
                agent_number="9000000000",
            )
        assert self.mock_logger.error.call_count == 2  # logger called twice
        self.mock_logger.error.assert_has_calls([
            call("Partner config not found for partner_id 4"),
            call("Error creating Agent–Service Board mapping: Partner config not found for partner_id 4")
        ])

    async def test_create_agent_service_board_mapping_exception(self):
        # Arrange
        self.mock_partner_config_repo.find_partner_config_by_partner_id.return_value = {
            "partner_id": 4
        }
        self.mock_datetime_util.get_current_time.return_value = 1696584000
        self.mock_repository.insert_agent_service_board_mapping.side_effect = Exception("DB error")

        # Act & Assert
        with pytest.raises(Exception, match="DB error"):
            await self.service.create_agent_service_board_mapping(
                partner_id=4,
                service_board_id=21,
                agent_id=12,
                agent_number="9000000000",
            )
        self.mock_logger.error.assert_called_once()

    async def test_get_agents_success(self):
        service_board_id = 21
        partner_id = 4

        agent_data = [
            {"_id": ObjectId("64d8f395e24f7c7b45c8eac9"), "partner_id": partner_id, "service_board_id": 21, "agent_id": 12, "agent_number": "9000000000", "is_active": True},
            {"_id": ObjectId("64d8f395e24f7c7b45c8eaca"), "partner_id": partner_id, "service_board_id": 21, "agent_id": 13, "agent_number": "9000000001", "is_active": True},
        ]
        
        self.mock_repository.get_agents_by_service_board_id_and_partner_id.return_value = copy.deepcopy(agent_data)

        result = await self.service.get_agents_by_service_board(service_board_id, partner_id)

        expected_response = [
            Contract.AgentServiceBoardMappingResponse(
                id=str(agent["_id"]),
                partner_id=agent["partner_id"],
                service_board_id=agent["service_board_id"],
                agent_id=agent["agent_id"],
                agent_number=agent["agent_number"],
                is_active=agent["is_active"],
            )
            for agent in agent_data
        ]

        assert result == expected_response
        self.mock_logger.debug.assert_any_call(
            f"Retrieved agent–service board mapping from DB. data: {agent_data}"
        )
        self.mock_logger.info.assert_called_once_with(
            f"Retrieved all agents for service_board_id {service_board_id} successfully."
        )

    async def test_get_agents_no_agents(self):
        service_board_id = 21
        partner_id = 4

        self.mock_repository.get_agents_by_service_board_id_and_partner_id.return_value = []

        with pytest.raises(ResourceNotFound, match="No agents mapped to this service board."):
            await self.service.get_agents_by_service_board(service_board_id, partner_id)

        self.mock_logger.debug.assert_any_call(
            f"No agents found for service_board_id {service_board_id} and partner_id {partner_id}"
        )

    async def test_get_agents_exception(self):
        service_board_id = 21
        partner_id = 4
        
        self.mock_repository.get_agents_by_service_board_id_and_partner_id.side_effect = Exception("DB error")

        with pytest.raises(Exception, match="DB error"):
            await self.service.get_agents_by_service_board(service_board_id, partner_id)

        self.mock_logger.error.assert_called_once_with(
            f"Failed to retrieve agent–service board mapping data for service_board_id {service_board_id} and partner_id {partner_id}: DB error"
        )

    async def test_update_is_active_success(self):
        partner_id = 4
        service_board_id = 21
        is_active = True
        
        self.mock_repository.update_is_active_by_service_board_and_partner_id.return_value = 3

        result = await self.service.update_is_active_by_service_board_and_partner_id(
            partner_id, service_board_id, is_active
        )

        assert result == 3
        self.mock_logger.info.assert_called_once_with(
            f"Updating agent mapping status for service_board_id={service_board_id}and partner_id={partner_id}"
        )
        self.mock_logger.warning.assert_not_called()

    async def test_update_is_active_no_mappings(self):
        partner_id = 4
        service_board_id = 21
        is_active = True

        self.mock_repository.update_is_active_by_service_board_and_partner_id.return_value = 0

        with pytest.raises(ResourceNotFound, match=f"No mappings found for service_board_id={service_board_id} and partner_id={partner_id}"):
            await self.service.update_is_active_by_service_board_and_partner_id(
                partner_id, service_board_id, is_active
            )

        self.mock_logger.warning.assert_called_once_with(
            f"No mappings found for service_board_id={service_board_id} and partner_id={partner_id}"
        )

    async def test_update_is_active_exception(self):
        partner_id = 4
        service_board_id = 21
        is_active = True

        self.mock_repository.update_is_active_by_service_board_and_partner_id.side_effect = Exception("DB error")

        with pytest.raises(Exception, match="DB error"):
            await self.service.update_is_active_by_service_board_and_partner_id(
                partner_id, service_board_id, is_active
            )

        self.mock_logger.error.assert_called_once_with(
            "Failed to delete agent–service board mapping data: DB error"
        )
