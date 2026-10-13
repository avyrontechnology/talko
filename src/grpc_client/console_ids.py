"""Console-ID boundary helpers (talko -> console-core gRPC).

Console-core carries all IDs as UUIDs exposed over proto3 `string` fields.
Accept int (legacy) / str / UUID on input, always send strings.
"""
from typing import Any, Iterable, List, Union
from uuid import UUID

ConsoleId = Union[int, str, UUID]


def console_id_str(value: ConsoleId) -> str:
    """Normalize one console ID to its proto string form."""
    return value if isinstance(value, str) else str(value)


def console_id_list(values: Any) -> List[str]:
    """Normalize a single ID or an iterable of IDs to a string list.

    Legacy int-only filters are widened: any int/str/UUID item passes
    through as its string form; None items are dropped.
    """
    if values is None:
        return []
    if isinstance(values, (int, str, UUID)):
        values = [values]
    out = []
    for v in values:
        if v is None:
            continue
        out.append(v if isinstance(v, str) else str(v))
    return out
