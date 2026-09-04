import re
from typing import Any


def normalize_auto_format(value: str) -> str:
    """Convert snake_case or lowercase strings into Title Case."""
    return re.sub(r"_+", " ", value).title()


def safe_to_int(value: Any) -> int:
    """Safely convert a value to an integer, logging invalid values."""
    if value is None or value == "":
        return 0
    try:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
        raise ValueError(f"Invalid value for conversion: {value}")
    except (ValueError, TypeError) as _:
        return 0
