import pytest
from bson import ObjectId
from pydantic import ValidationError

from src.components.partner_config.models import TalkoPartnerConfigModel
from src.utils.enums import TalkoRingType  # Assuming TalkoRingType is an enum defined elsewhere


class TestPartnerConfigModel:

    def test_mutual_exclusivity_raises_value_error(self):
        """Should raise ValueError if both round_robin and service_board are True"""
        with pytest.raises(ValidationError) as exc_info:
            TalkoPartnerConfigModel(
                partner_id=1,
                is_active=True,
                vendor_id=ObjectId(),
                enable_round_robin=True,
                enable_service_board=True,
            )

        assert "Round-robin and service board cannot be enabled simultaneously" in str(
            exc_info.value
        )

    def test_mutual_exclusivity_passes_for_round_robin_only(self):
        """Should pass if only round_robin is True"""
        model = TalkoPartnerConfigModel(
            partner_id=1,
            is_active=True,
            vendor_id=ObjectId(),
            enable_round_robin=True,
            enable_service_board=False,
            round_robin_did_count=10,
        )
        assert model.enable_round_robin is True
        assert model.enable_service_board is False

    def test_mutual_exclusivity_passes_for_service_board_only(self):
        """Should pass if only service_board is True"""
        model = TalkoPartnerConfigModel(
            partner_id=1,
            is_active=True,
            vendor_id=ObjectId(),
            enable_round_robin=False,
            enable_service_board=True,
            service_board_ids=[456],
        )
        assert model.enable_round_robin is False
        assert model.enable_service_board is True

    def test_mutual_exclusivity_passes_if_both_false(self):
        """Should pass if both round_robin and service_board are False"""
        model = TalkoPartnerConfigModel(
            partner_id=1,
            is_active=True,
            vendor_id=ObjectId(),
            enable_round_robin=False,
            enable_service_board=False,
        )
        assert model.enable_round_robin is False
        assert model.enable_service_board is False

    def test_service_board_requires_ids(self):
        """Should raise ValueError if service_board is enabled without service_board_ids"""
        with pytest.raises(ValidationError) as exc_info:
            TalkoPartnerConfigModel(
                partner_id=1,
                is_active=True,
                vendor_id=ObjectId(),
                enable_round_robin=False,
                enable_service_board=True,
                service_board_ids=None,
            )
        assert "Service board IDs are required when service board is enabled" in str(
            exc_info.value
        )

    def test_round_robin_requires_did_count(self):
        """Should raise ValueError if round_robin is enabled without round_robin_did_count"""
        with pytest.raises(ValidationError) as exc_info:
            TalkoPartnerConfigModel(
                partner_id=1,
                is_active=True,
                vendor_id=ObjectId(),
                enable_round_robin=True,
                enable_service_board=False,
                round_robin_did_count=None,
            )
        assert (
            "round_robin_did_count is required when enable_round_robin is true"
            in str(exc_info.value)
        )

    def test_round_robin_initializes_did_indices(self):
        """Should initialize did_indices['round_robin'] if missing when round_robin is enabled"""
        model = TalkoPartnerConfigModel(
            partner_id=1,
            is_active=True,
            vendor_id=ObjectId(),
            enable_round_robin=True,
            enable_service_board=False,
            round_robin_did_count=10,
            did_indices={},  # Override default to exclude "round_robin"
        )
        assert model.did_indices["round_robin"] == 0
        assert model.enable_round_robin is True

    def test_ring_type_required_for_multiple_attendance(self):
        """Should raise ValueError if ring_type is None with multiple default attendance numbers"""
        with pytest.raises(ValidationError) as exc_info:
            TalkoPartnerConfigModel(
                partner_id=1,
                is_active=True,
                vendor_id=ObjectId(),
                enable_round_robin=True,
                enable_service_board=False,
                round_robin_did_count=10,
                round_robin_default_attendance={
                    "default": [{"number": "123"}, {"number": "456"}]
                },  # Multiple entries
                ring_type=None,
            )
        assert "ring_type is required for multiple default attendance numbers" in str(
            exc_info.value
        )
