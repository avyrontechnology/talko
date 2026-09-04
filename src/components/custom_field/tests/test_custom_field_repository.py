from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.custom_field.repository import TalkoCustomFieldRepository
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoFakeCursor:
    def __init__(self, data=None):
        self._data = data or []

    def sort(self, *_, **__):
        return self

    async def to_list(self, *_):
        return self._data


@pytest.mark.asyncio
class TestCustomFieldRepository:
    @pytest.fixture
    def setup(self):
        mock_db_manager = MagicMock()
        mock_logger = MagicMock(spec=TalkoServiceLogger)
        repo = TalkoCustomFieldRepository(mock_db_manager, mock_logger)
        return repo, mock_db_manager, mock_logger

    def _mock_collection(self, mock_db_manager, mock_collection):
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

    async def test_insert_custom_field_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="field123")
        )
        self._mock_collection(mock_db_manager, mock_collection)

        result = await repo.insert_custom_field({"field_slug": "lead_source"})
        assert result == "field123"

    async def test_insert_custom_field_exception_logged_and_raised(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(side_effect=Exception("insert failed"))
        self._mock_collection(mock_db_manager, mock_collection)

        with pytest.raises(Exception, match="insert failed"):
            await repo.insert_custom_field({})
        assert "insert failed" in mock_logger.error.call_args[0][0]

    async def test_find_by_slug_returns_document(self, setup):
        repo, mock_db_manager, _ = setup
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value={"field_slug": "lead_source"})
        self._mock_collection(mock_db_manager, mock_collection)

        result = await repo.find_by_slug(1, "TalkoCDR", "lead_source")
        assert result == {"field_slug": "lead_source"}
        mock_collection.find_one.assert_awaited_once_with(
            {"partner_id": 1, "entity_type": "TalkoCDR", "field_slug": "lead_source"}
        )

    async def test_find_all_filters_inactive_by_default(self, setup):
        repo, mock_db_manager, _ = setup
        mock_collection = MagicMock()
        mock_collection.find.return_value = TalkoFakeCursor([{"field_slug": "a"}])
        self._mock_collection(mock_db_manager, mock_collection)

        result = await repo.find_all(1, "TalkoCDR")
        assert result == [{"field_slug": "a"}]
        query = mock_collection.find.call_args[0][0]
        assert query == {"partner_id": 1, "entity_type": "TalkoCDR", "is_active": True}

    async def test_find_all_include_inactive_skips_active_filter(self, setup):
        repo, mock_db_manager, _ = setup
        mock_collection = MagicMock()
        mock_collection.find.return_value = TalkoFakeCursor([])
        self._mock_collection(mock_db_manager, mock_collection)

        await repo.find_all(1, "TalkoCDR", include_inactive=True)
        query = mock_collection.find.call_args[0][0]
        assert "is_active" not in query

    async def test_update_by_id_uses_set_operator(self, setup):
        repo, mock_db_manager, _ = setup
        field_id = ObjectId()
        mock_collection = MagicMock()
        mock_collection.find_one_and_update = AsyncMock(
            return_value={"_id": field_id, "is_active": False}
        )
        self._mock_collection(mock_db_manager, mock_collection)

        result = await repo.update_by_id(field_id, {"is_active": False})
        assert result["is_active"] is False
        mock_collection.find_one_and_update.assert_awaited_once_with(
            {"_id": field_id},
            {"$set": {"is_active": False}},
            return_document=True,
        )
