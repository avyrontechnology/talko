from typing import Optional

from pydantic import BaseModel, model_validator

from src.utils.datetime_util import DateTimeUtil


class TimestampedModel(BaseModel):
    created_at: Optional[int] = None  # Created timestamp
    updated_at: Optional[int] = None  # Updated timestamp

    @model_validator(mode="before")
    @classmethod
    def set_timestamps(cls, data: dict) -> dict:
        datetime_util = DateTimeUtil()
        current_timestamp = datetime_util.get_current_time()

        # Set created_at only if it's not provided (for new instances)
        if data.get("created_at") is None:
            data["created_at"] = current_timestamp
        # Set updated_at only if it's not provided (for new instances)
        if data.get("updated_at") is None:
            data["updated_at"] = current_timestamp
        return data
