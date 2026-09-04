from typing import List, Optional

from pydantic import BaseModel


class TalkoContract:
    class WebhookConfigCreate(BaseModel):
        partner_id: int
        url: str
        subscribed_events: Optional[List[str]] = None

    class WebhookConfigUpdate(BaseModel):
        url: Optional[str] = None
        is_active: Optional[bool] = None
        subscribed_events: Optional[List[str]] = None

    class WebhookConfigResponse(BaseModel):
        id: str
        partner_id: int
        url: str
        is_active: bool
        subscribed_events: List[str]
        signing_secret_last_4: str  # last 4 chars only, for admin confirmation
        created_at: int
        updated_at: int

    class DeliveryAttemptResponse(BaseModel):
        id: str
        partner_id: int
        event_type: str
        event_id: str
        url: str
        attempt_number: int
        status_code: Optional[int] = None
        success: bool
        error: Optional[str] = None
        duration_ms: Optional[int] = None
        created_at: int
