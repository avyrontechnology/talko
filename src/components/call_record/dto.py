from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class TalkoContract:

    class CreateCallRecordReq(BaseModel):
        caller: str
        receiver: str
        duration: int
        timestamp: datetime

    class CreateCallRecordResp(BaseModel):
        record_id: str
        message: str

    class UpdateCallRecordReq(BaseModel):
        caller: Optional[str]
        receiver: Optional[str]
        duration: Optional[int]
        timestamp: Optional[datetime]

    class UpdateCallRecordResp(BaseModel):
        record_id: str
        message: str
