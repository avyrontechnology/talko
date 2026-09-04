from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.custom_field.constants import (
    TalkoCustomFieldDataType,
    TalkoCustomFieldEntityType,
)
from src.components.custom_field.dto import TalkoContract
from src.components.custom_field.services import TalkoCustomFieldService
from src.exceptions import TalkoBadRequestError


@pytest.mark.asyncio
class TestCustomFieldService:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        logger = MagicMock()
        datetime_util = MagicMock()
        datetime_util.get_current_time.return_value = 1735689600000
        validator = MagicMock()
        validator.validate_custom_field_create.return_value = "lead_source"
        validator.validate_slug_unique = AsyncMock()
        validator.validate_custom_field_exists = AsyncMock()

        service = TalkoCustomFieldService(
            repository=repo,
            logger=logger,
            datetime_util=datetime_util,
            validator=validator,
        )
        return service, repo, validator

    async def test_create_custom_field_success(self, setup):
        service, repo, validator = setup
        repo.insert_custom_field.return_value = "field123"

        field = TalkoContract.CustomFieldCreate(
            entity_type=TalkoCustomFieldEntityType.TalkoCDR,
            field_name="Lead Source",
            data_type=TalkoCustomFieldDataType.CHOICE,
            choice_options=["Web", "Referral"],
        )
        result = await service.create_custom_field(partner_id=1, field=field)

        assert result.id == "field123"
        validator.validate_slug_unique.assert_awaited_once_with(1, "TalkoCDR", "lead_source")
        inserted = repo.insert_custom_field.call_args[0][0]
        assert inserted["partner_id"] == 1
        assert inserted["entity_type"] == "TalkoCDR"
        assert inserted["field_slug"] == "lead_source"
        assert inserted["data_type"] == "choice"
        assert inserted["is_active"] is True

    async def test_get_custom_fields_maps_id_field(self, setup):
        service, repo, _ = setup
        field_id = ObjectId()
        repo.find_all.return_value = [
            {
                "_id": field_id,
                "partner_id": 1,
                "entity_type": "TalkoCDR",
                "field_name": "Lead Source",
                "field_slug": "lead_source",
                "data_type": "string",
                "is_required": False,
                "is_active": True,
            }
        ]

        results = await service.get_custom_fields(1, "TalkoCDR")
        assert len(results) == 1
        assert results[0].id == str(field_id)

    async def test_update_custom_field_success(self, setup):
        service, repo, validator = setup
        field_id = ObjectId()
        repo.update_by_id.return_value = {"_id": field_id}

        update = TalkoContract.CustomFieldUpdate(is_required=True)
        result = await service.update_custom_field(1, str(field_id), update)

        assert result.id == str(field_id)
        validator.validate_custom_field_exists.assert_awaited_once()
        update_dict = repo.update_by_id.call_args[0][1]
        assert update_dict["is_required"] is True

    async def test_update_custom_field_no_fields_raises(self, setup):
        service, _, _ = setup
        update = TalkoContract.CustomFieldUpdate()
        with pytest.raises(TalkoBadRequestError):
            await service.update_custom_field(1, str(ObjectId()), update)

    async def test_update_custom_field_invalid_id_raises(self, setup):
        service, _, _ = setup
        update = TalkoContract.CustomFieldUpdate(is_required=True)
        with pytest.raises(TalkoBadRequestError):
            await service.update_custom_field(1, "not-an-object-id", update)

    async def test_delete_custom_field_soft_deletes(self, setup):
        service, repo, validator = setup
        field_id = ObjectId()
        repo.update_by_id.return_value = {"_id": field_id}

        result = await service.delete_custom_field(1, str(field_id))

        assert result.id == str(field_id)
        update_dict = repo.update_by_id.call_args[0][1]
        assert update_dict["is_active"] is False
        validator.validate_custom_field_exists.assert_awaited_once()
