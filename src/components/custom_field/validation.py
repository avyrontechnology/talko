import re
from typing import Any, Dict, List, Optional

from bson import ObjectId

from src.components.custom_field.constants import CustomFieldDataType
from src.components.custom_field.dto import Contract
from src.components.custom_field.message import (
    CHOICE_OPTIONS_REQUIRED_FOR_CHOICE_TYPE,
    CUSTOM_FIELD_NOT_FOUND,
    CUSTOM_FIELD_SLUG_ALREADY_EXISTS,
)
from src.components.custom_field.repository import CustomFieldRepository
from src.exceptions import BadRequestError, DuplicateResourceError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.common_validation import validate_required_fields

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


class CustomFieldValidator:
    """
    Validator for custom field definitions and for values being set
    against a partner's active custom fields.
    """

    def __init__(
        self,
        repository: CustomFieldRepository,
        logger: HollerServiceLogger,
    ):
        self.__repository = repository
        self.__logger = logger

    @staticmethod
    def slugify(field_name: str) -> str:
        slug = _SLUG_INVALID_CHARS.sub("_", field_name.strip().lower()).strip("_")
        return slug

    def validate_custom_field_create(self, field: Contract.CustomFieldCreate) -> str:
        """
        Validate required fields and derive/return the field_slug to use.
        """
        required_fields = ["entity_type", "field_name", "data_type"]
        validate_required_fields(field.model_dump(), required_fields, self.__logger)

        if field.data_type == CustomFieldDataType.CHOICE and not field.choice_options:
            self.__logger.error(CHOICE_OPTIONS_REQUIRED_FOR_CHOICE_TYPE)
            raise BadRequestError(CHOICE_OPTIONS_REQUIRED_FOR_CHOICE_TYPE)

        field_slug: str = field.field_slug or self.slugify(field.field_name)
        if not field_slug:
            self.__logger.error("Unable to derive a valid field_slug.")
            raise BadRequestError("Unable to derive a valid field_slug.")

        return field_slug

    async def validate_slug_unique(
        self, partner_id: int, entity_type: str, field_slug: str
    ) -> None:
        existing: Optional[Dict[str, Any]] = await self.__repository.find_by_slug(
            partner_id, entity_type, field_slug
        )
        if existing:
            self.__logger.error(CUSTOM_FIELD_SLUG_ALREADY_EXISTS.format(field_slug))
            raise DuplicateResourceError(
                CUSTOM_FIELD_SLUG_ALREADY_EXISTS.format(field_slug)
            )

    async def validate_custom_field_exists(
        self, field_id: ObjectId, partner_id: int
    ) -> Dict[str, Any]:
        field: Optional[Dict[str, Any]] = await self.__repository.find_by_id(field_id)
        if not field or field.get("partner_id") != partner_id:
            self.__logger.error(
                "Custom field {} not found for partner {}.".format(field_id, partner_id)
            )
            raise ResourceNotFound(CUSTOM_FIELD_NOT_FOUND)
        return field

    async def validate_and_normalize_values(
        self, partner_id: int, entity_type: str, values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate submitted custom field values against the partner's active
        field definitions for the given entity_type, coercing each value to
        its declared data_type. Raises BadRequestError on any mismatch.
        """
        if not values:
            raise BadRequestError("No custom field values provided.")

        definitions: List[Dict[str, Any]] = await self.__repository.find_all(
            partner_id, entity_type, include_inactive=False
        )
        definitions_by_slug: Dict[str, Dict[str, Any]] = {
            d["field_slug"]: d for d in definitions
        }

        normalized: Dict[str, Any] = {}
        for slug, value in values.items():
            definition = definitions_by_slug.get(slug)
            if not definition:
                self.__logger.error(
                    "Unknown or inactive custom field slug '{}' for partner {}, entity_type {}.".format(
                        slug, partner_id, entity_type
                    )
                )
                raise BadRequestError(
                    "Unknown or inactive custom field: '{}'.".format(slug)
                )
            normalized[slug] = self.__coerce_value(definition, value)

        return normalized

    def __coerce_value(self, definition: Dict[str, Any], value: Any) -> Any:
        slug: str = definition["field_slug"]
        data_type: str = definition["data_type"]

        if value is None:
            return None

        if data_type == CustomFieldDataType.STRING.value:
            if not isinstance(value, str):
                raise BadRequestError(
                    "Custom field '{}' expects a string value.".format(slug)
                )
            return value

        if data_type == CustomFieldDataType.NUMBER.value:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise BadRequestError(
                    "Custom field '{}' expects a numeric value.".format(slug)
                )
            return value

        if data_type == CustomFieldDataType.BOOLEAN.value:
            if not isinstance(value, bool):
                raise BadRequestError(
                    "Custom field '{}' expects a boolean value.".format(slug)
                )
            return value

        if data_type == CustomFieldDataType.DATE.value:
            if isinstance(value, bool) or not isinstance(value, int):
                raise BadRequestError(
                    "Custom field '{}' expects an epoch-millisecond integer value.".format(
                        slug
                    )
                )
            return value

        if data_type == CustomFieldDataType.CHOICE.value:
            choice_options: List[str] = definition.get("choice_options") or []
            if value not in choice_options:
                raise BadRequestError(
                    "Custom field '{}' expects one of {}.".format(slug, choice_options)
                )
            return value

        raise BadRequestError(
            "Unsupported data_type for custom field '{}'.".format(slug)
        )
