from enum import Enum

import pytest

from src.components.call_management.enums import TalkoInboundType, TalkoOutboundType


class TestOutboundTypeEnum:
    def test_enum_is_instance_of_enum(self):
        assert issubclass(TalkoOutboundType, Enum)

    def test_enum_values(self):
        assert TalkoOutboundType.PHONE_NUMBER.value == "phone_number"
        assert TalkoOutboundType.SOFT_PHONE.value == "soft_phone"

    def test_enum_uniqueness(self):
        values = [item.value for item in TalkoOutboundType]
        assert len(values) == len(set(values))

    def test_values_classmethod(self):
        assert TalkoOutboundType.values() == ["phone_number", "soft_phone"]

    def test_choices_classmethod(self):
        assert TalkoOutboundType.choices() == [
            ("phone_number", "Phone Number"),
            ("soft_phone", "Soft Phone"),
        ]

    def test_str_representation(self):
        assert str(TalkoOutboundType.PHONE_NUMBER) == "phone_number"
        assert str(TalkoOutboundType.SOFT_PHONE) == "soft_phone"

    def test_enum_lookup_by_value(self):
        enum_value = TalkoOutboundType("phone_number")
        assert enum_value is TalkoOutboundType.PHONE_NUMBER

    def test_invalid_enum_value_raises_error(self):
        with pytest.raises(ValueError):
            TalkoOutboundType("invalid_type")


class TestInboundTypeEnum:
    def test_enum_is_instance_of_enum(self):
        assert issubclass(TalkoInboundType, Enum)

    def test_enum_values(self):
        assert TalkoInboundType.PHONE_NUMBER.value == "phone_number"
        assert TalkoInboundType.SOFT_PHONE.value == "soft_phone"

    def test_enum_uniqueness(self):
        values = [item.value for item in TalkoInboundType]
        assert len(values) == len(set(values))

    def test_values_classmethod(self):
        assert TalkoInboundType.values() == ["phone_number", "soft_phone"]

    def test_choices_classmethod(self):
        assert TalkoInboundType.choices() == [
            ("phone_number", "Phone Number"),
            ("soft_phone", "Soft Phone"),
        ]

    def test_str_representation(self):
        assert str(TalkoInboundType.PHONE_NUMBER) == "phone_number"
        assert str(TalkoInboundType.SOFT_PHONE) == "soft_phone"

    def test_enum_lookup_by_value(self):
        enum_value = TalkoInboundType("soft_phone")
        assert enum_value is TalkoInboundType.SOFT_PHONE

    def test_invalid_enum_value_raises_error(self):
        with pytest.raises(ValueError):
            TalkoInboundType("invalid_type")
