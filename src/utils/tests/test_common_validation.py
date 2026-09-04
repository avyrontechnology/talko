from unittest.mock import MagicMock

import pytest

from src.utils.common_validation import validate_required_fields


class TestValidateRequiredFields:
    def setup_method(self):
        self.mock_logger = MagicMock()

    def test_missing_single_field(self):
        data = {
            "name": "Vendor A",
        }
        required_fields = ["name", "vendor_type"]

        with pytest.raises(
            ValueError, match=r"Missing required fields: \['vendor_type'\]"
        ):
            validate_required_fields(data, required_fields, self.mock_logger)

        self.mock_logger.error.assert_called_once()
        self.mock_logger.info.assert_called_once_with("Missing field: ['vendor_type'].")

    def test_missing_multiple_fields(self):
        data = {}
        required_fields = ["name", "vendor_type"]

        with pytest.raises(
            ValueError, match=r"Missing required fields: \['name', 'vendor_type'\]"
        ):
            validate_required_fields(data, required_fields, self.mock_logger)

        self.mock_logger.error.assert_called_once()
        self.mock_logger.info.assert_called_once_with(
            "Missing field: ['name', 'vendor_type']."
        )

    def test_field_with_none_value(self):
        data = {
            "name": None,
            "vendor_type": "airtel",
        }
        required_fields = ["name", "vendor_type"]

        with pytest.raises(ValueError, match=r"Missing required fields: \['name'\]"):
            validate_required_fields(data, required_fields, self.mock_logger)

        self.mock_logger.error.assert_called_once()
        self.mock_logger.info.assert_called_once_with("Missing field: ['name'].")
