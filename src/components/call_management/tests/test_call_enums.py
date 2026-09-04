from enum import Enum

import pytest

from src.components.call_management.enums import InboundType, OutboundType


class TestOutboundTypeEnum:
    def test_enum_is_instance_of_enum(self):
        assert issubclass(OutboundType, Enum)

    def test_enum_values(self):
        assert OutboundType.PHONE_NUMBER.value == "phone_number"
        assert OutboundType.SOFT_PHONE.value == "soft_phone"

    def test_enum_uniqueness(self):
        values = [item.value for item in OutboundType]
        assert len(values) == len(set(values))

    def test_values_classmethod(self):
        assert OutboundType.values() == ["phone_number", "soft_phone"]

    def test_choices_classmethod(self):
        assert OutboundType.choices() == [
            ("phone_number", "Phone Number"),
            ("soft_phone", "Soft Phone"),
        ]

    def test_str_representation(self):
        assert str(OutboundType.PHONE_NUMBER) == "phone_number"
        assert str(OutboundType.SOFT_PHONE) == "soft_phone"

    def test_enum_lookup_by_value(self):
        enum_value = OutboundType("phone_number")
        assert enum_value is OutboundType.PHONE_NUMBER

    def test_invalid_enum_value_raises_error(self):
        with pytest.raises(ValueError):
            OutboundType("invalid_type")


class TestInboundTypeEnum:
    def test_enum_is_instance_of_enum(self):
        assert issubclass(InboundType, Enum)

    def test_enum_values(self):
        assert InboundType.PHONE_NUMBER.value == "phone_number"
        assert InboundType.SOFT_PHONE.value == "soft_phone"

    def test_enum_uniqueness(self):
        values = [item.value for item in InboundType]
        assert len(values) == len(set(values))

    def test_values_classmethod(self):
        assert InboundType.values() == ["phone_number", "soft_phone"]

    def test_choices_classmethod(self):
        assert InboundType.choices() == [
            ("phone_number", "Phone Number"),
            ("soft_phone", "Soft Phone"),
        ]

    def test_str_representation(self):
        assert str(InboundType.PHONE_NUMBER) == "phone_number"
        assert str(InboundType.SOFT_PHONE) == "soft_phone"

    def test_enum_lookup_by_value(self):
        enum_value = InboundType("soft_phone")
        assert enum_value is InboundType.SOFT_PHONE

    def test_invalid_enum_value_raises_error(self):
        with pytest.raises(ValueError):
            InboundType("invalid_type")
