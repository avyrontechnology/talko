from enum import Enum


class PSTNProvider(str, Enum):
    TATA_TELE = "tata_tele"
    EXOTEL = "exotel"


class CallDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
