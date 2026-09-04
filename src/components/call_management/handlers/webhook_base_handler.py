from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx

from src.components.call_assets.repository import TalkoAssetRepository
from src.components.call_management.repository import TalkoCallRepository
from src.core.environment import TalkoENV
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil

_MAKUNAI_RELAY_TIMEOUT_SECONDS = 5.0


class TalkoWebhookHandler(ABC):
    """
    Abstract base class for webhook and API payload handlers.
    """

    def __init__(
        self,
        logger: TalkoServiceLogger,
        call_repository: TalkoCallRepository,
        vendor_type: str,
    ):
        """
        Initialize the handler with dependencies.

        Args:
            logger: TalkoServiceLogger instance for logging.
            call_repository: Repository for TalkoCDR operations.
            datetime_util: Utility for timestamp conversions.
            vendor_type: Identifier for the vendor (e.g., 'tata_tele').
        """
        self.logger: TalkoServiceLogger = logger
        self.call_repository: TalkoCallRepository = call_repository
        self.datetime_util: TalkoDateTimeUtil = TalkoDateTimeUtil()
        self.vendor_type: str = vendor_type

    @abstractmethod
    async def process_webhook(self, payload: Dict) -> Dict:
        """
        Process a webhook payload and update the TalkoCDR.

        Args:
            payload: Webhook data from the vendor.

        Returns:
            Dict: Status response.

        Raises:
            TalkoBadRequestError: If required fields are missing or update fails.
            TalkoResourceNotFound: If the TalkoCDR is not found.
        """
        pass

    @abstractmethod
    async def process_cdr_api_payload(
        self, payload: Dict, call_id: Optional[str] = None, uuid: Optional[str] = None
    ) -> Dict:
        """
        Process a TalkoCDR API payload and update the TalkoCDR.

        Args:
            payload: API response data from the vendor.
            call_id: Call ID for the TalkoCDR (optional).
            uuid: UUID for the TalkoCDR (optional).

        Returns:
            Dict: Status response.

        Raises:
            TalkoBadRequestError: If required fields are missing or update fails.
            TalkoResourceNotFound: If the TalkoCDR is not found.
        """
        pass

    async def _relay_to_makunai(self, partner_id: int, payload: Dict[str, Any]) -> None:
        """
        Forwards a Tata webhook payload to makun-ai's campaign webhook
        verbatim, plus partner_id. Shared by both webhook handler types —
        AI-bridge/campaign calls (our own click-to-call flow) complete via
        Tata's STANDARD call webhook (TalkoTataTeleWebhookHandler, type=standard),
        not the Dialer product webhook (TalkoDialerWebhookHandler, type=dialer,
        an entirely different Tata Tele feature we don't use for campaigns).
        Both need this relay for makun-ai to ever hear about call completion.

        Best-effort: makun-ai only cares about AI-agent-DID campaign calls,
        so a huge fraction of webhooks legitimately have nothing for it to
        do there (Section 16.4) — and our own TalkoCDR write already succeeded
        by the time this runs, so a relay failure here must never surface
        as a failure of the Tata webhook itself.
        """
        relay_payload = {**payload, "partner_id": partner_id}
        try:
            async with httpx.AsyncClient(
                timeout=_MAKUNAI_RELAY_TIMEOUT_SECONDS
            ) as client:
                resp = await client.post(
                    TalkoENV.MAKUNAI_CDR_WEBHOOK_URL,
                    json=relay_payload,
                    headers={"X-Webhook-Secret": TalkoENV.CDR_WEBHOOK_RELAY_SECRET},
                )
                resp.raise_for_status()
            self.logger.debug(
                "[TalkoWebhookHandler] Relayed to makun-ai partner_id={} call_id={}".format(
                    partner_id, payload.get("call_id")
                )
            )
        except Exception as exc:
            self.logger.error(
                "[TalkoWebhookHandler] Failed to relay to makun-ai partner_id={} "
                "call_id={}: {}".format(partner_id, payload.get("call_id"), exc)
            )
