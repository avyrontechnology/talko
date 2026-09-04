from fastapi import APIRouter

from src.components.analytics.controllers import AnalyticsController
from src.components.call_agent_map.controllers import CallAgentMappingController
from src.components.call_assets.controllers import AssetsController
from src.components.call_management.controllers import CallController
from src.components.call_record.controllers import CallRecordController
from src.components.cdr.controllers import CDRController
from src.components.custom_field.controllers import CustomFieldController
from src.components.dialer.controllers import DialerController
from src.components.did_management.controllers import DIDController
from src.components.digital_assets.controllers import DigitalAssetController
from src.components.health.controllers import HealthController
from src.components.inbound_call_events.controllers import InboundCallEventController
from src.components.partner_config.controllers import PartnerConfigController
from src.components.pstn.controllers import PSTNAgentController
from src.components.reports.daily_lead_report.daily_lead_connection import (
    router as daily_lead_connection_router,
)
from src.components.vendor.controllers import VendorController
from src.components.vendor_config.controllers import VendorConfigController


class Router:
    @staticmethod
    def register_all_routes(router: APIRouter):
        """register all routers here."""
        router.include_router(
            CallRecordController.call_record_router, prefix="", tags=["Call Record"]
        ),
        router.include_router(
            VendorController.vendor_router, prefix="/vendors", tags=["Vendor"]
        )
        router.include_router(
            VendorConfigController.vendor_config_router,
            prefix="/vendor_configs",
            tags=["Vendor Config"],
        )
        router.include_router(
            PartnerConfigController.router,
            prefix="/partner_configs",
            tags=["Partner Config"],
        )
        router.include_router(CallController.call_router, prefix="/call", tags=["Call"])
        router.include_router(CDRController.cdr_router, prefix="/cdrs", tags=["CDR"])
        router.include_router(
            CustomFieldController.custom_field_router,
            prefix="/custom-fields",
            tags=["Custom Fields"],
        )
        router.include_router(
            CallAgentMappingController.router,
            prefix="/call_agent_mapping",
            tags=["Call Agent Mapping"],
        )
        router.include_router(
            AnalyticsController.router,
            prefix="/get-analytics",
            tags=["Analytics"],
        )
        router.include_router(
            DIDController.did_router,
            prefix="/dids",
            tags=["DID"],
        )

        router.include_router(
            DigitalAssetController.digital_asset_router,
            prefix="",
            tags=["Digital Assets"],
        )

        router.include_router(
            AssetsController.callassets,
            prefix="/assets",
            tags=["Call Assets"],
        )
        router.include_router(
            DialerController.dialer_router,
            prefix="/dialer",
            tags=["Dialer"],
        )
        router.include_router(
            daily_lead_connection_router,
        )
        router.include_router(
            HealthController.router,
            prefix="/health",
        )
        router.include_router(
            PSTNAgentController.router,
            prefix="/pstn",
            tags=["PSTN Agent"],
        )
        router.include_router(
            InboundCallEventController.router,
            prefix="",
            tags=["Inbound Call Events"],
        )
