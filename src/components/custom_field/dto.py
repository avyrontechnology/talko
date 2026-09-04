from typing import List, Optional

from pydantic import BaseModel

from src.components.custom_field.constants import (
    TalkoCustomFieldDataType,
    TalkoCustomFieldEntityType,
)


class TalkoContract:
    class CustomFieldCreate(BaseModel):
        entity_type: TalkoCustomFieldEntityType
        field_name: str
        field_slug: Optional[str] = None
        data_type: TalkoCustomFieldDataType
        choice_options: Optional[List[str]] = None
        is_required: bool = False
        sequence: Optional[int] = None

    class CustomFieldUpdate(BaseModel):
        field_name: Optional[str] = None
        choice_options: Optional[List[str]] = None
        is_required: Optional[bool] = None
        sequence: Optional[int] = None
        is_active: Optional[bool] = None

    class CustomFieldResponse(BaseModel):
        id: str
        partner_id: int
        entity_type: TalkoCustomFieldEntityType
        field_name: str
        field_slug: str
        data_type: TalkoCustomFieldDataType
        choice_options: Optional[List[str]] = None
        is_required: bool = False
        sequence: Optional[int] = None
        is_active: bool = True
        created_at: Optional[int] = None
        updated_at: Optional[int] = None

    class CustomFieldCreationUpdationResponse(BaseModel):
        id: str
        message: str
