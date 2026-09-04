from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.partner_config.dto import TalkoContract
from src.components.partner_config.helper import TalkoPartnerConfigHelper
from src.exceptions import TalkoBadRequestError, TalkoConflictError


@pytest.mark.asyncio
class TestPartnerConfigHelper:
    @pytest.fixture
    def config(self):
        return TalkoContract.PartnerConfigCreate(
            partner_id=123,
            vendor_id=str(ObjectId()),
            vendor_config_id=str(ObjectId()),
            enable_service_board=False,
            board_did_counts=None,
            service_board_ids=None,
            enable_agent_mapping=False,
            agent_mapping_ids=None,
            enable_round_robin=False,
            round_robin_did_count=None,
        )

    async def test_validate_and_prepare_config_invalid_vendor_id(self, config):
        mock_config = MagicMock()
        mock_config.vendor_id = "not-an-object-id"
        mock_config.partner_id = 123

        vendor_validator = AsyncMock()
        partner_validator = AsyncMock()
        repository = AsyncMock()
        logger = MagicMock()

        with pytest.raises(ValueError, match="Invalid vendor_id format."):
            await TalkoPartnerConfigHelper.validate_and_prepare_config(
                mock_config, vendor_validator, partner_validator, repository, logger
            )
        logger.error.assert_called()

    async def test_validate_and_prepare_config_conflict_error(self, config):
        vendor_validator = AsyncMock()
        partner_validator = AsyncMock()
        repository = AsyncMock()
        repository.find_partner_config_by_id.return_value = {"partner_id": 123}
        logger = MagicMock()

        with pytest.raises(
            TalkoConflictError, match="Partner config with partner_id already exists."
        ):
            await TalkoPartnerConfigHelper.validate_and_prepare_config(
                config, vendor_validator, partner_validator, repository, logger
            )

    async def test_validate_and_prepare_config_success(self, config):
        vendor_validator = AsyncMock()
        partner_validator = AsyncMock()
        repository = AsyncMock()
        repository.find_partner_config_by_id.return_value = None
        logger = MagicMock()

        vendor_id = await TalkoPartnerConfigHelper.validate_and_prepare_config(
            config, vendor_validator, partner_validator, repository, logger
        )

        assert isinstance(vendor_id, ObjectId)
        vendor_validator.validate_vendor_exists.assert_awaited_once()

    async def test_handle_did_assignment_no_available_dids(self, config):
        did_service = AsyncMock()
        did_service.get_available_dids.return_value = []
        vendor_id = ObjectId()

        result = await TalkoPartnerConfigHelper.handle_did_assignment(
            config, vendor_id, AsyncMock(), AsyncMock(), did_service, MagicMock()
        )
        assert result["is_active"] is True

    async def test_handle_did_assignment_insufficient_dids(self, config):
        config.enable_agent_mapping = True
        config.agent_mapping_ids = [1, 2]
        did_service = AsyncMock()
        did_service.get_available_dids.return_value = ["d1"]
        vendor_id = ObjectId()
        logger = MagicMock()

        with pytest.raises(TalkoBadRequestError, match="Insufficient available DIDs"):
            await TalkoPartnerConfigHelper.handle_did_assignment(
                config,
                vendor_id,
                vendor_config_repository=AsyncMock(),
                vendor_config_service=AsyncMock(),
                did_management_service=did_service,
                logger=logger,
            )

    async def test_handle_did_assignment_with_service_board(self, config):
        config.enable_service_board = True
        config.board_did_counts = {"101": 2}
        config.service_board_ids = [101]

        did_service = AsyncMock()
        did_service.get_available_dids.return_value = ["d1", "d2"]
        vendor_id = ObjectId()
        logger = MagicMock()

        result = await TalkoPartnerConfigHelper.handle_did_assignment(
            config,
            vendor_id,
            vendor_config_repository=AsyncMock(),
            vendor_config_service=AsyncMock(),
            did_management_service=did_service,
            logger=logger,
        )

        assert "service_board_ids" in result
        assert did_service.update_did.call_count == 2

    async def test_handle_did_assignment_with_agent_mapping(self, config):
        config.enable_agent_mapping = True
        config.agent_mapping_ids = [1001, 1002]

        did_service = AsyncMock()
        did_service.get_available_dids.return_value = ["d1", "d2"]
        vendor_id = ObjectId()
        logger = MagicMock()

        result = await TalkoPartnerConfigHelper.handle_did_assignment(
            config,
            vendor_id,
            vendor_config_repository=AsyncMock(),
            vendor_config_service=AsyncMock(),
            did_management_service=did_service,
            logger=logger,
        )

        assert result["agent_mapping_ids"] == [1001, 1002]
        did_service.update_did.assert_any_await(
            did_number="d1",
            vendor_id=str(vendor_id),
            partner_id=config.partner_id,
            service_board_id=None,
            agent_id=1001,
            vendor_config_id=ObjectId(config.vendor_config_id),
        )

    async def test_handle_did_assignment_round_robin_conflicts(self, config):
        config.enable_round_robin = True
        config.enable_service_board = True
        config.board_did_counts = {"101": 1}

        did_service = AsyncMock()
        did_service.get_available_dids.return_value = ["d1"]
        vendor_id = ObjectId()
        logger = MagicMock()

        with pytest.raises(
            TalkoBadRequestError, match="Round-robin cannot be enabled with service board."
        ):
            await TalkoPartnerConfigHelper.handle_did_assignment(
                config,
                vendor_id,
                vendor_config_repository=AsyncMock(),
                vendor_config_service=AsyncMock(),
                did_management_service=did_service,
                logger=logger,
            )

    async def test_handle_did_assignment_round_robin_success(self, config):
        config.enable_round_robin = True
        config.round_robin_did_count = 1

        did_service = AsyncMock()
        did_service.get_available_dids.return_value = ["d1"]
        vendor_id = ObjectId()
        logger = MagicMock()

        result = await TalkoPartnerConfigHelper.handle_did_assignment(
            config,
            vendor_id,
            vendor_config_repository=AsyncMock(),
            vendor_config_service=AsyncMock(),
            did_management_service=did_service,
            logger=logger,
        )

        assert result["round_robin_did_count"] == 1
        did_service.update_did.assert_awaited_once()

    def test_calculate_num_dids_all_enabled(self, config):
        config.enable_service_board = True
        config.board_did_counts = {"101": 2}
        config.enable_agent_mapping = True
        config.agent_mapping_ids = [1, 2, 3]
        config.enable_round_robin = True
        config.round_robin_did_count = 5

        num_dids = TalkoPartnerConfigHelper._calculate_num_dids(config)

        assert num_dids == (2 + 3 + 5)

    async def test_handle_did_assignment_with_round_robin_success(self, config):
        config.enable_round_robin = True
        config.round_robin_did_count = 1

        did_service = AsyncMock()
        did_service.get_available_dids.return_value = ["9999999999"]
        vendor_id = ObjectId()
        result = await TalkoPartnerConfigHelper.handle_did_assignment(
            config, vendor_id, AsyncMock(), AsyncMock(), did_service, MagicMock()
        )
        assert result["round_robin_did_count"] == 1
        did_service.update_did.assert_awaited()

    async def test_update_default_attendance_service_board(self, config):
        config.enable_service_board = True
        config.service_board_ids = [101]
        vendor_id = ObjectId()

        did_service = AsyncMock()
        did_service.get_dids_by_partner_service_board_and_vendor.return_value = [
            {"did_number": "111", "agent_id": 1}
        ]

        result = await TalkoPartnerConfigHelper.update_default_attendance(
            config, vendor_id, did_service, MagicMock()
        )

        assert "service_default_attendance" in result
        assert result["service_default_attendance"][101][0]["phone_number"] == "111"

    async def test_update_default_attendance_round_robin(self, config):
        config.enable_round_robin = True
        config.round_robin_did_count = 2
        vendor_id = ObjectId()

        did_service = AsyncMock()
        did_service.get_dids_by_partner_and_vendor.return_value = [
            {"did_number": "111", "agent_id": None},
            {"did_number": "222", "agent_id": None},
        ]

        result = await TalkoPartnerConfigHelper.update_default_attendance(
            config, vendor_id, did_service, MagicMock()
        )

        assert "round_robin_default_attendance" in result
        assert len(result["round_robin_default_attendance"]["default"]) == 2

    async def test_assign_round_robin_dids_error_cases(self, config):
        vendor_id = ObjectId()
        did_service = AsyncMock()
        config.enable_service_board = True
        with pytest.raises(
            TalkoBadRequestError, match="Round-robin cannot be enabled with service board."
        ):
            await TalkoPartnerConfigHelper._assign_round_robin_dids(
                config, ["d1"], vendor_id, did_service, MagicMock()
            )
        config.enable_service_board = False
        config.enable_round_robin = True
        config.round_robin_did_count = None
        with pytest.raises(TalkoBadRequestError, match="round_robin_did_count is required"):
            await TalkoPartnerConfigHelper._assign_round_robin_dids(
                config, ["d1"], vendor_id, did_service, MagicMock()
            )
