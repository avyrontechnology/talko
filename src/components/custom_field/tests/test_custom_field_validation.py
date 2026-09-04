from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.custom_field.constants import (
    TalkoCustomFieldDataType,
    TalkoCustomFieldEntityType,
)
from src.components.custom_field.dto import TalkoContract
from src.components.custom_field.validation import TalkoCustomFieldValidator
from src.exceptions import TalkoBadRequestError, TalkoDuplicateResourceError, TalkoResourceNotFound


class TestSlugify:
    def test_slugify_lowercases_and_replaces_non_alnum(self):
        assert TalkoCustomFieldValidator.slugify("Lead Source!!") == "lead_source"

    def test_slugify_strips_leading_trailing_underscores(self):
        assert TalkoCustomFieldValidator.slugify("  -VIP-  ") == "vip"


class TestCustomFieldValidatorCreate:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        logger = MagicMock()
        validator = TalkoCustomFieldValidator(repository=repo, logger=logger)
        return validator, repo, logger

    def test_validate_custom_field_create_derives_slug_from_name(self, setup):
        validator, _, _ = setup
        field = TalkoContract.CustomFieldCreate(
            entity_type=TalkoCustomFieldEntityType.TalkoCDR,
            field_name="Lead Source",
            data_type=TalkoCustomFieldDataType.STRING,
        )
        assert validator.validate_custom_field_create(field) == "lead_source"

    def test_validate_custom_field_create_respects_explicit_slug(self, setup):
        validator, _, _ = setup
        field = TalkoContract.CustomFieldCreate(
            entity_type=TalkoCustomFieldEntityType.TalkoCDR,
            field_name="Lead Source",
            field_slug="custom_slug",
            data_type=TalkoCustomFieldDataType.STRING,
        )
        assert validator.validate_custom_field_create(field) == "custom_slug"

    def test_choice_type_without_choice_options_raises(self, setup):
        validator, _, _ = setup
        field = TalkoContract.CustomFieldCreate(
            entity_type=TalkoCustomFieldEntityType.TalkoCDR,
            field_name="Bad Choice",
            data_type=TalkoCustomFieldDataType.CHOICE,
        )
        with pytest.raises(TalkoBadRequestError):
            validator.validate_custom_field_create(field)


@pytest.mark.asyncio
class TestCustomFieldValidator:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        logger = MagicMock()
        validator = TalkoCustomFieldValidator(repository=repo, logger=logger)
        return validator, repo, logger

    async def test_validate_slug_unique_raises_when_existing(self, setup):
        validator, repo, _ = setup
        repo.find_by_slug.return_value = {"field_slug": "lead_source"}
        with pytest.raises(TalkoDuplicateResourceError):
            await validator.validate_slug_unique(1, "TalkoCDR", "lead_source")

    async def test_validate_slug_unique_passes_when_absent(self, setup):
        validator, repo, _ = setup
        repo.find_by_slug.return_value = None
        await validator.validate_slug_unique(1, "TalkoCDR", "lead_source")  # no raise

    async def test_validate_custom_field_exists_raises_for_wrong_partner(self, setup):
        validator, repo, _ = setup
        field_id = ObjectId()
        repo.find_by_id.return_value = {"_id": field_id, "partner_id": 999}
        with pytest.raises(TalkoResourceNotFound):
            await validator.validate_custom_field_exists(field_id, partner_id=1)

    async def test_validate_custom_field_exists_returns_doc_for_matching_partner(
        self, setup
    ):
        validator, repo, _ = setup
        field_id = ObjectId()
        repo.find_by_id.return_value = {"_id": field_id, "partner_id": 1}
        result = await validator.validate_custom_field_exists(field_id, partner_id=1)
        assert result["partner_id"] == 1

    async def test_validate_and_normalize_values_empty_raises(self, setup):
        validator, _, _ = setup
        with pytest.raises(TalkoBadRequestError):
            await validator.validate_and_normalize_values(1, "TalkoCDR", {})

    async def test_validate_and_normalize_values_unknown_slug_raises(self, setup):
        validator, repo, _ = setup
        repo.find_all.return_value = []
        with pytest.raises(TalkoBadRequestError):
            await validator.validate_and_normalize_values(1, "TalkoCDR", {"unknown": "x"})

    @pytest.mark.parametrize(
        "data_type,valid_value,invalid_value",
        [
            (TalkoCustomFieldDataType.STRING.value, "hello", 123),
            (TalkoCustomFieldDataType.NUMBER.value, 42, "not-a-number"),
            (
                TalkoCustomFieldDataType.NUMBER.value,
                3.14,
                True,
            ),  # bool must not pass as number
            (TalkoCustomFieldDataType.BOOLEAN.value, True, "true"),
            (TalkoCustomFieldDataType.DATE.value, 1765900000000, "2026-01-01"),
            (
                TalkoCustomFieldDataType.DATE.value,
                1765900000000,
                True,
            ),  # bool must not pass as date
        ],
    )
    async def test_validate_and_normalize_values_type_checks(
        self, setup, data_type, valid_value, invalid_value
    ):
        validator, repo, _ = setup
        repo.find_all.return_value = [
            {"field_slug": "field_x", "data_type": data_type, "choice_options": None}
        ]

        normalized = await validator.validate_and_normalize_values(
            1, "TalkoCDR", {"field_x": valid_value}
        )
        assert normalized == {"field_x": valid_value}

        with pytest.raises(TalkoBadRequestError):
            await validator.validate_and_normalize_values(
                1, "TalkoCDR", {"field_x": invalid_value}
            )

    async def test_validate_and_normalize_values_choice_rejects_unlisted_option(
        self, setup
    ):
        validator, repo, _ = setup
        repo.find_all.return_value = [
            {
                "field_slug": "lead_source",
                "data_type": TalkoCustomFieldDataType.CHOICE.value,
                "choice_options": ["Web", "Referral"],
            }
        ]

        normalized = await validator.validate_and_normalize_values(
            1, "TalkoCDR", {"lead_source": "Web"}
        )
        assert normalized == {"lead_source": "Web"}

        with pytest.raises(TalkoBadRequestError):
            await validator.validate_and_normalize_values(
                1, "TalkoCDR", {"lead_source": "NotAnOption"}
            )

    async def test_validate_and_normalize_values_none_passthrough(self, setup):
        validator, repo, _ = setup
        repo.find_all.return_value = [
            {
                "field_slug": "notes",
                "data_type": TalkoCustomFieldDataType.STRING.value,
                "choice_options": None,
            }
        ]
        normalized = await validator.validate_and_normalize_values(
            1, "TalkoCDR", {"notes": None}
        )
        assert normalized == {"notes": None}
