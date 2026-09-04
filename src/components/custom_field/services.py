from typing import Any, Dict, List

from bson import ObjectId

from src.components.custom_field.dto import Contract
from src.components.custom_field.message import (
    CUSTOM_FIELD_CREATED_SUCCESSFULLY,
    CUSTOM_FIELD_DELETED_SUCCESSFULLY,
    CUSTOM_FIELD_UPDATED_SUCCESSFULLY,
    NO_FIELDS_PROVIDED_FOR_UPDATE,
)
from src.components.custom_field.repository import CustomFieldRepository
from src.components.custom_field.validation import CustomFieldValidator
from src.exceptions import BadRequestError
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.datetime_util import DateTimeUtil


class CustomFieldService:
    """
    Service class responsible for managing custom field definitions
    (create, list, update, soft-delete).
    """

    def __init__(
        self,
        repository: CustomFieldRepository,
        logger: HollerServiceLogger,
        datetime_util: DateTimeUtil,
        validator: CustomFieldValidator,
    ):
        self.__repository = repository
        self.__logger = logger
        self.__datetime_util = datetime_util
        self.__validator = validator

    async def create_custom_field(
        self, partner_id: int, field: Contract.CustomFieldCreate
    ) -> Contract.CustomFieldCreationUpdationResponse:
        self.__logger.info(
            "Creating custom field for partner {}: {}".format(partner_id, field)
        )

        field_slug: str = self.__validator.validate_custom_field_create(field)
        await self.__validator.validate_slug_unique(
            partner_id, field.entity_type.value, field_slug
        )

        current_timestamp: Any = self.__datetime_util.get_current_time()
        field_dict: Dict[str, Any] = {
            "partner_id": partner_id,
            "entity_type": field.entity_type.value,
            "field_name": field.field_name,
            "field_slug": field_slug,
            "data_type": field.data_type.value,
            "choice_options": field.choice_options,
            "is_required": field.is_required,
            "sequence": field.sequence,
            "is_active": True,
            "created_at": current_timestamp,
            "updated_at": current_timestamp,
        }

        field_id: str = await self.__repository.insert_custom_field(field_dict)
        self.__logger.info("Custom field created with ID: {}".format(field_id))

        return Contract.CustomFieldCreationUpdationResponse(
            id=field_id, message=CUSTOM_FIELD_CREATED_SUCCESSFULLY
        )

    async def get_custom_fields(
        self, partner_id: int, entity_type: str
    ) -> List[Contract.CustomFieldResponse]:
        self.__logger.info(
            "Listing custom fields for partner {}, entity_type {}".format(
                partner_id, entity_type
            )
        )
        fields: List[Dict[str, Any]] = await self.__repository.find_all(
            partner_id, entity_type
        )

        responses: List[Contract.CustomFieldResponse] = []
        for field in fields:
            field["id"] = str(field["_id"])
            del field["_id"]
            responses.append(Contract.CustomFieldResponse(**field))
        return responses

    async def update_custom_field(
        self,
        partner_id: int,
        field_id: str,
        update: Contract.CustomFieldUpdate,
    ) -> Contract.CustomFieldCreationUpdationResponse:
        self.__logger.info(
            "Updating custom field {} for partner {}".format(field_id, partner_id)
        )
        try:
            object_id: ObjectId = ObjectId(field_id)
        except Exception:
            raise BadRequestError("Invalid custom field id.")

        await self.__validator.validate_custom_field_exists(object_id, partner_id)

        update_dict: Dict[str, Any] = {
            k: v for k, v in update.model_dump().items() if v is not None
        }
        if not update_dict:
            self.__logger.error(NO_FIELDS_PROVIDED_FOR_UPDATE)
            raise BadRequestError(NO_FIELDS_PROVIDED_FOR_UPDATE)

        update_dict["updated_at"] = self.__datetime_util.get_current_time()

        updated: Dict[str, Any] = await self.__repository.update_by_id(
            object_id, update_dict
        )
        return Contract.CustomFieldCreationUpdationResponse(
            id=str(updated["_id"]), message=CUSTOM_FIELD_UPDATED_SUCCESSFULLY
        )

    async def delete_custom_field(
        self, partner_id: int, field_id: str
    ) -> Contract.CustomFieldCreationUpdationResponse:
        self.__logger.info(
            "Soft-deleting custom field {} for partner {}".format(field_id, partner_id)
        )
        try:
            object_id: ObjectId = ObjectId(field_id)
        except Exception:
            raise BadRequestError("Invalid custom field id.")

        await self.__validator.validate_custom_field_exists(object_id, partner_id)

        update_dict: Dict[str, Any] = {
            "is_active": False,
            "updated_at": self.__datetime_util.get_current_time(),
        }
        updated: Dict[str, Any] = await self.__repository.update_by_id(
            object_id, update_dict
        )
        return Contract.CustomFieldCreationUpdationResponse(
            id=str(updated["_id"]), message=CUSTOM_FIELD_DELETED_SUCCESSFULLY
        )
