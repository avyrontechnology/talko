from typing import Any

from src.components.call_management.constant import OTOBA_CDR_FIELD_MAPPING
from src.components.call_management.tata_tele.call_webhook import (
    TalkoTataTeleWebhookHandler,
)


class TalkoOtobaWebhookHandler(TalkoTataTeleWebhookHandler):
    """OTOBA CDR relay handler.

    Normalizes OTOBA API payload key variants to the Tata-equivalent keys,
    then delegates to the shared Tata _process_payload logic so CDR update,
    entity preservation, and makun-ai relay behave identically across vendors.

    An optional ``field_map`` (OTOBA key -> TalkoCDR field) from the vendor
    config ``cdr_url_handler`` is applied first and wins over the defaults.
    """

    def __init__(
        self,
        logger: Any,
        call_repository: Any,
        vendor_type: str = "otoba",
        call_redis_helper: Any = None,
        field_map: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            logger=logger,
            call_repository=call_repository,
            vendor_type=vendor_type,
            call_redis_helper=call_redis_helper,
        )
        self.field_map: dict[str, str] = field_map or {}

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Unwrap common envelope shapes first.
        for wrapper in ("results", "data", "cdr", "call"):
            inner = payload.get(wrapper)
            if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                return self.normalize(inner[0])
            if isinstance(inner, dict):
                return self.normalize(inner)
        normalized: dict[str, Any] = dict(payload)
        for src_key, db_field in OTOBA_CDR_FIELD_MAPPING.items():
            if src_key in payload and payload[src_key] is not None:
                normalized[db_field] = payload[src_key]
        for src_key, db_field in self.field_map.items():
            if src_key in payload and payload[src_key] is not None:
                normalized[db_field] = payload[src_key]
        # Tata core expects these identifier keys.
        if normalized.get("call_id") is None and payload.get("callId"):
            normalized["call_id"] = payload.get("callId")
        return normalized

    async def process_cdr_api_payload(
        self,
        payload: dict[str, Any],
        call_id: str | None = None,
        uuid: str | None = None,
    ) -> dict[str, str]:
        return await super().process_cdr_api_payload(self.normalize(payload or {}), call_id, uuid)

    async def process_webhook(self, payload: dict[str, Any]) -> dict[str, str]:
        return await super().process_webhook(self.normalize(payload or {}))
