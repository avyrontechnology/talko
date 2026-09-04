from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.cdr.repository import TalkoCDRRepository
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoFakeCursor:
    """Fake async cursor for mocking MongoDB cursor methods"""

    def __init__(self, data=None, raise_exc=None):
        self._data = data or []
        self._raise_exc = raise_exc

    def sort(self, *_, **__):
        if self._raise_exc:
            raise self._raise_exc
        return self

    def skip(self, *_):
        return self

    def limit(self, *_):
        return self

    def max_time_ms(self, *_):
        return self

    async def to_list(self, *_):
        if self._raise_exc:
            raise self._raise_exc
        return self._data

    def __aiter__(self):
        async def gen():
            if self._raise_exc:
                raise self._raise_exc
            for item in self._data:
                yield item

        return gen()


@pytest.mark.asyncio
class TestCDRRepository:

    @pytest.fixture
    def setup(self):
        mock_db_manager = MagicMock()
        mock_logger = MagicMock(spec=TalkoServiceLogger)
        repo = TalkoCDRRepository(mock_db_manager, mock_logger)
        return repo, mock_db_manager, mock_logger

    async def test_insert_cdr_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="12345")
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        result = await repo.insert_cdr({"call_id": "abc"})
        assert result == "12345"
        mock_logger.info.assert_called_once()

    async def test_insert_cdr_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(side_effect=Exception("Insert failed"))
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(Exception, match="Insert failed"):
            await repo.insert_cdr({"call_id": "xyz"})
        assert "Insert failed" in mock_logger.error.call_args[0][0]

    async def test_find_all_cdrs_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.find.return_value = TalkoFakeCursor(
            [{"call_id": "1"}, {"call_id": "2"}]
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        results = await repo.find_all_cdrs_on_the_basis_of_partner_id(
            123, 0, 20, 23442545
        )
        assert results == [{"call_id": "1"}, {"call_id": "2"}]

    async def test_find_all_cdrs_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.find.side_effect = Exception("Find failed")
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(Exception, match="Find failed"):
            await repo.find_all_cdrs_on_the_basis_of_partner_id(123, 0, 2, 1232)
        assert "Find failed" in mock_logger.error.call_args[0][0]

    async def test_get_cdrs_by_criteria_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.find.return_value = TalkoFakeCursor(
            [{"call_id": "1"}, {"call_id": "2"}]
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        result = await repo.get_cdrs_by_criteria({"partner_id": 123})
        assert result == [{"call_id": "1"}, {"call_id": "2"}]

    async def test_get_cdrs_by_criteria_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.find.return_value = TalkoFakeCursor(
            raise_exc=Exception("DB failure")
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(Exception, match="DB failure"):
            await repo.get_cdrs_by_criteria({"partner_id": 123})
        assert "DB failure" in mock_logger.error.call_args[0][0]

    async def test_find_agent_call_logs_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        # find_all_call_logs_on_the_basis_of_user_id runs a single $facet
        # aggregation returning both the page ("data") and the total ("count")
        # in one document.
        mock_collection.aggregate.return_value = TalkoFakeCursor(
            [
                {
                    "data": [{"call_id": "1"}, {"call_id": "2"}],
                    "count": [{"total": 2}],
                }
            ]
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        results, total = await repo.find_all_call_logs_on_the_basis_of_user_id(
            123, 2, 1, {}
        )
        assert total == 2
        assert results == [{"call_id": "1"}, {"call_id": "2"}]

    async def test_find_agent_call_logs_exception_branch(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = TalkoFakeCursor(
            raise_exc=Exception("Aggregate failed")
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(Exception, match="Aggregate failed"):
            await repo.find_all_call_logs_on_the_basis_of_user_id(321, 10, 1, {})
        assert "Aggregate failed" in mock_logger.error.call_args[0][0]


@pytest.mark.asyncio
class TestCDRRepositoryCustomFields:
    @pytest.fixture
    def setup(self):
        mock_db_manager = MagicMock()
        mock_logger = MagicMock(spec=TalkoServiceLogger)
        repo = TalkoCDRRepository(mock_db_manager, mock_logger)
        return repo, mock_db_manager, mock_logger

    async def test_find_cdr_by_call_id_success(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "_id": "abc",
                "call_id": "call-1",
                "partner_id": 1,
                "custom_fields": {"lead_source": "Web"},
            }
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        result = await repo.find_cdr_by_call_id("call-1")
        assert result["partner_id"] == 1
        assert result["custom_fields"] == {"lead_source": "Web"}
        mock_collection.find_one.assert_awaited_once()
        query = mock_collection.find_one.call_args[0][0]
        assert query == {"call_id": "call-1"}

    async def test_find_cdr_by_call_id_not_found(self, setup):
        repo, mock_db_manager, _ = setup
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        result = await repo.find_cdr_by_call_id("missing")
        assert result is None

    async def test_find_cdr_by_call_id_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(side_effect=Exception("db down"))
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(Exception, match="db down"):
            await repo.find_cdr_by_call_id("call-1")
        assert "db down" in mock_logger.error.call_args[0][0]

    async def test_set_custom_field_values_uses_dot_notation_set(self, setup):
        repo, mock_db_manager, _ = setup
        mock_collection = MagicMock()
        mock_collection.find_one_and_update = AsyncMock(
            return_value={
                "_id": "abc",
                "call_id": "call-1",
                "custom_fields": {"lead_source": "Web"},
            }
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        result = await repo.set_custom_field_values(
            "call-1", {"lead_source": "Web"}, 1735689600000
        )
        assert result["custom_fields"] == {"lead_source": "Web"}

        call_args = mock_collection.find_one_and_update.call_args
        assert call_args[0][0] == {"call_id": "call-1"}
        update_ops = call_args[0][1]["$set"]
        assert update_ops["custom_fields.lead_source"] == "Web"
        assert update_ops["updated_at"] == 1735689600000

    async def test_set_custom_field_values_exception(self, setup):
        repo, mock_db_manager, mock_logger = setup
        mock_collection = MagicMock()
        mock_collection.find_one_and_update = AsyncMock(
            side_effect=Exception("update failed")
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_collection
        mock_db_manager.collection.return_value = mock_cm

        with pytest.raises(Exception, match="update failed"):
            await repo.set_custom_field_values("call-1", {"x": 1}, 123)
        assert "update failed" in mock_logger.error.call_args[0][0]
