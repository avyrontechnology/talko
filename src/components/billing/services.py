from src.components.billing.dto import TalkoContract
from src.components.billing.message import (
    CALL_ALREADY_PRICED,
    CDR_NOT_FOUND,
    INSUFFICIENT_BALANCE,
)
from src.components.billing.models import (
    TalkoRateCardModel,
    TalkoTransactionModel,
)
from src.components.billing.repository import TalkoBillingRepository, billed_minutes
from src.components.call_management.repository import TalkoCallRepository
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil


class TalkoBillingService:
    """Wholesaler/reseller billing: rate cards, ledgers, per-call pricing."""

    def __init__(
        self,
        repository: TalkoBillingRepository,
        call_repository: TalkoCallRepository,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
    ):
        self.__repository = repository
        self.__call_repository = call_repository
        self.__logger = logger
        self.__datetime_util = datetime_util

    @staticmethod
    def _doc_to_rate(doc: dict) -> TalkoContract.RateCardResponse:
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return TalkoContract.RateCardResponse(**doc)

    @staticmethod
    def _doc_to_ledger(doc: dict) -> TalkoContract.LedgerResponse:
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return TalkoContract.LedgerResponse(**doc)

    @staticmethod
    def _doc_to_txn(doc: dict) -> TalkoContract.TransactionResponse:
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return TalkoContract.TransactionResponse(**doc)

    async def save_rate_card(self, payload: TalkoContract.RateCardCreate) -> TalkoContract.RateCardResponse:
        doc = TalkoRateCardModel(
            vendor_type=payload.vendor_type or "default",
            per_min_rate=payload.per_min_rate,
            per_call_rate=payload.per_call_rate,
            currency=payload.currency,
            is_active=True,
        ).model_dump()
        saved = await self.__repository.upsert_rate_card(doc)
        return self._doc_to_rate(saved)

    async def list_rate_cards(self) -> list[TalkoContract.RateCardResponse]:
        return [self._doc_to_rate(d) for d in await self.__repository.list_rate_cards()]

    async def topup(self, payload: TalkoContract.TopupRequest) -> TalkoContract.LedgerResponse:
        if payload.amount <= 0:
            raise TalkoBadRequestError("Topup amount must be positive")
        now = self.__datetime_util.get_current_time()
        ledger = await self.__repository.adjust_ledger(
            partner_id=payload.partner_id,
            amount=payload.amount,
            client_id=payload.client_id,
            currency=payload.currency,
            enforce_balance=payload.enforce_balance,
        )
        await self.__repository.insert_transaction(
            TalkoTransactionModel(
                partner_id=payload.partner_id,
                client_id=payload.client_id,
                kind="topup",
                amount=payload.amount,
                currency=payload.currency,
                remark=payload.remark or "topup",
                created_at=now,
            ).model_dump()
        )
        self.__logger.info(f"Topup partner={payload.partner_id} amount={payload.amount}")
        return self._doc_to_ledger(ledger)

    async def get_ledger(self, partner_id: int, client_id: str | None = None) -> TalkoContract.LedgerResponse:
        doc = await self.__repository.get_ledger(partner_id, client_id)
        if not doc:
            raise TalkoResourceNotFound(f"No ledger for partner {partner_id}")
        return self._doc_to_ledger(doc)

    async def list_transactions(self, partner_id: int, limit: int = 50) -> list[TalkoContract.TransactionResponse]:
        return [self._doc_to_txn(d) for d in await self.__repository.list_transactions(partner_id, limit)]

    def check_balance(self, ledger: dict) -> None:
        """Enforce only opt-in ledgers (fail-open when no ledger / not enforced)."""
        if ledger and ledger.get("enforce_balance") and ledger.get("balance", 0) <= 0:
            raise TalkoBadRequestError(INSUFFICIENT_BALANCE.format(ledger.get("partner_id"), ledger.get("balance")))

    async def price_call(self, call_id: str, client_id: str | None = None) -> TalkoContract.PriceResponse:
        cdr = await self.__call_repository.get_cdr_by_call_id_or_uuid(call_id, None)
        if not cdr:
            raise TalkoResourceNotFound(CDR_NOT_FOUND.format(call_id))
        existing = await self.__repository.find_transaction_by_call(call_id)
        if existing:
            self.__logger.info(CALL_ALREADY_PRICED + f" call_id={call_id}")
            raise TalkoBadRequestError(CALL_ALREADY_PRICED)
        vendor_type = str(cdr.get("vendor_type") or cdr.get("vendor_id") or "default")
        card = await self.__repository.find_rate_card(vendor_type)
        per_min = float((card or {}).get("per_min_rate", 0))
        per_call = float((card or {}).get("per_call_rate", 0))
        currency = str((card or {}).get("currency", "INR"))
        minutes = billed_minutes(cdr.get("talk_time"), cdr.get("total_call_duration"))
        amount = round(per_call + per_min * minutes, 2)
        partner_id = int(cdr.get("partner_id") or 0)
        now = self.__datetime_util.get_current_time()
        ledger = await self.__repository.adjust_ledger(
            partner_id=partner_id,
            amount=-amount,
            client_id=client_id,
            currency=currency,
        )
        await self.__repository.insert_transaction(
            TalkoTransactionModel(
                partner_id=partner_id,
                client_id=client_id,
                kind="debit",
                amount=-amount,
                currency=currency,
                call_id=call_id,
                remark=f"call {call_id} ({minutes} min)",
                created_at=now,
            ).model_dump()
        )
        self.__logger.info(f"Priced call_id={call_id} minutes={minutes} amount={amount}")
        return TalkoContract.PriceResponse(
            call_id=call_id,
            billed_minutes=minutes,
            amount=amount,
            currency=currency,
            ledger_balance=float(ledger.get("balance", 0)),
        )
