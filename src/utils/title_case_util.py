from typing import Any, List


class TalkoTitleCaseUtil:
    """Utility class for converting string values to title case."""

    @staticmethod
    def to_title_case(snake_str: str) -> str:
        """Convert a string to title case."""
        if not isinstance(snake_str, str):
            return snake_str
        components = snake_str.replace("_", " ").split()
        return " ".join(x.capitalize() for x in components)

    @staticmethod
    def convert_values_to_title_case(obj: Any, exclude_keys: List[str] = None) -> Any:
        """
        Recursively convert string values in a dictionary or object to title case.
        Keys remain unchanged unless excluded.
        """
        if exclude_keys is None:
            exclude_keys = []

        if isinstance(obj, dict):
            return {
                k: (obj[k] if k in exclude_keys
                    else TalkoTitleCaseUtil.convert_values_to_title_case(v, exclude_keys))
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [TalkoTitleCaseUtil.convert_values_to_title_case(item, exclude_keys) for item in obj]
        elif hasattr(obj, "__dict__"):
            return TalkoTitleCaseUtil.convert_values_to_title_case(obj.__dict__, exclude_keys)
        elif isinstance(obj, str):
            return TalkoTitleCaseUtil.to_title_case(obj)
        return obj
