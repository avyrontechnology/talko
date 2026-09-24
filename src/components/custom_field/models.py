from src.components.custom_field.constants import (
    TalkoCustomFieldDataType,
    TalkoCustomFieldEntityType,
)
from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoCustomFieldDefinition(TalkoTimestampedModel):
    partner_id: int
    entity_type: TalkoCustomFieldEntityType
    field_name: str
    field_slug: str
    data_type: TalkoCustomFieldDataType
    choice_options: list[str] | None = None
    is_required: bool = False
    sequence: int | None = None
    is_active: bool = True

    class CollectionName:
        CUSTOM_FIELD_DEFINITIONS = "custom_field_definitions"
