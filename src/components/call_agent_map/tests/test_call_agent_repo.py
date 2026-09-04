from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.components.call_agent_map.repository import TalkoAgentMappingRepository
from src.components.call_agent_map.services import TalkoAgentMappingService
from src.exceptions import TalkoBadRequestError
from src.loggers.talko_service_logger import TalkoServiceLogger


@pytest.mark.asyncio
class TestAgentMappingRepository:

    @pytest.fixture
    def setup(self):
        mock_db_manager = MagicMock()
        mock_logger = MagicMock(spec=TalkoServiceLogger)
        repo = TalkoAgentMappingRepository(mock_db_manager, mock_logger)
        return repo, mock_db_manager, mock_logger

    async def test_get_agent_did_mapping_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {
            "agent_id": 1,
            "partner_id": 123,
        }
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        result = await repo.get_agent_did_mapping(1, 123)
        assert result == {"agent_id": 1, "partner_id": 123}
        expected_calls = [
            call(
                "Get agent did mapping final query: {'is_active': True, 'agent_id': 1, 'partner_id': 123}"
            ),
            call(
                "Fetched agent DID mapping for agent_id 1 and partner_id 123: {'agent_id': 1, 'partner_id': 123}"
            ),
        ]
        mock_logger.debug.assert_has_calls(expected_calls)

    async def test_get_agent_did_mapping_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.find_one.side_effect = Exception("Find error")
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(Exception, match="Find error"):
            await repo.get_agent_did_mapping("agent1", 123)
        mock_logger.error.assert_called_once()

    async def test_insert_agent_did_mapping_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.insert_one.return_value.inserted_id = "12345"
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        result = await repo.insert_agent_did_mapping({"agent_id": "agent1"})
        assert result == "12345"
        mock_logger.debug.assert_called_once()

    async def test_insert_agent_did_mapping_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.insert_one.side_effect = Exception("Insert error")
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(Exception, match="Insert error"):
            await repo.insert_agent_did_mapping({"agent_id": "agent1"})
        mock_logger.error.assert_called_once()

    async def test_update_agent_did_mapping_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.update_one.return_value.modified_count = 1
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        result = await repo.update_agent_did_mapping("agent1", 123, {"did": "9999"})
        assert result is True
        mock_logger.debug.assert_called_once()

    async def test_update_agent_did_mapping_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.update_one.side_effect = Exception("Update error")
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(Exception, match="Update error"):
            await repo.update_agent_did_mapping("agent1", 123, {"did": "9999"})
        mock_logger.error.assert_called_once()

    async def test_bulk_insert_agent_did_mappings_success_and_failure(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.insert_one.side_effect = [
            MagicMock(inserted_id="id1"),
            Exception("Insert fail"),
        ]
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        mappings = [{"agent_id": "agent1"}, {"agent_id": "agent2"}]
        result = await repo.bulk_insert_agent_did_mappings(mappings)
        assert result == [
            {"agent_id": "agent1", "id": "id1", "status": "success"},
            {"agent_id": "agent2", "status": "failed", "error": "Insert fail"},
        ]
        assert mock_logger.info.called
        assert mock_logger.error.called

    async def test_count_active_agent_mappings_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.count_documents.return_value = 5
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        result = await repo.count_active_agent_mappings(123)
        assert result == 5
        mock_logger.debug.assert_called_once()

    async def test_count_active_agent_mappings_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.count_documents.side_effect = Exception("Count error")
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(Exception, match="Count error"):
            await repo.count_active_agent_mappings(123)
        mock_logger.error.assert_called_once()

    async def test_get_unassigned_did_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.distinct.return_value = ["1001", "1002"]
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        result = await repo.get_unassigned_did(123, ["1001", "1003"])
        assert result == "1003"

    async def test_get_unassigned_did_no_available(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.distinct.return_value = ["1001", "1002"]
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(
            TalkoBadRequestError, match="No available DIDs for agent mapping"
        ):
            await repo.get_unassigned_did(123, ["1001", "1002"])

    async def test_bulk_insert_agent_did_mappings_exception_before_loop(self, setup):
        repo, mock_db_manager, mock_logger = setup

        # Raise exception when trying to enter `async with` block
        mock_cm = AsyncMock()
        mock_cm.__aenter__.side_effect = Exception("DB connection failed")
        mock_db_manager.collection.return_value = mock_cm

        mappings = [{"agent_id": "a1"}, {"agent_id": "a2"}]

        with pytest.raises(Exception, match="DB connection failed"):
            await repo.bulk_insert_agent_did_mappings(mappings)

        mock_logger.error.assert_called_once()
        assert "bulk insert of agent DID mappings" in mock_logger.error.call_args[0][0]

    async def test_insert_agent_service_board_mapping_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.insert_one.return_value.inserted_id = "12345"
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm
        
        mapping_data = {
            "partner_id": 4,
            "service_board_id": 21,
            "agent_id": 12,
            "agent_number": 9000000000,
            "is_active": True
        }

        result = await repo.insert_agent_service_board_mapping(mapping_data)
        assert result == "12345"
        mock_logger.debug.assert_called_once()

    async def test_insert_agent_service_board_mapping_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = AsyncMock()
        mock_collection.insert_one.side_effect = Exception("Insert error")
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        mapping_data = {
            "partner_id": 4,
            "service_board_id": 21,
            "agent_id": 12,
            "agent_number": 9000000000,
            "is_active": True
        }

        with pytest.raises(Exception, match="Insert error"):
            await repo.insert_agent_service_board_mapping(mapping_data)
        mock_logger.error.assert_called_once()

    async def test_get_agents_by_service_board_id_and_partner_id_success(self, setup):
        repo, mock_db_manager, mock_logger = setup

        # Cursor mock
        mock_cursor = MagicMock()
        mock_agents = [
            {"agent_id": 1, "agent_number": 9000000000},
            {"agent_id": 2, "agent_number": 9000000001},
        ]
        mock_cursor.to_list = AsyncMock(return_value=mock_agents)

        # Collection mock returns cursor
        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor

        # Async context manager
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        # Call the repo method
        result = await repo.get_agents_by_service_board_id_and_partner_id(21, 4)

        assert result == mock_agents
        mock_collection.find.assert_called_once_with(
            {"service_board_id": 21, "partner_id": 4, "is_active": True}
        )
        mock_logger.debug.assert_called_once()



    async def test_get_agents_by_service_board_id_and_partner_id_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup

        # Cursor mock with exception on to_list
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(side_effect=Exception("Find error"))

        # Collection mock returns cursor
        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor

        # Async context manager
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        # Exception check
        with pytest.raises(Exception, match="Find error"):
            await repo.get_agents_by_service_board_id_and_partner_id(21, 4)

        mock_logger.error.assert_called_once()



    async def test_update_is_active_by_service_board_and_partner_id_success(self, setup):
        repo, mock_db_manager, mock_logger = setup

        mock_collection = AsyncMock()
        mock_update_result = AsyncMock()
        mock_update_result.modified_count = 3
        mock_collection.update_many.return_value = mock_update_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        result = await repo.update_is_active_by_service_board_and_partner_id(
            partner_id=4, service_board_id=21, is_active=False
        )

        assert result == 3
        mock_collection.update_many.assert_called_once_with(
            {"service_board_id": 21, "partner_id": 4},
            {"$set": {"is_active": False}},
        )
        mock_logger.info.assert_called_once()

    async def test_update_is_active_by_service_board_and_partner_id_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup
        
        mock_collection = AsyncMock()
        mock_collection.update_many.side_effect = Exception("Update error")

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(Exception, match="Update error"):
            await repo.update_is_active_by_service_board_and_partner_id(
                partner_id=4, service_board_id=21, is_active=True
            )

        mock_logger.error.assert_called_once()

@pytest.mark.asyncio
class TestAgentMappingCheckRepository:
    def setup_method(self):
        self.db_manager = MagicMock()
        self.logger = MagicMock()
        self.repository = TalkoAgentMappingRepository(self.db_manager, self.logger)

        self.collection_mock = MagicMock()
        self.db_manager.collection.return_value.__aenter__ = AsyncMock(
            return_value=self.collection_mock
        )
        self.db_manager.collection.return_value.__aexit__ = AsyncMock(return_value=None)

    async def test_get_all_agent_mapping_success(self):
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[{"agent_id": "123", "did": "2001"}]
        )
        self.collection_mock.find.return_value = mock_cursor

        result = await self.repository.get_all_agent_mapping()

        self.collection_mock.find.assert_called_once_with({"is_active": True})
        mock_cursor.to_list.assert_called_once_with(length=None)
        assert result == [{"agent_id": "123", "did": "2001"}]
        self.logger.debug.assert_called_once()

    async def test_get_all_agent_mapping_empty_result(self):
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        self.collection_mock.find.return_value = mock_cursor

        result = await self.repository.get_all_agent_mapping()

        self.collection_mock.find.assert_called_once_with({"is_active": True})
        assert result == []
        self.logger.debug.assert_called_once()

    async def test_get_all_agent_mapping_exception(self):
        self.collection_mock.find.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await self.repository.get_all_agent_mapping()

        self.collection_mock.find.assert_called_once_with({"is_active": True})
        self.logger.error.assert_called_once()
