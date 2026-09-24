from pydantic import BaseModel


class TalkoContract:
    class WebhookConfigCreate(BaseModel):
        partner_id: int
        url: str
        subscribed_events: list[str] | None = None

    class WebhookConfigUpdate(BaseModel):
        url: str | None = None
        is_active: bool | None = None
        subscribed_events: list[str] | None = None

    class WebhookConfigResponse(BaseModel):
        id: str
        partner_id: int
        url: str
        is_active: bool
        subscribed_events: list[str]
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
        status_code: int | None = None
        success: bool
        error: str | None = None
        duration_ms: int | None = None
        created_at: int
