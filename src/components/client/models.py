from pydantic import ConfigDict, Field

from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoClientModel(TalkoTimestampedModel):
    """A client belongs to exactly one partner (partner_id FK).

    Forward-compat: billing_account_id links to the Phase 7 billing ledger.
    """

    partner_id: int = Field(description="Owning partner ID")
    name: str = Field(min_length=1, max_length=120, description="Client display name")
    workspace_ids: list[int] = Field(default_factory=list, description="Workspace IDs scoped to this client")
    is_active: bool = Field(default=True)
    billing_account_id: str | None = Field(default=None, description="Billing ledger account (Phase 7)")

    class CollectionName:
        CLIENT = "client"

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)
