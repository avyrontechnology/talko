from pydantic import ConfigDict, Field

from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoClientModel(TalkoTimestampedModel):
    """A client belongs to exactly one partner (partner_id FK).

    Forward-compat: billing_account_id links to the Phase 7 billing ledger.
    """

    partner_id: int = Field(description="Owning partner ID")
    name: str = Field(min_length=1, max_length=120, description="Client display name")
    contact_name: str | None = Field(default=None, max_length=120, description="Contact person for this sub-account")
    email: str | None = Field(default=None, max_length=254, description="Contact email")
    phone: str | None = Field(default=None, max_length=20, description="Contact phone")
    external_ref: str | None = Field(default=None, max_length=120, description="Maglo/CRM account ID for reconciliation")
    notes: str | None = Field(default=None, max_length=2000, description="Ops notes")
    tags: list[str] = Field(default_factory=list, description="Ops tags")
    is_active: bool = Field(default=True)
    billing_account_id: str | None = Field(default=None, description="Billing ledger account (Phase 7)")

    class CollectionName:
        CLIENT = "client"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)
