from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.partner_config.dto import TalkoContract
from src.components.partner_config.helper import TalkoPartnerConfigHelper
from src.components.partner_config.services import TalkoPartnerConfigService
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound


@pytest.mark.asyncio
class TestPartnerConfigService:
    @pytest.fixture(autouse=True)
    def setup_service(self):
        # Mock dependencies
        repository = AsyncMock()
        logger = MagicMock()
        datetime_util = MagicMock()
        datetime_util.get_current_time.return_value = 1234567890
        vendor_validator = AsyncMock()
        vendor_config_service = AsyncMock()
        vendor_config_validator = AsyncMock()
        vendor_config_repository = AsyncMock()
        partner_config_validator = AsyncMock()
        did_management_service = AsyncMock()

        self.service = TalkoPartnerConfigService(
            repository=repository,
            logger=logger,
            datetime_util=datetime_util,
            validator=vendor_validator,
            vendor_config_service=vendor_config_service,
            vendor_config_validator=vendor_config_validator,
            vendor_config_repository=vendor_config_repository,
            partner_config_validator=partner_config_validator,
            did_management_service=did_management_service,
        )

    async def test_create_partner_config_success(self, monkeypatch):
        config = TalkoContract.PartnerConfigCreate(
            partner_id=1,
            vendor_id=str(ObjectId()),
        )

        # Patch helper methods
        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "validate_and_prepare_config",
            AsyncMock(return_value=ObjectId()),
        )
        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "handle_did_assignment",
            AsyncMock(
                return_value={
                    "is_active": True,  # Add missing required fields
                    "did_index": 0,
                    "enable_round_robin": False,
                    "enable_agent_mapping": False,
                    "enable_service_board": False,
                    "service_board_ids": [],
                    "board_did_counts": {},
                    "agent_mapping_ids": [],
                    "round_robin_did_count": None,
                }
            ),
        )

        self.service.repository.insert_partner_config = AsyncMock(
            return_value=ObjectId()
        )

        response = await self.service.create_partner_config(config)

        assert response.id is not None
        assert response.message == "Partner config created successfully."

    async def test_create_partner_config_round_robin_and_service_board_error(
        self, monkeypatch
    ):
        config = TalkoContract.PartnerConfigCreate(
            partner_id=1,
            vendor_id=str(ObjectId()),
            enable_service_board=True,
            board_did_counts={"101": 1},
            service_board_ids=[101],
            enable_round_robin=True,
            round_robin_did_count=1,
        )

        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "validate_and_prepare_config",
            AsyncMock(return_value=ObjectId()),
        )

        with pytest.raises(
            TalkoBadRequestError, match="Round-robin and service board cannot"
        ):
            await self.service.create_partner_config(config)

    async def test_create_partner_config_missing_required_fields(self, monkeypatch):
        # Missing board_did_counts and service_board_ids
        config = TalkoContract.PartnerConfigCreate(
            partner_id=1,
            vendor_id=str(ObjectId()),
            enable_service_board=True,
            board_did_counts=None,
            service_board_ids=None,
            enable_agent_mapping=True,
            agent_mapping_ids=None,
            enable_round_robin=True,
            round_robin_did_count=None,
        )

        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "validate_and_prepare_config",
            AsyncMock(return_value=ObjectId()),
        )

        with pytest.raises(
            TalkoBadRequestError,
            match="Round-robin and service board cannot be enabled simultaneously",
        ):
            await self.service.create_partner_config(config)

    async def test_get_all_partner_configs_success(self):
        obj_id = ObjectId()
        vendor_id = ObjectId()
        self.service.repository.find_all_partner_configs.return_value = [
            {
                "_id": obj_id,
                "partner_id": 1,
                "vendor_id": vendor_id,
                "is_active": True,
                "did_index": 0,
                "enable_round_robin": False,
                "enable_agent_mapping": False,
                "enable_service_board": False,
                "service_board_ids": [],
                "board_did_counts": {},
                "agent_mapping_ids": [],
                "round_robin_did_count": None,
                "created_at": 1234567890,
                "updated_at": 1234567890,
                "message": "mocked",
            }
        ]

        result = await self.service.get_all_partner_configs()

        assert len(result) == 1
        assert result[0].partner_id == 1
        assert result[0].vendor_id == str(vendor_id)

    async def test_get_partner_config_by_id_success(self):
        obj_id = ObjectId()
        vendor_id = ObjectId()
        self.service.repository.find_partner_config_by_id.return_value = {
            "_id": obj_id,
            "partner_id": 1,
            "vendor_id": vendor_id,
            "is_active": True,
            "did_index": 0,
            "enable_round_robin": False,
            "enable_agent_mapping": False,
            "enable_service_board": False,
            "service_board_ids": [],
            "board_did_counts": {},
            "agent_mapping_ids": [],
            "round_robin_did_count": None,
            "created_at": 1234567890,
            "updated_at": 1234567890,
            "message": "mocked",
        }

        result = await self.service.get_partner_config_by_id(str(obj_id))

        assert result.partner_id == 1
        assert result.vendor_id == str(vendor_id)

    async def test_get_partner_config_by_id_not_found(self):
        obj_id = ObjectId()
        self.service.repository.find_partner_config_by_id.return_value = None

        with pytest.raises(TalkoResourceNotFound):
            await self.service.get_partner_config_by_id(str(obj_id))

        # Logger is called twice in the service
        assert self.service.logger.error.call_count == 2


class TestPartnerConfigServiceValidation:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = TalkoPartnerConfigService(
            repository=AsyncMock(),
            vendor_config_repository=AsyncMock(),
            vendor_config_service=AsyncMock(),
            did_management_service=AsyncMock(),
            partner_config_validator=MagicMock(),
            vendor_config_validator=MagicMock(),
            validator=MagicMock(),
            logger=MagicMock(),
            datetime_util=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_missing_service_board_fields_raises(self, monkeypatch):
        config = TalkoContract.PartnerConfigCreate(
            partner_id=1,
            vendor_id=str(ObjectId()),
            enable_service_board=True,
            service_board_ids=None,
            board_did_counts=None,
            enable_agent_mapping=False,
            agent_mapping_ids=None,
            enable_round_robin=False,
            round_robin_did_count=None,
        )

        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "validate_and_prepare_config",
            AsyncMock(return_value=ObjectId()),
        )
        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "handle_did_assignment",
            AsyncMock(return_value={"is_active": True}),
        )

        with pytest.raises(
            TalkoBadRequestError, match="service_board_ids and board_did_counts are required"
        ):
            await self.service.create_partner_config(config)

    @pytest.mark.asyncio
    async def test_missing_agent_mapping_fields_raises(self, monkeypatch):
        config = TalkoContract.PartnerConfigCreate(
            partner_id=1,
            vendor_id=str(ObjectId()),
            enable_service_board=False,
            enable_agent_mapping=True,
            agent_mapping_ids=None,
            enable_round_robin=False,
            round_robin_did_count=None,
        )

        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "validate_and_prepare_config",
            AsyncMock(return_value=ObjectId()),
        )
        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "handle_did_assignment",
            AsyncMock(return_value={"is_active": True}),
        )

        with pytest.raises(TalkoBadRequestError, match="agent_mapping_ids is required"):
            await self.service.create_partner_config(config)

    @pytest.mark.asyncio
    async def test_missing_round_robin_fields_raises(self, monkeypatch):
        config = TalkoContract.PartnerConfigCreate(
            partner_id=1,
            vendor_id=str(ObjectId()),
            enable_service_board=False,
            enable_agent_mapping=False,
            enable_round_robin=True,
            round_robin_did_count=None,
        )

        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "validate_and_prepare_config",
            AsyncMock(return_value=ObjectId()),
        )
        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "handle_did_assignment",
            AsyncMock(return_value={"is_active": True}),
        )

        with pytest.raises(TalkoBadRequestError, match="round_robin_did_count is required"):
            await self.service.create_partner_config(config)

    @pytest.mark.asyncio
    async def test_exception_logged_and_raised(self, monkeypatch):
        config = TalkoContract.PartnerConfigCreate(
            partner_id=1,
            vendor_id=str(ObjectId()),
        )

        # Force validate_and_prepare_config to raise a generic exception
        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "validate_and_prepare_config",
            AsyncMock(side_effect=Exception("Unexpected error")),
        )

        with pytest.raises(Exception, match="Unexpected error"):
            await self.service.create_partner_config(config)

        # Ensure logger.error was called
        self.service.logger.error.assert_called_once()


class TestPartnerConfigServiceException:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = TalkoPartnerConfigService(
            repository=AsyncMock(),
            vendor_config_repository=AsyncMock(),
            vendor_config_service=AsyncMock(),
            did_management_service=AsyncMock(),
            partner_config_validator=MagicMock(),
            vendor_config_validator=MagicMock(),
            validator=MagicMock(),
            logger=MagicMock(),
            datetime_util=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_generic_exception_is_logged_and_raised(self, monkeypatch):
        config = TalkoContract.PartnerConfigCreate(
            partner_id=1,
            vendor_id=str(ObjectId()),
        )

        # Force validate_and_prepare_config to raise a generic exception
        monkeypatch.setattr(
            TalkoPartnerConfigHelper,
            "validate_and_prepare_config",
            AsyncMock(side_effect=Exception("Unexpected error")),
        )

        with pytest.raises(Exception, match="Unexpected error"):
            await self.service.create_partner_config(config)

        # Assert logger.error was called with the exception message
        self.service.logger.error.assert_called_once()
        logged_msg = self.service.logger.error.call_args[0][0]
        assert "Error creating partner config: Unexpected error" in logged_msg


class TestPartnerConfigServiceGetAllException:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = TalkoPartnerConfigService(
            repository=AsyncMock(),
            vendor_config_repository=AsyncMock(),
            vendor_config_service=AsyncMock(),
            did_management_service=AsyncMock(),
            partner_config_validator=MagicMock(),
            vendor_config_validator=MagicMock(),
            validator=MagicMock(),
            logger=MagicMock(),
            datetime_util=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_get_all_partner_configs_exception_logged(self):
        # Force repository to raise
        self.service.repository.find_all_partner_configs.side_effect = Exception(
            "DB error"
        )

        with pytest.raises(Exception, match="DB error"):
            await self.service.get_all_partner_configs()

        self.service.logger.error.assert_called_once()
        logged_msg = self.service.logger.error.call_args[0][0]
        assert "Failed to retrieve partner configs: DB error" in logged_msg
