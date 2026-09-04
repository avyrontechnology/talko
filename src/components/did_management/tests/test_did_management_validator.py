from unittest.mock import AsyncMock, Mock

import pytest
from bson import ObjectId

from src.components.did_management.validator import TalkoDidValidator
from src.components.partner_config.repository import TalkoPartnerConfigRepository
from src.components.vendor_config.repository import TalkoVendorConfigRepository
from src.loggers.talko_service_logger import TalkoServiceLogger


@pytest.fixture
def mock_vendor_config_repository():
    return Mock(spec=TalkoVendorConfigRepository)


@pytest.fixture
def mock_partner_config_repository():
    return Mock(spec=TalkoPartnerConfigRepository)


@pytest.fixture
def mock_logger():
    return Mock(spec=TalkoServiceLogger)


@pytest.fixture
def did_validator(
    mock_vendor_config_repository, mock_partner_config_repository, mock_logger
):
    return TalkoDidValidator(
        vendor_config_repository=mock_vendor_config_repository,
        partner_config_repository=mock_partner_config_repository,
        logger=mock_logger,
    )


class TestDidValidator:
    @pytest.mark.asyncio
    async def test_validate_did_assignment_success(
        self,
        did_validator,
        mock_vendor_config_repository,
        mock_partner_config_repository,
        mock_logger,
    ):
        # Arrange
        vendor_id = "507f1f77bcf86cd799439011"
        partner_id = 1
        did_data = {
            "did_number": "12345",
            "vendor_id": vendor_id,
            "partner_id": partner_id,
        }
        mock_vendor_config_repository.find_configs_by_vendor_id = AsyncMock(
            return_value=[{"vendor_id": ObjectId(vendor_id)}]
        )
        mock_partner_config_repository.find_partner_config_by_id = AsyncMock(
            return_value={"partner_id": partner_id}
        )

        # Act
        await did_validator.validate_did_assignment(did_data)

        # Assert
        mock_vendor_config_repository.find_configs_by_vendor_id.assert_awaited_with(
            ObjectId(vendor_id)
        )
        mock_partner_config_repository.find_partner_config_by_id.assert_awaited_with(
            partner_id
        )
        mock_logger.info.assert_any_call(
            "Validating DID assignment for DID: {}".format(did_data["did_number"])
        )
        mock_logger.info.assert_any_call(
            "DID assignment validation successful for DID: {}".format(
                did_data["did_number"]
            )
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_did_assignment_success_placeholder_partner(
        self,
        did_validator,
        mock_vendor_config_repository,
        mock_partner_config_repository,
        mock_logger,
    ):
        # Arrange
        vendor_id = "507f1f77bcf86cd799439011"
        partner_id = 0  # Placeholder partner_id
        did_data = {
            "did_number": "12345",
            "vendor_id": vendor_id,
            "partner_id": partner_id,
        }
        mock_vendor_config_repository.find_configs_by_vendor_id = AsyncMock(
            return_value=[{"vendor_id": ObjectId(vendor_id)}]
        )

        # Act
        await did_validator.validate_did_assignment(did_data)

        # Assert
        mock_vendor_config_repository.find_configs_by_vendor_id.assert_awaited_with(
            ObjectId(vendor_id)
        )
        mock_partner_config_repository.find_partner_config_by_id.assert_not_called()
        mock_logger.info.assert_any_call(
            "Validating DID assignment for DID: {}".format(did_data["did_number"])
        )
        mock_logger.info.assert_any_call(
            "DID assignment validation successful for DID: {}".format(
                did_data["did_number"]
            )
        )
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_did_assignment_invalid_vendor_id(
        self,
        did_validator,
        mock_vendor_config_repository,
        mock_partner_config_repository,
        mock_logger,
    ):
        # Arrange
        vendor_id = "invalid_object_id"
        did_data = {"did_number": "12345", "vendor_id": vendor_id, "partner_id": 1}

        # Act/Assert
        with pytest.raises(ValueError, match="Invalid vendor_id format."):
            await did_validator.validate_did_assignment(did_data)
        mock_vendor_config_repository.find_configs_by_vendor_id.assert_not_called()
        mock_partner_config_repository.find_partner_config_by_id.assert_not_called()
        mock_logger.info.assert_called_with(
            "Validating DID assignment for DID: {}".format(did_data["did_number"])
        )
        mock_logger.error.assert_called_with(
            "Failed to validate DID assignment: Invalid vendor_id format."
        )

    @pytest.mark.asyncio
    async def test_validate_did_assignment_missing_vendor_config(
        self,
        did_validator,
        mock_vendor_config_repository,
        mock_partner_config_repository,
        mock_logger,
    ):
        # Arrange
        vendor_id = "507f1f77bcf86cd799439011"
        partner_id = 1
        did_data = {
            "did_number": "12345",
            "vendor_id": vendor_id,
            "partner_id": partner_id,
        }
        mock_vendor_config_repository.find_configs_by_vendor_id = AsyncMock(
            return_value=[]
        )

        # Act/Assert
        with pytest.raises(
            ValueError, match=f"Vendor config not found for vendor_id: {vendor_id}"
        ):
            await did_validator.validate_did_assignment(did_data)
        mock_vendor_config_repository.find_configs_by_vendor_id.assert_awaited_with(
            ObjectId(vendor_id)
        )
        mock_partner_config_repository.find_partner_config_by_id.assert_not_called()
        mock_logger.info.assert_called_with(
            "Validating DID assignment for DID: {}".format(did_data["did_number"])
        )
        mock_logger.error.assert_called_with(
            f"Failed to validate DID assignment: Vendor config not found for vendor_id: {vendor_id}"
        )

    @pytest.mark.asyncio
    async def test_validate_did_assignment_missing_partner_config(
        self,
        did_validator,
        mock_vendor_config_repository,
        mock_partner_config_repository,
        mock_logger,
    ):
        # Arrange
        vendor_id = "507f1f77bcf86cd799439011"
        partner_id = 1
        did_data = {
            "did_number": "12345",
            "vendor_id": vendor_id,
            "partner_id": partner_id,
        }
        mock_vendor_config_repository.find_configs_by_vendor_id = AsyncMock(
            return_value=[{"vendor_id": ObjectId(vendor_id)}]
        )
        mock_partner_config_repository.find_partner_config_by_id = AsyncMock(
            return_value=None
        )

        # Act/Assert
        with pytest.raises(
            ValueError, match=f"Partner config not found for partner_id: {partner_id}"
        ):
            await did_validator.validate_did_assignment(did_data)
        mock_vendor_config_repository.find_configs_by_vendor_id.assert_awaited_with(
            ObjectId(vendor_id)
        )
        mock_partner_config_repository.find_partner_config_by_id.assert_awaited_with(
            partner_id
        )
        mock_logger.info.assert_called_with(
            "Validating DID assignment for DID: {}".format(did_data["did_number"])
        )
        mock_logger.error.assert_called_with(
            f"Failed to validate DID assignment: Partner config not found for partner_id: {partner_id}"
        )

    @pytest.mark.asyncio
    async def test_validate_did_assignment_repository_error(
        self,
        did_validator,
        mock_vendor_config_repository,
        mock_partner_config_repository,
        mock_logger,
    ):
        # Arrange
        vendor_id = "507f1f77bcf86cd799439011"
        partner_id = 1
        did_data = {
            "did_number": "12345",
            "vendor_id": vendor_id,
            "partner_id": partner_id,
        }
        mock_vendor_config_repository.find_configs_by_vendor_id = AsyncMock(
            side_effect=Exception("Database error")
        )

        # Act/Assert
        with pytest.raises(Exception, match="Database error"):
            await did_validator.validate_did_assignment(did_data)
        mock_vendor_config_repository.find_configs_by_vendor_id.assert_awaited_with(
            ObjectId(vendor_id)
        )
        mock_partner_config_repository.find_partner_config_by_id.assert_not_called()
        mock_logger.info.assert_called_with(
            "Validating DID assignment for DID: {}".format(did_data["did_number"])
        )
        mock_logger.error.assert_called_with(
            "Failed to validate DID assignment: Database error"
        )
