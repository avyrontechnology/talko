from typing import Optional

from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoPartnerApiKeyModel(TalkoTimestampedModel):
    partner_id: int
    key_prefix: str  # e.g. "tkp_live_ab12cd34" — safe to display, never the full key
    key_hash: str  # SHA-256 hex digest of the full raw key; the raw key is never stored
    label: Optional[str] = None
    is_active: bool = True
    created_by_user_id: Optional[int] = None
    last_used_at: Optional[int] = None
    revoked_at: Optional[int] = None

    class CollectionName:
        PARTNER_API_KEYS = "partner_api_keys"
