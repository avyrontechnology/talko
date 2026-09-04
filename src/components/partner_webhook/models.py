from typing import List, Optional

from pydantic import Field

from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoPartnerWebhookConfigModel(TalkoTimestampedModel):
    partner_id: int
    url: str
    is_active: bool = True
    signing_secret_encrypted: str  # Fernet ciphertext — read back at delivery time to sign
    subscribed_events: List[str] = Field(default_factory=lambda: ["call.completed"])
    created_by_user_id: Optional[int] = None

    class CollectionName:
        PARTNER_WEBHOOK_CONFIGS = "partner_webhook_configs"


class TalkoWebhookDeliveryAttemptModel(TalkoTimestampedModel):
    partner_id: int
    event_type: str
    event_id: str  # uuid4, stable across retries of the same logical event
    url: str
    attempt_number: int
    status_code: Optional[int] = None
    success: bool = False
    error: Optional[str] = None
    duration_ms: Optional[int] = None

    class CollectionName:
        WEBHOOK_DELIVERY_ATTEMPTS = "webhook_delivery_attempts"
