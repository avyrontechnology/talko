import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from src.components.vendor.repository import VendorRepository
from src.components.vendor_config.repository import VendorConfigRepository
from src.components.vendor_config.validation import VendorConfigValidator
from src.loggers.holler_service_logger import HollerServiceLogger


@pytest.mark.asyncio
class TestVendorConfigValidator:
    @pytest.fixture
    def mock_vendor_repository(self):
        return MagicMock(spec=VendorRepository)

    @pytest.fixture
    def mock_logger(self):
        return MagicMock(spec=HollerServiceLogger)

    @pytest.fixture
    def mock_vendor_config_repository(self):
        return MagicMock(spec=VendorConfigRepository)

    @pytest.fixture
    def validator(
        self, mock_vendor_repository, mock_logger, mock_vendor_config_repository
    ):
        return VendorConfigValidator(
            repository=mock_vendor_repository,
            logger=mock_logger,
            vendor_config_repository=mock_vendor_config_repository,
        )

    @pytest.fixture
    def mock_vendor_config_create(self):
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {"vendor_id": ObjectId()}
        return mock_config

    async def test_validate_vendor_config_create_missing_field(
        self, validator, mock_vendor_config_create, mock_logger
    ):
        mock_vendor_config_create.model_dump.return_value = {}

        with patch(
            "src.components.vendor_config.validation.validate_required_fields"
        ) as mock_validate:
            mock_validate.side_effect = ValueError(
                "Missing required fields: ['vendor_id']"
            )

            with pytest.raises(
                ValueError, match=re.escape("Missing required fields: ['vendor_id']")
            ):
                await validator.validate_vendor_config_create(mock_vendor_config_create)

            mock_validate.assert_called_once_with({}, ["vendor_id"], mock_logger)

    async def test_validate_vendor_exists_success(
        self, validator, mock_vendor_repository, mock_logger
    ):
        vendor_id = ObjectId()
        mock_vendor_repository.find_vendor_by_id = AsyncMock(
            return_value={"_id": vendor_id, "is_active": True}
        )

        await validator.validate_vendor_exists(vendor_id)

        mock_vendor_repository.find_vendor_by_id.assert_called_once_with(vendor_id)
        mock_logger.error.assert_not_called()

    async def test_validate_vendor_exists_vendor_not_found(
        self, validator, mock_vendor_repository, mock_logger
    ):
        vendor_id = ObjectId()
        mock_vendor_repository.find_vendor_by_id = AsyncMock(return_value=None)

        with pytest.raises(
            ValueError, match=f"Vendor with ID {vendor_id} not found or inactive."
        ):
            await validator.validate_vendor_exists(vendor_id)

        mock_logger.error.assert_called_once_with(
            f"Vendor with ID {vendor_id} not found or inactive."
        )

    async def test_validate_vendor_exists_vendor_inactive(
        self, validator, mock_vendor_repository, mock_logger
    ):
        vendor_id = ObjectId()
        mock_vendor_repository.find_vendor_by_id = AsyncMock(
            return_value={"_id": vendor_id, "is_active": False}
        )

        with pytest.raises(
            ValueError, match=f"Vendor with ID {vendor_id} not found or inactive."
        ):
            await validator.validate_vendor_exists(vendor_id)

        mock_logger.error.assert_called_once_with(
            f"Vendor with ID {vendor_id} not found or inactive."
        )

    async def test_validate_vendor_config_exist_using_vendor_id_fails_when_exists(
        self, validator, mock_vendor_config_repository, mock_logger
    ):
        vendor_id = ObjectId()
        mock_vendor_config_repository.check_vendor_config_exists_for_existing_vendor = (
            AsyncMock(return_value=True)
        )

        with pytest.raises(
            ValueError, match=f"Vendor config for vendor ID {vendor_id} does exist."
        ):
            await validator.validate_vendor_config_exist_using_vendor_id(vendor_id)

        mock_logger.error.assert_called_once_with(
            f"Vendor config for vendor ID {vendor_id} does exist."
        )

    async def test_validate_vendor_config_exist_using_vendor_id_does_not_exist(
        self, validator, mock_vendor_config_repository, mock_logger
    ):
        vendor_id = ObjectId()
        mock_vendor_config_repository.check_vendor_config_exists_for_existing_vendor = (
            AsyncMock(return_value=False)
        )

        with pytest.raises(
            ValueError, match=f"Vendor config for vendor ID {vendor_id} does not exist."
        ):
            await validator.validate_vendor_config_not_exist_using_vendor_id(vendor_id)

        mock_logger.error.assert_called_once_with(
            f"Vendor config for vendor ID {vendor_id} does not exist."
        )

    async def test_validate_vendor_config_exists_success(
        self, validator, mock_vendor_config_repository, mock_logger
    ):
        vendor_config_id = ObjectId()
        mock_vendor_config_repository.check_vendor_config_exists_for_existing_vendor_using_pk_id = AsyncMock(
            return_value=True
        )

        await validator.validate_vendor_config_exists(vendor_config_id)

        mock_vendor_config_repository.check_vendor_config_exists_for_existing_vendor_using_pk_id.assert_called_once_with(
            vendor_config_id
        )
        mock_logger.error.assert_not_called()

    async def test_validate_vendor_config_exists_not_found(
        self, validator, mock_vendor_config_repository, mock_logger
    ):
        vendor_config_id = ObjectId()
        mock_vendor_config_repository.check_vendor_config_exists_for_existing_vendor_using_pk_id = AsyncMock(
            return_value=False
        )

        with pytest.raises(
            ValueError,
            match=f"Vendor config for vendor config ID {vendor_config_id} does not exist.",
        ):
            await validator.validate_vendor_config_exists(vendor_config_id)

        mock_logger.error.assert_called_once_with(
            f"Vendor config for vendor config ID {vendor_config_id} does not exist."
        )
