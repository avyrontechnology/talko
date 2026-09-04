from enum import Enum


class TalkoPSTNProvider(str, Enum):
    TATA_TELE = "tata_tele"
    EXOTEL = "exotel"


class TalkoCallDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
