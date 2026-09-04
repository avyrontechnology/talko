from typing import Any, Dict, Optional, Union

from src.components.cdr.constants import EntityType


def normalize_entity_type(
    entity_type: Optional[Union[str, EntityType]],
) -> Optional[str]:
    if entity_type is None:
        return None
    if isinstance(entity_type, EntityType):
        return entity_type.value
    return str(entity_type)


def derive_entity_fields(
    entity_type: Optional[Union[str, EntityType]] = None,
    entity_id: Optional[Any] = None,
    entity_name: Optional[str] = None,
    lead_id: Optional[Any] = None,
    lead_name: Optional[str] = None,
    default_entity_type: Optional[EntityType] = None,
) -> Dict[str, Optional[Any]]:
    """
    Single source of truth for reconciling the new entity_type/entity_id/entity_name
    fields with the legacy lead_id/lead_name fields on a CDR.

    - Prefers explicit entity_* values when present.
    - Falls back to deriving entity_type="Lead"/entity_id=lead_id from legacy lead_id.
    - When default_entity_type is given and nothing else resolved an entity_type
      (e.g. a brand-new inbound caller with no lead in the system), entity_type is
      still set to that default so the call isn't left with entity_type=None.
      entity_id/entity_name stay None in that case since no actual record exists yet.
    """
    normalized_entity_type = normalize_entity_type(entity_type)
    resolved_entity_id = entity_id
    resolved_entity_name = entity_name

    if normalized_entity_type is None and lead_id is not None:
        normalized_entity_type = EntityType.LEAD.value
        resolved_entity_id = lead_id

    if (
        resolved_entity_name is None
        and normalized_entity_type == EntityType.LEAD.value
        and lead_name
    ):
        resolved_entity_name = lead_name

    if normalized_entity_type is None and default_entity_type is not None:
        normalized_entity_type = normalize_entity_type(default_entity_type)

    derived_lead_id = (
        resolved_entity_id
        if normalized_entity_type == EntityType.LEAD.value
        else lead_id
    )
    derived_lead_name = (
        resolved_entity_name
        if normalized_entity_type == EntityType.LEAD.value
        else lead_name
    )

    return {
        "entity_type": normalized_entity_type,
        "entity_id": resolved_entity_id,
        "entity_name": resolved_entity_name,
        "lead_id": derived_lead_id,
        "lead_name": derived_lead_name,
    }
