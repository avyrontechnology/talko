from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.components.call_assets.repository import AssetRepository
from src.components.call_assets.models import AssetsModel
from src.components.call_assets.messages import DUPLICATE_ASSET_INSERTION
from src.exceptions import BadRequestError
from src.loggers.holler_service_logger import HollerServiceLogger
from pymongo.results import InsertOneResult


@pytest.mark.asyncio
class TestCallAssetsRepository:

    @pytest.fixture
    def setup(self):
        mock_db_manager = MagicMock()
        mock_logger = MagicMock(spec=HollerServiceLogger)
        repo = AssetRepository(mock_db_manager, mock_logger)
        return repo, mock_db_manager, mock_logger

    async def test_get_digital_asset_by_partner_id_found(self, setup):
        repo, mock_db_manager, mock_logger = setup
        partner_id = 1
        asset_type = "GLOBAL_MEDIA_CONSTANT"
        mock_collection = AsyncMock()
        mock_doc = {
            "_id": "some_id",
            "name": "sample.mp3",
            "partner_id": partner_id,
            "version": 1,
            "asset_type": asset_type,
        }
        mock_collection.find_one.return_value = mock_doc
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        result = await repo.get_digital_asset_by_partner_id(partner_id, asset_type)

        assert isinstance(result, dict)
        assert result["id"] == str(mock_doc["_id"])
        assert result["name"] == "sample.mp3"
        mock_logger.info.assert_any_call(
            f"Found digital asset: {mock_doc}"
        )
        mock_collection.find_one.assert_awaited_once_with(
            {"partner_id": partner_id, "asset_type": asset_type},
            sort=[("created_at", -1)]
        )

    async def test_get_digital_asset_by_partner_id_not_found(self, setup):
        repo, mock_db_manager, mock_logger = setup
        partner_id = 1
        asset_type = "GLOBAL_MEDIA_CONSTANT"
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        result = await repo.get_digital_asset_by_partner_id(partner_id, asset_type)
        assert result is None
        mock_logger.info.assert_any_call("No digital asset found")

    async def test_create_digital_asset_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        partner_id = 1
        asset_type = "GLOBAL_MEDIA_CONSTANT"
        file_name = "sample.mp3"
        user_id = 12
        lead_number = 101
        call_time = 123456
        agent_id = 5


        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_collection.insert_one.return_value = InsertOneResult("mock_id", acknowledged=True)
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        asset = await repo.create_digital_asset(
            partner_id=partner_id,
            asset_type=asset_type,
            file_name=file_name,
            user_id=user_id,
            lead_number=lead_number,
            call_time=call_time,
            agent_id=agent_id,
        )

        assert isinstance(asset, AssetsModel)
        assert asset.version == 1
        assert asset.name == file_name
        assert asset.partner_id == partner_id
        mock_logger.info.assert_any_call("Creating new digital asset with version=1")
        mock_collection.insert_one.assert_awaited_once()

    async def test_create_digital_asset_version_increment(self, setup):
        repo, mock_db_manager, mock_logger = setup
        partner_id = 1
        asset_type = "GLOBAL_MEDIA_CONSTANT"
        file_name = "sample.mp3"
        user_id = 12
        lead_number = 101


        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = {"version": 2}
        mock_collection.insert_one.return_value = InsertOneResult("mock_id", acknowledged=True)
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        asset = await repo.create_digital_asset(
            partner_id=partner_id,
            asset_type=asset_type,
            file_name=file_name,
            user_id=user_id,
            lead_number=lead_number,
        )

        assert asset.version == 3
        mock_logger.info.assert_any_call("Creating new digital asset with version=3")

    async def test_create_digital_asset_duplicate_key_error(self, setup):
        repo, mock_db_manager, mock_logger = setup
        partner_id = 1
        asset_type = "GLOBAL_MEDIA_CONSTANT"
        file_name = "sample.mp3"
        user_id = 12
        lead_number = 101

        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_collection.insert_one.side_effect = BadRequestError(DUPLICATE_ASSET_INSERTION)
        mock_db_manager.collection.return_value.__aenter__.return_value = mock_collection

        with pytest.raises(BadRequestError):
            await repo.create_digital_asset(
                partner_id=partner_id,
                asset_type=asset_type,
                file_name=file_name,
                user_id=user_id,
                lead_number=lead_number,
            )