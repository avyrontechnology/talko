from unittest.mock import AsyncMock, Mock

import pytest
from bson import ObjectId

from src.components.did_management.models import TalkoPhoneNumberManagement
from src.components.did_management.services import TalkoDidManagementService
from src.exceptions import TalkoResourceNotFound
from src.utils.datetime_util import TalkoDateTimeUtil


def _svc():
    repo = AsyncMock()
    logger = Mock()
    dt = Mock(spec=TalkoDateTimeUtil)
    dt.get_current_time.return_value = 1_234_567_890
    validator = Mock()
    validator.validate_did_assignment = AsyncMock(return_value=None)
    partner_repo = AsyncMock()
    svc = TalkoDidManagementService(
        did_repository=repo,
        logger=logger,
        datetime_util=dt,
        validator=validator,
        partner_config_repository=partner_repo,
    )
    return svc, repo


class TestDualLayerModel:
    def test_normal_with_zero_bot_passes(self):
        m = TalkoPhoneNumberManagement(
            workspace_id=1,
            did_number="911234567890",
            partner_id=1,
            vendor_id=ObjectId(),
            vendor_config_id=ObjectId(),
            did_type="normal",
            agent_bot_id=0,
        )
        assert m.did_layer.value == "external"

    def test_internal_requires_parent(self):
        with pytest.raises(Exception):
            TalkoPhoneNumberManagement(
                workspace_id=1,
                did_number="911234567891",
                partner_id=1,
                vendor_id=ObjectId(),
                vendor_config_id=ObjectId(),
                did_layer="internal",
            )


class TestImportExternal:
    @pytest.mark.asyncio
    async def test_import_skips_duplicates(self):
        svc, repo = _svc()
        repo.find_did_by_did_number_and_vendor_id = AsyncMock(side_effect=[{"did_number": "111"}, None])
        repo.insert_did_default_attendance = AsyncMock(return_value={"did_number": "222"})
        out = await svc.import_external_dids(vendor_id=str(ObjectId()), did_numbers=["111", "222"])
        assert out["count"] == 1
        assert out["imported"] == ["222"]
        assert out["skipped"][0]["did_number"] == "111"


class TestProvisionInternal:
    @pytest.mark.asyncio
    async def test_provision_missing_parent_raises(self):
        svc, repo = _svc()
        repo.get_did_by_number = AsyncMock(return_value=None)
        with pytest.raises(TalkoResourceNotFound):
            await svc.provision_internal_did("999", partner_id=7)

    @pytest.mark.asyncio
    async def test_provision_ok_links_parent(self):
        svc, repo = _svc()
        parent_id = ObjectId()
        repo.get_did_by_number = AsyncMock(
            return_value={
                "_id": parent_id,
                "did_number": "91111",
                "did_layer": "external",
                "vendor_id": ObjectId(),
                "vendor_config_id": ObjectId(),
            }
        )
        repo.find_did_attendance = AsyncMock(return_value=None)
        repo.insert_did_default_attendance = AsyncMock(
            side_effect=lambda d: d,
        )
        out = await svc.provision_internal_did("91111", partner_id=7, workspace_id=3)
        assert out["did_layer"] == "internal"
        assert out["parent_did_number"] == "91111"
        assert out["partner_id"] == 7

    @pytest.mark.asyncio
    async def test_provision_idempotent(self):
        svc, repo = _svc()
        repo.get_did_by_number = AsyncMock(
            return_value={"_id": ObjectId(), "did_layer": "external", "vendor_id": ObjectId()}
        )
        repo.find_did_attendance = AsyncMock(
            return_value={"did_number": "91111", "did_layer": "internal", "status": "Mapped"}
        )
        out = await svc.provision_internal_did("91111", partner_id=7)
        assert out["status"] == "Mapped"


class TestMapExternalInternal:
    @pytest.mark.asyncio
    async def test_map_rejects_cross_parent(self):
        svc, repo = _svc()
        repo.get_did_by_number = AsyncMock(return_value={"_id": ObjectId(), "did_layer": "external"})
        repo.find_did_attendance = AsyncMock(
            return_value={
                "did_number": "IN1",
                "did_layer": "internal",
                "parent_did_number": "OTHER",
            }
        )
        with pytest.raises(ValueError):
            await svc.map_external_internal("EXT1", "IN1", partner_id=7)

    @pytest.mark.asyncio
    async def test_pool_utilization_passthrough(self):
        svc, repo = _svc()
        repo.get_pool_utilization = AsyncMock(
            return_value=[{"did_layer": "external", "status": "Available", "count": 2}]
        )
        rows = await svc.get_pool_utilization()
        assert rows[0]["count"] == 2
