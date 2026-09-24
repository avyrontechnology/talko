from pydantic import BaseModel

from src.components.custom_field.constants import (
    TalkoCustomFieldDataType,
    TalkoCustomFieldEntityType,
)


class TalkoContract:
    class CustomFieldCreate(BaseModel):
        entity_type: TalkoCustomFieldEntityType
        field_name: str
        field_slug: str | None = None
        data_type: TalkoCustomFieldDataType
        choice_options: list[str] | None = None
        is_required: bool = False
        sequence: int | None = None

    class CustomFieldUpdate(BaseModel):
        field_name: str | None = None
        choice_options: list[str] | None = None
        is_required: bool | None = None
        sequence: int | None = None
        is_active: bool | None = None

    class CustomFieldResponse(BaseModel):
        id: str
        partner_id: int
        entity_type: TalkoCustomFieldEntityType
        field_name: str
        field_slug: str
        data_type: TalkoCustomFieldDataType
        choice_options: list[str] | None = None
        is_required: bool = False
        sequence: int | None = None
        is_active: bool = True
        created_at: int | None = None
        updated_at: int | None = None

    class CustomFieldCreationUpdationResponse(BaseModel):
        id: str
        message: str
