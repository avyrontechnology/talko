from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.billing.dto import TalkoContract
from src.components.billing.services import TalkoBillingService
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound


def _svc():
    repo = AsyncMock()
    call_repo = AsyncMock()
    logger = MagicMock()
    dt = MagicMock()
    dt.get_current_time.return_value = 1234
    return (
        TalkoBillingService(
            repository=repo,
            call_repository=call_repo,
            logger=logger,
            datetime_util=dt,
        ),
        repo,
        call_repo,
    )


class TestRateCard:
    @pytest.mark.asyncio
    async def test_save_and_list(self):
        svc, repo, _ = _svc()
        repo.upsert_rate_card = AsyncMock(
            return_value={
                "_id": ObjectId(),
                "vendor_type": "otoba",
                "per_min_rate": 1.5,
                "per_call_rate": 0.5,
                "currency": "INR",
                "is_active": True,
            }
        )
        out = await svc.save_rate_card(
            TalkoContract.RateCardCreate(vendor_type="otoba", per_min_rate=1.5, per_call_rate=0.5)
        )
        assert out.vendor_type == "otoba"
        assert out.per_min_rate == 1.5


class TestTopup:
    @pytest.mark.asyncio
    async def test_topup_creates_txn(self):
        svc, repo, _ = _svc()
        repo.adjust_ledger = AsyncMock(
            return_value={
                "_id": ObjectId(),
                "partner_id": 7,
                "client_id": None,
                "balance": 100.0,
                "currency": "INR",
                "enforce_balance": False,
            }
        )
        repo.insert_transaction = AsyncMock(return_value=str(ObjectId()))
        out = await svc.topup(TalkoContract.TopupRequest(partner_id=7, amount=100))
        assert out.balance == 100.0
        repo.insert_transaction.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_topup_rejects_nonpositive(self):
        svc, _, _ = _svc()
        with pytest.raises(TalkoBadRequestError):
            await svc.topup(TalkoContract.TopupRequest(partner_id=7, amount=0))


class TestPrice:
    @pytest.mark.asyncio
    async def test_price_debits_ledger(self):
        svc, repo, call_repo = _svc()
        call_repo.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value={
                "call_id": "C1",
                "partner_id": 7,
                "vendor_type": "otoba",
                "talk_time": 90,
                "total_call_duration": 120,
            }
        )
        repo.find_transaction_by_call = AsyncMock(return_value=None)
        repo.find_rate_card = AsyncMock(return_value={"per_min_rate": 2.0, "per_call_rate": 1.0, "currency": "INR"})
        repo.adjust_ledger = AsyncMock(return_value={"balance": 95.0})
        repo.insert_transaction = AsyncMock(return_value=str(ObjectId()))
        out = await svc.price_call("C1")
        # 90s -> 2 min * 2.0 + 1.0 = 5.0
        assert out.billed_minutes == 2
        assert out.amount == 5.0
        assert out.ledger_balance == 95.0

    @pytest.mark.asyncio
    async def test_price_idempotent(self):
        svc, repo, call_repo = _svc()
        call_repo.get_cdr_by_call_id_or_uuid = AsyncMock(return_value={"call_id": "C1"})
        repo.find_transaction_by_call = AsyncMock(return_value={"_id": ObjectId()})
        with pytest.raises(TalkoBadRequestError):
            await svc.price_call("C1")

    @pytest.mark.asyncio
    async def test_price_missing_cdr(self):
        svc, repo, call_repo = _svc()
        call_repo.get_cdr_by_call_id_or_uuid = AsyncMock(return_value=None)
        with pytest.raises(TalkoResourceNotFound):
            await svc.price_call("NOPE")

    @pytest.mark.asyncio
    async def test_zero_duration_free(self):
        svc, repo, call_repo = _svc()
        call_repo.get_cdr_by_call_id_or_uuid = AsyncMock(
            return_value={
                "call_id": "C2",
                "partner_id": 7,
                "talk_time": 0,
                "total_call_duration": 0,
            }
        )
        repo.find_transaction_by_call = AsyncMock(return_value=None)
        repo.find_rate_card = AsyncMock(return_value=None)
        repo.adjust_ledger = AsyncMock(return_value={"balance": 10.0})
        repo.insert_transaction = AsyncMock(return_value=str(ObjectId()))
        out = await svc.price_call("C2")
        assert out.amount == 0


class TestGuard:
    def test_enforced_zero_blocks(self):
        svc, _, _ = _svc()
        with pytest.raises(TalkoBadRequestError):
            svc.check_balance({"partner_id": 7, "balance": 0, "enforce_balance": True})

    def test_unenforced_passes(self):
        svc, _, _ = _svc()
        svc.check_balance({"partner_id": 7, "balance": -5, "enforce_balance": False})

    def test_billed_minutes(self):
        from src.components.billing.repository import billed_minutes

        assert billed_minutes(90, 120) == 2
        assert billed_minutes(60, 60) == 1
        assert billed_minutes(0, 0) == 0
        assert billed_minutes(None, None) == 0
