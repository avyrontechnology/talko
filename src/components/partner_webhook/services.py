import json
import secrets
import time
from typing import Any, Dict, List, Optional

import httpx

from src.components.partner_webhook.constant import (
    DEFAULT_DELIVERY_ATTEMPTS_LIMIT,
    DELIVERY_TIMEOUT_SECONDS,
)
from src.components.partner_webhook.crypto import TalkoWebhookSecretCipher
from src.components.partner_webhook.dto import TalkoContract
from src.components.partner_webhook.message import PARTNER_WEBHOOK_CONFIG_NOT_FOUND
from src.components.partner_webhook.models import TalkoPartnerWebhookConfigModel
from src.components.partner_webhook.repository import TalkoPartnerWebhookRepository
from src.components.partner_webhook.signing import TalkoWebhookSigner
from src.components.partner_webhook.validation import TalkoPartnerWebhookValidator
from src.exceptions import TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil


class TalkoPartnerWebhookService:
    def __init__(
        self,
        repository: TalkoPartnerWebhookRepository,
        validator: TalkoPartnerWebhookValidator,
        cipher: TalkoWebhookSecretCipher,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
    ):
        self.repository = repository
        self.validator = validator
        self.cipher = cipher
        self.logger = logger
        self.datetime_util = datetime_util

    async def create_webhook_config(
        self, data: TalkoContract.WebhookConfigCreate, created_by_user_id: Optional[int]
    ) -> TalkoContract.WebhookConfigResponse:
        self.logger.info(
            "Creating webhook config for partner_id: {}".format(data.partner_id)
        )
        self.validator.validate_url_is_https(data.url)
        await self.validator.check_config_does_not_already_exist(data.partner_id)

        raw_secret = secrets.token_urlsafe(32)
        now = self.datetime_util.get_current_time()
        model = TalkoPartnerWebhookConfigModel(
            partner_id=data.partner_id,
            url=data.url,
            signing_secret_encrypted=self.cipher.encrypt(raw_secret),
            subscribed_events=data.subscribed_events or ["call.completed"],
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        doc = model.model_dump(exclude_unset=False)
        config_id = await self.repository.insert_config(doc)
        self.logger.info(
            "Created webhook config {} for partner_id: {}".format(
                config_id, data.partner_id
            )
        )
        return TalkoContract.WebhookConfigResponse(
            id=config_id,
            partner_id=data.partner_id,
            url=data.url,
            is_active=True,
            subscribed_events=model.subscribed_events,
            signing_secret_last_4=raw_secret[-4:],
            created_at=now,
            updated_at=now,
        )

    async def update_webhook_config(
        self, partner_id: int, data: TalkoContract.WebhookConfigUpdate
    ) -> TalkoContract.WebhookConfigResponse:
        self.logger.info("Updating webhook config for partner_id: {}".format(partner_id))
        if data.url is not None:
            self.validator.validate_url_is_https(data.url)

        update_dict = data.model_dump(exclude_unset=True)
        update_dict["updated_at"] = self.datetime_util.get_current_time()
        updated = await self.repository.update_config(partner_id, update_dict)
        return self.__to_response(updated)

    async def get_webhook_config(
        self, partner_id: int
    ) -> TalkoContract.WebhookConfigResponse:
        config = await self.repository.find_config_by_partner_id(partner_id)
        if not config:
            raise TalkoResourceNotFound(PARTNER_WEBHOOK_CONFIG_NOT_FOUND)
        return self.__to_response(config)

    async def list_delivery_attempts(
        self, partner_id: int, limit: int = DEFAULT_DELIVERY_ATTEMPTS_LIMIT
    ) -> List[TalkoContract.DeliveryAttemptResponse]:
        attempts = await self.repository.find_delivery_attempts_by_partner_id(
            partner_id, limit
        )
        return [
            TalkoContract.DeliveryAttemptResponse(
                id=str(attempt["_id"]),
                partner_id=attempt["partner_id"],
                event_type=attempt["event_type"],
                event_id=attempt["event_id"],
                url=attempt["url"],
                attempt_number=attempt["attempt_number"],
                status_code=attempt.get("status_code"),
                success=attempt["success"],
                error=attempt.get("error"),
                duration_ms=attempt.get("duration_ms"),
                created_at=attempt["created_at"],
            )
            for attempt in attempts
        ]

    async def get_active_config_for_delivery(self, partner_id: int) -> Optional[dict]:
        config = await self.repository.find_config_by_partner_id(partner_id)
        if not config or not config.get("is_active"):
            return None
        return config

    async def deliver_event(
        self,
        partner_id: int,
        event_type: str,
        event_id: str,
        payload: Dict[str, Any],
        attempt_number: int,
    ) -> str:
        """Signs and POSTs one webhook event to a partner's configured URL.

        Pure async — intentionally has no asyncio.run() of its own, so it's
        directly unit-testable. The Celery task in tasks.py is a thin
        asyncio.run() wrapper around this method; see that module for why
        the split matters (calling a task's own asyncio.run() from a sync
        test corrupts the thread's event loop for later, unrelated tests).
        """
        config = await self.get_active_config_for_delivery(partner_id)
        if not config:
            self.logger.info(
                "No active webhook config for partner_id {}; skipping delivery".format(
                    partner_id
                )
            )
            return "no_active_config"

        if event_type not in config.get("subscribed_events", []):
            self.logger.info(
                "partner_id {} not subscribed to event_type {}; skipping".format(
                    partner_id, event_type
                )
            )
            return "not_subscribed"

        secret = self.cipher.decrypt(config["signing_secret_encrypted"])
        body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ts = int(time.time())
        signature = TalkoWebhookSigner.sign(secret, ts, body)

        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    config["url"],
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Talko-Signature": "t={},v1={}".format(ts, signature),
                        "X-Talko-Event-Id": event_id,
                        "X-Talko-Event-Type": event_type,
                    },
                )
                resp.raise_for_status()

            await self.log_delivery_attempt(
                partner_id=partner_id,
                event_type=event_type,
                event_id=event_id,
                url=config["url"],
                attempt_number=attempt_number,
                status_code=resp.status_code,
                success=True,
                error=None,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            self.logger.info(
                "Delivered webhook event {} to partner_id {}".format(
                    event_id, partner_id
                )
            )
            return "delivered"
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            await self.log_delivery_attempt(
                partner_id=partner_id,
                event_type=event_type,
                event_id=event_id,
                url=config["url"],
                attempt_number=attempt_number,
                status_code=status_code,
                success=False,
                error=str(exc),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            self.logger.error(
                "Webhook delivery failed for partner_id {} event {}: {}".format(
                    partner_id, event_id, exc
                )
            )
            raise

    async def log_delivery_attempt(
        self,
        partner_id: int,
        event_type: str,
        event_id: str,
        url: str,
        attempt_number: int,
        status_code: Optional[int],
        success: bool,
        error: Optional[str],
        duration_ms: Optional[int],
    ) -> None:
        now = self.datetime_util.get_current_time()
        await self.repository.insert_delivery_attempt(
            {
                "partner_id": partner_id,
                "event_type": event_type,
                "event_id": event_id,
                "url": url,
                "attempt_number": attempt_number,
                "status_code": status_code,
                "success": success,
                "error": error,
                "duration_ms": duration_ms,
                "created_at": now,
                "updated_at": now,
            }
        )

    def __to_response(self, config: dict) -> TalkoContract.WebhookConfigResponse:
        raw_secret = self.cipher.decrypt(config["signing_secret_encrypted"])
        return TalkoContract.WebhookConfigResponse(
            id=str(config["_id"]),
            partner_id=config["partner_id"],
            url=config["url"],
            is_active=config["is_active"],
            subscribed_events=config["subscribed_events"],
            signing_secret_last_4=raw_secret[-4:],
            created_at=config["created_at"],
            updated_at=config["updated_at"],
        )
