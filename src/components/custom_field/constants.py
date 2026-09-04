from enum import Enum


class TalkoCustomFieldDataType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    CHOICE = "choice"


class TalkoCustomFieldEntityType(str, Enum):
    TalkoCDR = "TalkoCDR"


SET = "$set"
