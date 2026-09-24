"""MongoDB document serialization helpers (single place for ObjectId handling)."""

from typing import Any

from bson import ObjectId


def stringify_object_ids(doc: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `doc` with top-level ObjectId values stringified.

    Replaces the ad-hoc `{k: str(v) if isinstance(v, ObjectId) ...}`
    comprehensions scattered across services. Never mutates the input.
    """
    return {k: (str(v) if isinstance(v, ObjectId) else v) for k, v in doc.items()}
