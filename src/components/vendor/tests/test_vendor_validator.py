from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.vendor.dto import TalkoContract
from src.components.vendor.validation import TalkoVendorValidator
from src.utils.enums import TalkoVendorType


@pytest.mark.asyncio
class TestVendorValidator:
    """Unit tests for TalkoVendorValidator class."""

    @classmethod
    def setup_class(cls):
        cls.mock_repository = AsyncMock()
        cls.mock_logger = MagicMock()
        cls.validator = TalkoVendorValidator(
            repository=cls.mock_repository, logger=cls.mock_logger
        )

    async def test_validate_vendor_create_success(self):
        """Should pass validation if required fields exist and vendor type doesn't exist already."""
        vendor_data = TalkoContract.VendorCreate(
            name="airtel", vendor_type=TalkoVendorType.AIRTEL
        )

        self.mock_repository.find_vendor_by_type.return_value = None

        await self.validator.validate_vendor_create(vendor_data)

        self.mock_repository.find_vendor_by_type.assert_called_once_with(
            "airtel", "airtel"
        )
        self.mock_logger.error.assert_not_called()

    async def test_validate_vendor_create_duplicate_vendor_type(self):
        """Should raise ValueError if vendor with same type already exists."""
        vendor_data = TalkoContract.VendorCreate(
            name="airtel", vendor_type=TalkoVendorType.AIRTEL
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

        vendor_data = TalkoContract.VendorCreate(name="", vendor_type=TalkoVendorType.AIRTEL)

        with pytest.raises(ValueError, match="Missing fields"):
            await self.validator.validate_vendor_create(vendor_data)
