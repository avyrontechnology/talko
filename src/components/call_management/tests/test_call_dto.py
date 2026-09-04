import pytest
from pydantic import ValidationError

from src.components.call_management.dto import Contract
from src.components.call_management.enums import OutboundType


class TestCallCreateDTO:

    def test_valid_with_encryption_and_secret(self):
        """Test that encryption requires lead_secret and passes when provided."""
        data = {
            "lead_id": 1,
            "service_board_id": 10,
            "encryption_enabled": True,
            "lead_secret": "supersecret",
            "agent_number": "9876543210",
        }
        dto = Contract.CallCreate(**data)
        assert dto.lead_secret == "supersecret"
        assert dto.encryption_enabled is True

    def test_valid_without_encryption_and_with_to_number(self):
        """Test that disabled encryption passes when to_number is provided."""
        data = {
            "lead_id": 2,
            "service_board_id": 20,
            "to_number": "1234567890",
            "encryption_enabled": False,
            "agent_number": "9876543210",
        }
        dto = Contract.CallCreate(**data)
        assert dto.to_number == "1234567890"

    def test_valid_dedicated_did(self):
        """Test the field validator for dedicated_did with valid data."""
        data = {
            "service_board_id": 30,
            "agent_number": "9876543210",
            "to_number": "1234567890",
            "encryption_enabled": False,
            "dedicated_did": "918889560593",  # 12 digits
        }
        dto = Contract.CallCreate(**data)
        assert dto.dedicated_did == "918889560593"

    def test_invalid_encryption_enabled_without_lead_secret(self):
        data = {
            "service_board_id": 40,
            "encryption_enabled": True,
            "agent_number": "9876543210",
        }
        with pytest.raises(ValidationError) as exc:
            Contract.CallCreate(**data)
        assert "lead_secret is required" in str(exc.value)

    def test_invalid_encryption_disabled_without_to_number(self):
        data = {
            "service_board_id": 50,
            "encryption_enabled": False,
            "agent_number": "9876543210",
        }
        with pytest.raises(ValidationError) as exc:
            Contract.CallCreate(**data)
        assert "to_number is required" in str(exc.value)

    def test_invalid_missing_agent_number(self):
        data = {
            "service_board_id": 60,
            "encryption_enabled": False,
            "to_number": "1234567890",
        }
        with pytest.raises(ValidationError) as exc:
            Contract.CallCreate(**data)
        assert "agent_number is required" in str(exc.value)

    def test_invalid_outbound_type_value(self):
        data = {
            "service_board_id": 70,
            "encryption_enabled": False,
            "to_number": "1234567890",
            "agent_number": "9876543210",
            "outbound_type": "not_a_valid_enum_value",
        }
        with pytest.raises(ValidationError) as exc:
            Contract.CallCreate(**data)
        assert "Invalid outbound_type" in str(exc.value)

    @pytest.mark.parametrize(
        "bad_did",
        [
            "12345",  # Too short
            "1234567890123456",  # Too long (16)
            "abcdefghijk",  # Non-digits
            "91-888-956",  # Contains symbols
        ],
    )
    def test_invalid_dedicated_did_formats(self, bad_did):
        data = {
            "service_board_id": 80,
            "agent_number": "9876543210",
            "to_number": "1234567890",
            "encryption_enabled": False,
            "dedicated_did": bad_did,
        }
        with pytest.raises(ValidationError) as exc:
            Contract.CallCreate(**data)
        assert "dedicated_did must contain only digits" in str(exc.value)

    def test_none_values_for_optional_fields(self):
        """Ensure validators don't crash when optional fields are None."""
        data = {
            "service_board_id": 90,
            "agent_number": "9876543210",
            "to_number": "1234567890",
            "encryption_enabled": False,
            "outbound_type": None,
            "dedicated_did": None,
        }
        dto = Contract.CallCreate(**data)
        assert dto.outbound_type is None
        assert dto.dedicated_did is None


class TestCallResponseDTO:
    def test_call_response_success(self):
        dto = Contract.CallResponse(id="uuid-123", message="Success")
        assert dto.id == "uuid-123"
        assert dto.message == "Success"
