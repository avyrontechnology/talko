from pydantic import BaseModel


class TalkoContract:
    class RateCardCreate(BaseModel):
        vendor_type: str = "default"
        per_min_rate: float = 0
        per_call_rate: float = 0
        currency: str = "INR"

    class RateCardResponse(BaseModel):
        id: str
        vendor_type: str
        per_min_rate: float
        per_call_rate: float
        currency: str
        is_active: bool = True

    class TopupRequest(BaseModel):
        partner_id: int
        amount: float
        client_id: str | None = None
        currency: str = "INR"
        enforce_balance: bool | None = None
        remark: str | None = None

    class LedgerResponse(BaseModel):
        id: str
        partner_id: int
        client_id: str | None = None
        balance: float
        currency: str
        enforce_balance: bool

    class TransactionResponse(BaseModel):
        id: str
        partner_id: int
        client_id: str | None = None
        kind: str
        amount: float
        currency: str
        call_id: str | None = None
        remark: str | None = None

    class PriceRequest(BaseModel):
        call_id: str
        client_id: str | None = None

    class PriceResponse(BaseModel):
        call_id: str
        billed_minutes: int
        amount: float
        currency: str
        ledger_balance: float
