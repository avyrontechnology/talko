"""Shared slug helper (human-readable, URL-safe identifiers)."""

import re
import uuid

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def slugify_name(name: str, fallback: str = "item") -> str:
    """Slugify a display name; falls back to a short uuid when empty."""
    slug = _SLUG_INVALID_CHARS.sub("-", (name or "").strip().lower()).strip("-")
    return slug or f"{fallback}-{uuid.uuid4().hex[:8]}"


def unique_slug(base: str, exists: set[str]) -> str:
    """Append -2, -3, ... until the slug is unique within `exists`."""
    candidate, n = base, 2
    while candidate in exists:
        candidate = f"{base}-{n}"
        n += 1
    return candidate
