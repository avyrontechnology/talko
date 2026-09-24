from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.client.dto import TalkoContract
from src.components.client.services import TalkoClientService
from src.exceptions import TalkoConflictError, TalkoResourceNotFound


def _svc():
    repo = AsyncMock()
    logger = MagicMock()
    dt = MagicMock()
    dt.get_current_time.return_value = 1234
    return TalkoClientService(repository=repo, logger=logger, datetime_util=dt), repo


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_ok(self):
        svc, repo = _svc()
        repo.find_by_name = AsyncMock(return_value=None)
        repo.insert_client = AsyncMock(return_value=str(ObjectId()))
        out = await svc.create_client(TalkoContract.ClientCreate(partner_id=7, name="Acme", workspace_ids=[1]))
        assert out.message == "Client created successfully"
        assert out.id

    @pytest.mark.asyncio
    async def test_duplicate_name(self):
        svc, repo = _svc()
        repo.find_by_name = AsyncMock(return_value={"_id": ObjectId()})
        with pytest.raises(TalkoConflictError):
            await svc.create_client(TalkoContract.ClientCreate(partner_id=7, name="Acme"))

    @pytest.mark.asyncio
    async def test_blank_name(self):
        svc, repo = _svc()
        from src.exceptions import TalkoBadRequestError

        with pytest.raises(TalkoBadRequestError):
            await svc.create_client(TalkoContract.ClientCreate(partner_id=7, name="  "))


class TestReadUpdate:
    @pytest.mark.asyncio
    async def test_list_maps_ids(self):
        svc, repo = _svc()
        repo.find_by_partner = AsyncMock(
            return_value=[
                {
                    "_id": ObjectId(),
                    "partner_id": 7,
                    "name": "A",
                    "workspace_ids": [],
                    "is_active": True,
                }
            ]
        )
        out = await svc.list_clients(7)
        assert len(out) == 1 and out[0].name == "A"

    @pytest.mark.asyncio
    async def test_get_missing(self):
        svc, repo = _svc()
        repo.find_by_id = AsyncMock(return_value=None)
        with pytest.raises(TalkoResourceNotFound):
            await svc.get_client(str(ObjectId()))

    @pytest.mark.asyncio
    async def test_update_missing(self):
        svc, repo = _svc()
        repo.update_client = AsyncMock(return_value=None)
        with pytest.raises(TalkoResourceNotFound):
            await svc.update_client(str(ObjectId()), TalkoContract.ClientUpdate(name="B"))

    @pytest.mark.asyncio
    async def test_set_active(self):
        svc, repo = _svc()
        repo.update_client = AsyncMock(return_value={"_id": ObjectId()})
        out = await svc.set_active(str(ObjectId()), False)
        assert "deactivated" in out.message
