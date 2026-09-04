from enum import Enum, unique


@unique
class OutboundType(str, Enum):
    """
    Defines supported outbound calling types.
    """

    PHONE_NUMBER = "phone_number"  # Regular PSTN call
    SOFT_PHONE = "soft_phone"  # System / SIP based call

    @classmethod
    def choices(cls):
        """
        Returns choices suitable for Django model fields.
        """
        return [(item.value, item.name.replace("_", " ").title()) for item in cls]

    @classmethod
    def values(cls):
        """
        Returns all enum values.
        """
        return [item.value for item in cls]

    def __str__(self) -> str:
        return self.value


@unique
class InboundType(str, Enum):
    """
    Defines supported inbound calling types (how the inbound call is transferred/routed to the agent).
    """

    PHONE_NUMBER = "phone_number"  # Regular PSTN/mobile/landline transfer
    SOFT_PHONE = "soft_phone"  # Cloud phonic / SIP extension / agent username transfer

    @classmethod
    def choices(cls):
        """
        Returns choices suitable for Django model fields (e.g. choices=InboundType.choices()).
        """
        return [(item.value, item.name.replace("_", " ").title()) for item in cls]

    @classmethod
    def values(cls):
        """
        Returns all enum values as a list.
        """
        return [item.value for item in cls]

    def __str__(self) -> str:
        return self.value
