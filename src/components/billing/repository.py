import math
from typing import Any

from src.components.billing.models import (
    TalkoLedgerModel,
    TalkoRateCardModel,
    TalkoTransactionModel,
)
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


def billed_minutes(talk_seconds: Any, total_seconds: Any) -> int:
    """Ceil call seconds to billable minutes. Pure helper (module-level so
    repository mocks in tests never swallow it)."""
    base = talk_seconds or total_seconds or 0
    try:
        base = int(float(base))
    except (TypeError, ValueError):
        base = 0
    if base <= 0:
        return 0
    return int(math.ceil(base / 60))


class TalkoBillingRepository:
    def __init__(self, db_manager: TalkoDocDatabaseSessionManager, logger: TalkoServiceLogger) -> None:
        self.__db_manager = db_manager
        self.__logger = logger

    async def upsert_rate_card(self, doc: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self.__db_manager.connect() as db:
                collection = db[TalkoRateCardModel.CollectionName.RATE_CARD]
                return await collection.find_one_and_update(
                    {"vendor_type": doc["vendor_type"]},
                    {"$set": doc},
                    upsert=True,
                    return_document=True,
                )
        except Exception as e:
            self.__logger.error(f"Failed to save rate card: {str(e)}")
            raise

    async def list_rate_cards(self) -> list[dict[str, Any]]:
        try:
            async with self.__db_manager.collection(TalkoRateCardModel.CollectionName.RATE_CARD) as collection:
                return [doc async for doc in collection.find({"is_active": True})]
        except Exception as e:
            self.__logger.error(f"Failed to list rate cards: {str(e)}")
            raise

    async def find_rate_card(self, vendor_type: str) -> dict[str, Any] | None:
        try:
            async with self.__db_manager.collection(TalkoRateCardModel.CollectionName.RATE_CARD) as collection:
                card = await collection.find_one({"vendor_type": vendor_type, "is_active": True})
                if card is None and vendor_type != "default":
                    card = await collection.find_one({"vendor_type": "default", "is_active": True})
                return card
        except Exception as e:
            self.__logger.error(f"Failed to find rate card: {str(e)}")
            raise

    async def get_ledger(self, partner_id: int, client_id: str | None = None) -> dict[str, Any] | None:
        try:
            query: dict[str, Any] = {"partner_id": partner_id}
            query["client_id"] = client_id
            async with self.__db_manager.collection(TalkoLedgerModel.CollectionName.LEDGER) as collection:
                return await collection.find_one(query)
        except Exception as e:
            self.__logger.error(f"Failed to get ledger: {str(e)}")
            raise

    async def adjust_ledger(
        self,
        partner_id: int,
        amount: float,
        client_id: str | None = None,
        currency: str = "INR",
        enforce_balance: bool | None = None,
    ) -> dict[str, Any]:
        """Atomic balance adjust (creates the ledger on first topup)."""
        try:
            async with self.__db_manager.connect() as db:
                collection = db[TalkoLedgerModel.CollectionName.LEDGER]
                update: dict[str, Any] = {"$inc": {"balance": amount}}
                set_on_insert: dict[str, Any] = {
                    "partner_id": partner_id,
                    "client_id": client_id,
                    "currency": currency,
                    "is_active": True,
                }
                if enforce_balance is not None:
                    update["$set"] = {"enforce_balance": enforce_balance}
                update["$setOnInsert"] = set_on_insert
                return await collection.find_one_and_update(
                    {"partner_id": partner_id, "client_id": client_id},
                    update,
                    upsert=True,
                    return_document=True,
                )
        except Exception as e:
            self.__logger.error(f"Failed to adjust ledger: {str(e)}")
            raise

    async def insert_transaction(self, doc: dict[str, Any]) -> str:
        try:
            async with self.__db_manager.collection(TalkoTransactionModel.CollectionName.TRANSACTION) as collection:
                result = await collection.insert_one(doc)
                return str(result.inserted_id)
        except Exception as e:
            self.__logger.error(f"Failed to insert transaction: {str(e)}")
            raise

    async def find_transaction_by_call(self, call_id: str) -> dict[str, Any] | None:
        try:
            async with self.__db_manager.collection(TalkoTransactionModel.CollectionName.TRANSACTION) as collection:
                return await collection.find_one({"call_id": call_id, "kind": "debit"})
        except Exception as e:
            self.__logger.error(f"Failed to find transaction: {str(e)}")
            raise

    async def list_transactions(self, partner_id: int, limit: int = 50) -> list[dict[str, Any]]:
        try:
            async with self.__db_manager.collection(TalkoTransactionModel.CollectionName.TRANSACTION) as collection:
                cursor = collection.find({"partner_id": partner_id}).sort("created_at", -1).limit(limit)
                return [doc async for doc in cursor]
        except Exception as e:
            self.__logger.error(f"Failed to list transactions: {str(e)}")
            raise
