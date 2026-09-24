from typing import Any

from src.components.cdr.constants import TalkoEntityType


def normalize_entity_type(
    entity_type: str | TalkoEntityType | None,
) -> str | None:
    if entity_type is None:
        return None
    if isinstance(entity_type, TalkoEntityType):
        return entity_type.value
    return str(entity_type)


def derive_entity_fields(
    entity_type: str | TalkoEntityType | None = None,
    entity_id: Any | None = None,
    entity_name: str | None = None,
    lead_id: Any | None = None,
    lead_name: str | None = None,
    default_entity_type: TalkoEntityType | None = None,
) -> dict[str, Any | None]:
    """
    Single source of truth for reconciling the new entity_type/entity_id/entity_name
    fields with the legacy lead_id/lead_name fields on a TalkoCDR.

    - Prefers explicit entity_* values when present.
    - Falls back to deriving entity_type="Lead"/entity_id=lead_id from legacy lead_id.
    - When default_entity_type is given and nothing else resolved an entity_type
      (e.g. a brand-new inbound caller with no lead in the system), entity_type is
      still set to that default so the call isn't left with entity_type=None.
      entity_id/entity_name stay None in that case since no actual record exists yet.
    - Falsy lead_id (0/""/None) means "no lead" — never derive a phantom
      Lead entity with id 0. Falsy lead_name normalizes to "".
    """
    # Normalize absent-ish inputs before any derivation.
    if not lead_id:
        lead_id = None
    if entity_id is not None and not entity_id:
        entity_id = None
    if not lead_name:
        lead_name = ""
    normalized_entity_type = normalize_entity_type(entity_type)
    resolved_entity_id = entity_id
    resolved_entity_name = entity_name

    if normalized_entity_type is None and lead_id is not None:
        normalized_entity_type = TalkoEntityType.LEAD.value
        resolved_entity_id = lead_id

    if resolved_entity_name is None and normalized_entity_type == TalkoEntityType.LEAD.value and lead_name:
        resolved_entity_name = lead_name

    if normalized_entity_type is None and default_entity_type is not None:
        normalized_entity_type = normalize_entity_type(default_entity_type)

    derived_lead_id = resolved_entity_id if normalized_entity_type == TalkoEntityType.LEAD.value else lead_id
    derived_lead_name = (
        (resolved_entity_name or lead_name) if normalized_entity_type == TalkoEntityType.LEAD.value else lead_name
    )

    return {
        "entity_type": normalized_entity_type,
        "entity_id": resolved_entity_id,
        "entity_name": resolved_entity_name,
        "lead_id": derived_lead_id,
        "lead_name": derived_lead_name,
    }
