from fastapi import APIRouter

from src.components.analytics.controllers import TalkoAnalyticsController
from src.components.call_agent_map.controllers import TalkoCallAgentMappingController
from src.components.call_assets.controllers import TalkoAssetsController
from src.components.call_management.controllers import TalkoCallController
from src.components.call_record.controllers import TalkoCallRecordController
from src.components.cdr.controllers import TalkoCDRController
from src.components.custom_field.controllers import TalkoCustomFieldController
from src.components.dialer.controllers import TalkoDialerController
from src.components.did_management.controllers import TalkoDIDController
from src.components.digital_assets.controllers import TalkoDigitalAssetController
from src.components.health.controllers import TalkoHealthController
from src.components.inbound_call_events.controllers import TalkoInboundCallEventController
from src.components.partner_auth.controllers import TalkoPartnerApiKeyController
from src.components.partner_config.controllers import TalkoPartnerConfigController
from src.components.partner_webhook.controllers import TalkoPartnerWebhookController
from src.components.pstn.controllers import TalkoPSTNAgentController
from src.components.reports.daily_lead_report.daily_lead_connection import (
    router as daily_lead_connection_router,
)
from src.components.vendor.controllers import TalkoVendorController
from src.components.vendor_config.controllers import TalkoVendorConfigController


class TalkoRouter:
    @staticmethod
    def register_all_routes(router: APIRouter):
        """register all routers here."""
        router.include_router(
            TalkoCallRecordController.call_record_router, prefix="", tags=["Call Record"]
        ),
        router.include_router(
            TalkoVendorController.vendor_router, prefix="/vendors", tags=["Vendor"]
        )
        router.include_router(
            TalkoVendorConfigController.vendor_config_router,
            prefix="/vendor_configs",
            tags=["Vendor Config"],
        )
        router.include_router(
            TalkoPartnerConfigController.router,
            prefix="/partner_configs",
            tags=["Partner Config"],
        )
        router.include_router(TalkoCallController.call_router, prefix="/call", tags=["Call"])
        router.include_router(TalkoCDRController.cdr_router, prefix="/cdrs", tags=["TalkoCDR"])
        router.include_router(
            TalkoCustomFieldController.custom_field_router,
            prefix="/custom-fields",
            tags=["Custom Fields"],
        )
        router.include_router(
            TalkoCallAgentMappingController.router,
            prefix="/call_agent_mapping",
            tags=["Call Agent Mapping"],
        )
        router.include_router(
            TalkoAnalyticsController.router,
            prefix="/get-analytics",
            tags=["Analytics"],
        )
        router.include_router(
            TalkoDIDController.did_router,
            prefix="/dids",
            tags=["DID"],
        )

        router.include_router(
            TalkoDigitalAssetController.digital_asset_router,
            prefix="",
            tags=["Digital Assets"],
        )

        router.include_router(
            TalkoAssetsController.callassets,
            prefix="/assets",
            tags=["Call Assets"],
        )
        router.include_router(
            TalkoDialerController.dialer_router,
            prefix="/dialer",
            tags=["Dialer"],
        )
        router.include_router(
            daily_lead_connection_router,
        )
        router.include_router(
            TalkoHealthController.router,
            prefix="/health",
        )
        router.include_router(
            TalkoPSTNAgentController.router,
            prefix="/pstn",
            tags=["PSTN Agent"],
        )
        router.include_router(
            TalkoInboundCallEventController.router,
            prefix="",
            tags=["Inbound Call Events"],
        )
        router.include_router(
            TalkoPartnerApiKeyController.router,
            prefix="/partner_api_keys",
            tags=["Partner API Keys"],
        )
        router.include_router(
            TalkoPartnerWebhookController.router,
            prefix="/partner_webhooks",
            tags=["Partner Webhooks"],
        )
