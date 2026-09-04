import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.components.call_assets.services import TalkoAssetService
from src.components.digital_assets.constants import TalkoDigitalAssetEnum
from src.components.digital_assets.schema import TalkoDigitalAssetResponse
from src.components.call_assets.models import TalkoAssetsModel
from src.components.digital_assets.utils import TalkoDigitalAssetUtils
from src.components.digital_assets.storage.helper import TalkoStorageHelper
from src.exceptions import TalkoResourceNotFound, TalkoInvalidAssetTypeError


@pytest.mark.asyncio
class TestAssetService:
    def setup_method(self):
        self.mock_repo = AsyncMock()
        self.mock_logger = MagicMock()
        self.service = TalkoAssetService(repository=self.mock_repo, logger=self.mock_logger)

    async def test_get_digital_asset_details_success(self):
        partner_id = 1
        asset_type = "GLOBAL_MEDIA_CONSTANT"
        asset_doc = {
            "id": "abc123",
            "name": "sample.mp3",
            "partner_id": partner_id,
            "version": 1,
            "asset_type": asset_type,
            "additional_info": None,
            "created_by": 1,
            "updated_by": 1,
        }

        self.mock_repo.get_digital_asset_by_partner_id.return_value = asset_doc
        with patch.object(TalkoStorageHelper, "get_presigned_url", return_value="https://presigned.url/sample.mp3"), \
             patch.object(TalkoDigitalAssetUtils, "is_valid_asset_type", return_value=True):
            result = await self.service.get_digital_asset_details(partner_id, asset_type)

        assert result["id"] == "abc123"
        assert result["asset_type"] == TalkoDigitalAssetEnum[asset_type]
        assert result["url"] == "https://presigned.url/sample.mp3"
        self.mock_logger.info.assert_called()

    async def test_get_digital_asset_details_not_found(self):
        partner_id = 1
        asset_type = "GLOBAL_MEDIA_CONSTANT"
        self.mock_repo.get_digital_asset_by_partner_id.return_value = None
        with patch.object(TalkoDigitalAssetUtils, "is_valid_asset_type", return_value=True):
            with pytest.raises(TalkoResourceNotFound):
                await self.service.get_digital_asset_details(partner_id, asset_type)
        self.mock_logger.error.assert_called()

    async def test_get_digital_asset_details_invalid_type(self):
        partner_id = 1
        asset_type = "INVALID_TYPE"
        with patch.object(TalkoDigitalAssetUtils, "is_valid_asset_type", return_value=False):
            with pytest.raises(TalkoInvalidAssetTypeError):
                await self.service.get_digital_asset_details(partner_id, asset_type)
        self.mock_logger.error.assert_called_once()
        self.mock_logger.error.assert_called_with(
            "An unexpected error occurred while fetching digital asset details for partner_id {}: Invalid asset provided".format(partner_id)
        )
