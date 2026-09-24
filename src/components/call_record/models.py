from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field
from pydantic.functional_validators import BeforeValidator

PyObjectId = Annotated[str, BeforeValidator(str)]


class TalkoCallRecordModel(BaseModel):
    call_record_id: PyObjectId | None = Field(alias="_id", default=None)
    caller: str
    receiver: str
    duration: int
    timestamp: datetime
    partner_id: int
    created_by: int
    created_at: datetime
    updated_at: datetime | None = None

    class CollectionName:
        CALL_RECORD = "call_record"
