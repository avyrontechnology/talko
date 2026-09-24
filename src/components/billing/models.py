from pydantic import ConfigDict, Field

from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoRateCardModel(TalkoTimestampedModel):
    """Per-vendor sell rate. `vendor_type="default"` is the fallback."""

    vendor_type: str = Field(description="Vendor type or 'default'")
    per_min_rate: float = Field(ge=0, description="Price per billed minute")
    per_call_rate: float = Field(default=0, ge=0, description="Flat price per call")
    currency: str = Field(default="INR")
    is_active: bool = Field(default=True)

    class CollectionName:
        RATE_CARD = "billing_rate_card"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)


class TalkoLedgerModel(TalkoTimestampedModel):
    """Balance account for a partner or a client (client_id wins when set)."""

    partner_id: int = Field(description="Owning partner ID")
    client_id: str | None = Field(default=None, description="Client _id for client-scoped ledgers")
    balance: float = Field(default=0)
    currency: str = Field(default="INR")
    enforce_balance: bool = Field(
        default=False,
        description="When True, initiate_call rejects calls at balance<=0",
    )
    is_active: bool = Field(default=True)

    class CollectionName:
        LEDGER = "billing_ledger"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)


class TalkoTransactionModel(TalkoTimestampedModel):
    """Immutable money movement. call_id unique per debit (idempotency)."""

    partner_id: int
    client_id: str | None = None
    kind: str = Field(description="debit | credit | topup")
    amount: float = Field(description="Signed amount (debits negative)")
    currency: str = Field(default="INR")
    call_id: str | None = Field(default=None, description="Priced call (debits)")
    remark: str | None = None

    class CollectionName:
        TRANSACTION = "billing_transaction"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)
