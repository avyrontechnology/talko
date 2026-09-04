from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.vendor.dto import Contract
from src.components.vendor.validation import VendorValidator
from src.utils.enums import VendorType


@pytest.mark.asyncio
class TestVendorValidator:
    """Unit tests for VendorValidator class."""

    @classmethod
    def setup_class(cls):
        cls.mock_repository = AsyncMock()
        cls.mock_logger = MagicMock()
        cls.validator = VendorValidator(
            repository=cls.mock_repository, logger=cls.mock_logger
        )

    async def test_validate_vendor_create_success(self):
        """Should pass validation if required fields exist and vendor type doesn't exist already."""
        vendor_data = Contract.VendorCreate(
            name="airtel", vendor_type=VendorType.AIRTEL
        )

        self.mock_repository.find_vendor_by_type.return_value = None

        await self.validator.validate_vendor_create(vendor_data)

        self.mock_repository.find_vendor_by_type.assert_called_once_with(
            "airtel", "airtel"
        )
        self.mock_logger.error.assert_not_called()

    async def test_validate_vendor_create_duplicate_vendor_type(self):
        """Should raise ValueError if vendor with same type already exists."""
        vendor_data = Contract.VendorCreate(
            name="airtel", vendor_type=VendorType.AIRTEL
        )

        self.mock_repository.find_vendor_by_type.return_value = {
            "id": 123,
            "vendor_type": "airtel",
            "name": "airtel",
        }

        with pytest.raises(ValueError, match=r"Vendor already exists."):
            await self.validator.validate_vendor_create(vendor_data)

        self.mock_logger.error.assert_called_once_with(
            "Vendor with type airtel and name airtel already exists."
        )

    async def test_validate_vendor_create_missing_required_fields(self, monkeypatch):
        """Should raise ValueError if required fields are missing."""

        monkeypatch.setattr(
            "src.components.vendor.validation.validate_required_fields",
            lambda *_: (_ for _ in ()).throw(ValueError("Missing fields")),
        )

        vendor_data = Contract.VendorCreate(name="", vendor_type=VendorType.AIRTEL)

        with pytest.raises(ValueError, match="Missing fields"):
            await self.validator.validate_vendor_create(vendor_data)
