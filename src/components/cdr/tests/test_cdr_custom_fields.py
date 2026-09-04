from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.cdr.dto import TalkoContract
from src.components.cdr.services import TalkoCDRService
from src.exceptions import TalkoResourceNotFound


@pytest.mark.asyncio
class TestCDRServiceSetCustomFieldValues:
    @pytest.fixture
    def setup(self):
        repository = AsyncMock()
        logger = MagicMock()
        datetime_util = MagicMock()
        datetime_util.get_current_time.return_value = 1735689600000
        custom_field_validator = AsyncMock()

        service = TalkoCDRService(
            repository=repository,
            logger=logger,
            datetime_util=datetime_util,
            analytics_processor=MagicMock(),
            date_range_helper=MagicMock(),
            did_repository=MagicMock(),
            custom_field_validator=custom_field_validator,
        )
        return service, repository, custom_field_validator

    async def test_set_custom_field_values_success(self, setup):
        service, repository, custom_field_validator = setup
        repository.find_cdr_by_call_id.return_value = {
            "_id": "abc",
            "call_id": "call-1",
            "partner_id": 1,
            "custom_fields": {},
        }
        custom_field_validator.validate_and_normalize_values.return_value = {
            "lead_source": "Web"
        }
        repository.set_custom_field_values.return_value = {
            "_id": "abc",
            "call_id": "call-1",
            "custom_fields": {"lead_source": "Web"},
        }

        result = await service.set_custom_field_values(
            user_id=1,
            partner_id=1,
            call_id="call-1",
            values={"lead_source": "Web"},
        )

        assert isinstance(result, TalkoContract.SetCDRCustomFieldsResponse)
        assert result.call_id == "call-1"
        assert result.custom_fields == {"lead_source": "Web"}

        custom_field_validator.validate_and_normalize_values.assert_awaited_once_with(
            1, "TalkoCDR", {"lead_source": "Web"}
        )
        repository.set_custom_field_values.assert_awaited_once_with(
            "call-1", {"lead_source": "Web"}, 1735689600000
        )

    async def test_set_custom_field_values_cdr_not_found_raises(self, setup):
        service, repository, _ = setup
        repository.find_cdr_by_call_id.return_value = None

        with pytest.raises(TalkoResourceNotFound):
            await service.set_custom_field_values(
                user_id=1, partner_id=1, call_id="missing", values={"x": 1}
            )

    async def test_set_custom_field_values_cross_tenant_raises_not_found(self, setup):
        service, repository, _ = setup
        repository.find_cdr_by_call_id.return_value = {
            "_id": "abc",
            "call_id": "call-1",
            "partner_id": 999,
        }

        with pytest.raises(TalkoResourceNotFound):
            await service.set_custom_field_values(
                user_id=1, partner_id=1, call_id="call-1", values={"x": 1}
            )

    async def test_set_custom_field_values_propagates_validator_errors(self, setup):
        service, repository, custom_field_validator = setup
        repository.find_cdr_by_call_id.return_value = {
            "_id": "abc",
            "call_id": "call-1",
            "partner_id": 1,
        }
        custom_field_validator.validate_and_normalize_values.side_effect = ValueError(
            "bad value"
        )

        with pytest.raises(ValueError, match="bad value"):
            await service.set_custom_field_values(
                user_id=1, partner_id=1, call_id="call-1", values={"x": 1}
            )
        repository.set_custom_field_values.assert_not_awaited()

    async def test_set_custom_field_values_handles_missing_updated_doc(self, setup):
        service, repository, custom_field_validator = setup
        repository.find_cdr_by_call_id.return_value = {
            "_id": "abc",
            "call_id": "call-1",
            "partner_id": 1,
        }
        custom_field_validator.validate_and_normalize_values.return_value = {"x": 1}
        repository.set_custom_field_values.return_value = None

        result = await service.set_custom_field_values(
            user_id=1, partner_id=1, call_id="call-1", values={"x": 1}
        )
        assert result.custom_fields == {}
