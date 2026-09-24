from datetime import datetime

from pydantic import BaseModel


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
        caller: str | None
        receiver: str | None
        duration: int | None
        timestamp: datetime | None

    class UpdateCallRecordResp(BaseModel):
        record_id: str
        message: str
