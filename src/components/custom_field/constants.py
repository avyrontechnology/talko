from enum import Enum


class CustomFieldDataType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    CHOICE = "choice"


class CustomFieldEntityType(str, Enum):
    CDR = "CDR"


SET = "$set"
