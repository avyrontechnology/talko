import asyncio
from typing import Any, Dict

import httpx
from celery import shared_task

from src.core.container import TalkoContainer


@shared_task(
    bind=True,
    autoretry_for=(httpx.HTTPStatusError, httpx.RequestError),
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=6,
    soft_time_limit=30,
    time_limit=45,
)
def deliver_webhook_event(
    self, partner_id: int, event_type: str, event_id: str, payload: Dict[str, Any]
) -> str:
    """Thin asyncio.run() wrapper — all delivery logic lives in
    TalkoPartnerWebhookService.deliver_event so it stays unit-testable
    without going through asyncio.run() (see that method's docstring).

    Fire-and-forget from the caller's perspective (see call_webhook.py's
    trigger site) — retries with backoff on failure via autoretry_for.
    """
    container = TalkoContainer()
    webhook_service = container.partner_webhook_service()

    return asyncio.run(
        webhook_service.deliver_event(
            partner_id=partner_id,
            event_type=event_type,
            event_id=event_id,
            payload=payload,
            attempt_number=self.request.retries + 1,
        )
    )
