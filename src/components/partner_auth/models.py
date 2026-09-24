from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoPartnerApiKeyModel(TalkoTimestampedModel):
    partner_id: int
    key_prefix: str  # e.g. "tkp_live_ab12cd34" — safe to display, never the full key
    key_hash: str  # SHA-256 hex digest of the full raw key; the raw key is never stored
    label: str | None = None
    is_active: bool = True
    created_by_user_id: int | None = None
    last_used_at: int | None = None
    revoked_at: int | None = None

    class CollectionName:
        PARTNER_API_KEYS = "partner_api_keys"
