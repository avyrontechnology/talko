from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from pydantic.functional_validators import BeforeValidator
from typing_extensions import Annotated

PyObjectId = Annotated[str, BeforeValidator(str)]


class CallRecordModel(BaseModel):
    call_record_id: Optional[PyObjectId] = Field(alias="_id", default=None)
    caller: str
    receiver: str
    duration: int
    timestamp: datetime
    partner_id: int
    created_by: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class CollectionName:
        CALL_RECORD = "call_record"
