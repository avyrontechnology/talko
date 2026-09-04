import httpx
from dependency_injector import containers, providers

from src.components.analytics.base import AnalyticsBase
from src.components.analytics.builder import QueryBuilder
from src.components.analytics.date_range_helper import DateRangeHelper
from src.components.analytics.processor import AnalyticsProcessor
from src.components.analytics.repositories import AnalyticsRepository
from src.components.analytics.services import AnalyticsService
from src.components.cache.helper import CacheHelper
from src.components.call_agent_map.repository import AgentMappingRepository
from src.components.call_agent_map.services import AgentMappingService
from src.components.call_agent_map.validation import AgentMapperValidator
from src.components.call_assets.helper import AssetsHelper
from src.components.call_assets.repository import AssetRepository
from src.components.call_assets.services import AssetService
from src.components.call_assets.update_recordings import RecordingsUpdateTask
from src.components.call_management.agent_dialplan_resolver import AgentDialPlanResolver
from src.components.call_management.redis_helper import CallRedisHelper
from src.components.call_management.repository import CallRepository
from src.components.call_management.services import CallService
from src.components.call_operation.cdr_update import CDRUpdateTask
from src.components.call_operation.vendor_cdr_gateway import VendorCDRGateway
from src.components.call_record.repositories import CallRecordRepository
from src.components.call_record.services import CallRecordService
from src.components.cdr.repository import CDRRepository
from src.components.cdr.services import CDRService
from src.components.common.user_hierarchy import UserHierarchy
from src.components.custom_field.repository import CustomFieldRepository
from src.components.custom_field.services import CustomFieldService
from src.components.custom_field.validation import CustomFieldValidator
from src.components.dialer.services import DialerService
from src.components.did_management.repositories import DidRepository
from src.components.did_management.services import DidManagementService
from src.components.did_management.validator import DidValidator
from src.components.digital_assets.repositories import DigitalAssetRepository
from src.components.digital_assets.services import DigitalAssetService
from src.components.email_service.services import EmailService
from src.components.inbound_call_events.connection_manager import InboundCallEventBroker
from src.components.inbound_call_events.publisher import InboundCallEventPublisher
from src.components.integrations.console.maglo_client import MagloClient
from src.components.partner_config.repository import PartnerConfigRepository
from src.components.partner_config.services import PartnerConfigService
from src.components.partner_config.validation import PartnerConfigValidator
from src.components.pstn.services import PSTNBridgeService
from src.components.reports.daily_lead_report.lead_connection_service import (
    LeadConnectionReportService,
)
from src.components.vendor.repository import VendorRepository
from src.components.vendor.services import VendorService
from src.components.vendor.validation import VendorValidator
from src.components.vendor_config.repository import VendorConfigRepository
from src.components.vendor_config.services import VendorConfigService
from src.components.vendor_config.validation import VendorConfigValidator
from src.core.doc_db import DocDatabaseSessionManager
from src.core.environment import ENV
from src.core.redis import RedisCache
from src.grpc_client.constants import GrpcServices
from src.grpc_client.rpc_service_factory import RPCServiceFactory
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.datetime_util import DateTimeUtil
from src.components.call_management.agent_dialplan_resolver import AgentDialPlanResolver

logger = HollerServiceLogger.get_logger()


class Container(containers.DeclarativeContainer):

    @staticmethod
    def __add_wiring():
        return containers.WiringConfiguration(
            modules=[
                "..middlewares.allowed_host",
                "..middlewares.authentication",
                "..middlewares.logging_request_and_response",
                "src.components.health.controllers",
                "src.components.call_record.controllers",
                "src.components.call_record.repositories",
                "src.components.vendor.controllers",
                "src.components.vendor_config.controllers",
                "src.components.partner_config.controllers",
                "src.components.cdr.controllers",
                "src.components.custom_field.controllers",
                "src.components.call_management.controllers",
                "src.components.call_agent_map.controllers",
                "src.components.analytics.controllers",
                "src.components.did_management.controllers",
                "src.components.call_assets.controllers",
                "src.components.dialer.controllers",
                "src.components.pstn.controllers",
                "src.components.inbound_call_events.controllers",
            ]
        )

    wiring_config = __add_wiring()

    logger = providers.Singleton(HollerServiceLogger)

    db = providers.Singleton(DocDatabaseSessionManager, logger=logger)

    email_service = providers.Singleton(
        EmailService,
        logger=logger,
        api_url=ENV.MAILMG_API_URL,
        channel_key=ENV.MAILMG_CHANNEL_KEY,
        sender_email=ENV.MAILMG_CLIENT_NAME,
        template_env="",
    )

    redis_pool = providers.Resource(
        RedisCache.init_redis_pool,
    )

    cache_helper = providers.Singleton(
        CacheHelper,
        redis_pool=redis_pool,
        holler_service_logger=logger,
    )

    call_redis_helper = providers.Singleton(
        CallRedisHelper,
        logger=logger,
    )

    # grpc
    grpc_client = providers.Singleton(
        RPCServiceFactory.get_service,
        GrpcServices.AUTH,
    )

    # maglo client
    maglo_client = providers.Factory(
        MagloClient,
        logger=logger,
    )

    # analytics query builder
    analytics_query_builder = providers.Factory(QueryBuilder, logger=logger)

    # user hierarchy
    user_hierarchy = providers.Factory(
        UserHierarchy, grpc_client=grpc_client, logger=logger
    )

    # helper
    date_range_helper = providers.Factory(DateRangeHelper, logger=logger)

    # Repositories
    call_record_repo = providers.Factory(
        CallRecordRepository, session_factory=db, logger=logger
    )
    vendor_repo = providers.Factory(VendorRepository, session_factory=db, logger=logger)
    vendor_config_repo = providers.Factory(
        VendorConfigRepository, db_manager=db, logger=logger
    )
    partner_config_repo = providers.Factory(
        PartnerConfigRepository, db_manager=db, logger=logger
    )
    cdr_repository = providers.Factory(CDRRepository, db_manager=db, logger=logger)
    custom_field_repository = providers.Factory(
        CustomFieldRepository, db_manager=db, logger=logger
    )
    call_repository = providers.Factory(CallRepository, db_manager=db, logger=logger)
    call_agent_mapping_repository = providers.Factory(
        AgentMappingRepository, db_manager=db, logger=logger
    )
    analytics_repositories = providers.Factory(
        AnalyticsRepository,
        db_manager=db,
        logger=logger,
        analytics_query_builder=analytics_query_builder,
    )
    did_repositories = providers.Factory(DidRepository, db_manager=db, logger=logger)
    assets_repository = providers.Factory(AssetRepository, db_manager=db, logger=logger)

    # validation
    did_validator = providers.Factory(
        DidValidator,
        vendor_config_repository=vendor_config_repo,
        partner_config_repository=partner_config_repo,
        logger=logger,
    )
    vendor_validator = providers.Factory(
        VendorValidator,
        repository=vendor_repo,
        logger=logger,
    )
    vendor_config_validator = providers.Factory(
        VendorConfigValidator,
        repository=vendor_repo,
        logger=logger,
        vendor_config_repository=vendor_config_repo,
    )
    partner_config_validator = providers.Factory(
        PartnerConfigValidator,
        logger=logger,
        partner_config_repository=partner_config_repo,
    )
    call_agent_mapping_validation = providers.Factory(
        AgentMapperValidator, logger=logger, repository=call_agent_mapping_repository
    )
    custom_field_validator = providers.Factory(
        CustomFieldValidator,
        repository=custom_field_repository,
        logger=logger,
    )

    # processor
    analytics_processor = providers.Factory(
        AnalyticsProcessor,
        analytics_repository=analytics_repositories,
        logger=logger,
        grpc_client=grpc_client,
        user_hierarchy=user_hierarchy,
    )

    # base
    analytics_base = providers.Factory(
        AnalyticsBase, analytics_processor=analytics_processor, logger=logger
    )

    # Services
    did_service = providers.Factory(
        DidManagementService,
        did_repository=did_repositories,
        logger=logger,
        datetime_util=DateTimeUtil,
        validator=did_validator,
        partner_config_repository=partner_config_repo,
    )
    call_record_service = providers.Factory(
        CallRecordService,
        call_record_repo=call_record_repo,
        logger=logger,
    )
    vendor_service = providers.Factory(
        VendorService,
        vendor_repo=vendor_repo,
        logger=logger,
        datetime_util=DateTimeUtil,
        validator=vendor_validator,
    )
    vendor_config_service = providers.Factory(
        VendorConfigService,
        repository=vendor_config_repo,
        logger=logger,
        datetime_util=DateTimeUtil,
        validator=vendor_config_validator,
        did_management_service=did_service,
        vendor_repository=vendor_repo,
    )
    partner_config_service = providers.Factory(
        PartnerConfigService,
        repository=partner_config_repo,
        logger=logger,
        datetime_util=DateTimeUtil,
        validator=vendor_validator,
        vendor_config_service=vendor_config_service,
        vendor_config_validator=vendor_config_validator,
        vendor_config_repository=vendor_config_repo,
        partner_config_validator=partner_config_validator,
        did_management_service=did_service,
    )
    custom_field_service = providers.Factory(
        CustomFieldService,
        repository=custom_field_repository,
        logger=logger,
        datetime_util=DateTimeUtil,
        validator=custom_field_validator,
    )
    cdr_config_service = providers.Factory(
        CDRService,
        repository=cdr_repository,
        logger=logger,
        datetime_util=DateTimeUtil,
        analytics_processor=analytics_processor,
        date_range_helper=date_range_helper,
        did_repository=did_repositories,
        custom_field_validator=custom_field_validator,
    )
    call_agent_mapping_service = providers.Factory(
        AgentMappingService,
        repository=call_agent_mapping_repository,
        logger=logger,
        datetime_util=DateTimeUtil,
        partner_config_repository=partner_config_repo,
        validation=call_agent_mapping_validation,
    )

    # CDR UPDATE TASK
    cdr_update_task = providers.Factory(
        CDRUpdateTask,
        cdr_repository=cdr_repository,
        vendor_config_repository=vendor_config_repo,
        call_repository=call_repository,
        logger=logger,
    )

    # CDR GATEWAY
    vendor_cdr_gateway = providers.Factory(
        VendorCDRGateway,
        cdr_update_task=cdr_update_task,
        logger=logger,
    )

    # INBOUND CALL EVENTS (websocket: partner_id, service_board_id, dedicated_did, agent_id)
    # Redis-backed fanout — see InboundCallEventBroker's docstring for why this pod
    # needs to hear about events published from other pods.
    inbound_call_event_broker = providers.Singleton(
        InboundCallEventBroker,
        redis_pool=redis_pool,
        logger=logger,
    )
    inbound_call_event_publisher = providers.Factory(
        InboundCallEventPublisher,
        broker=inbound_call_event_broker,
        logger=logger,
    )

    # CALL SERVICE
    call_service = providers.Factory(
        CallService,
        repository=call_repository,
        logger=logger,
        datetime_util=DateTimeUtil,
        partner_config_repository=partner_config_repo,
        vendor_config_repository=vendor_config_repo,
        agent_mapping_service=call_agent_mapping_service,
        agent_mapping_repository=call_agent_mapping_repository,
        did_management_service=did_service,
        cdr_update_task=cdr_update_task,
        vendor_cdr_gateway=vendor_cdr_gateway,
        cdr_repository=cdr_repository,
        call_redis_helper=call_redis_helper,
        did_repository=did_repositories,
        inbound_call_event_publisher=inbound_call_event_publisher,
    )

    analytics_service = providers.Factory(
        AnalyticsService, analytics_base=analytics_base, logger=logger
    )
    dialer_service = providers.Factory(
        DialerService,
        partner_config_repository=partner_config_repo,
        vendor_config_repository=vendor_config_repo,
        logger=logger,
    )

    lead_connection_report_service = providers.Factory(
        LeadConnectionReportService,
        maglo_client=maglo_client,
        db=db,
        logger=logger,
    )

    call_assets_helper = providers.Factory(AssetsHelper, logger=logger)

    save_and_update_unsaved_recorings_task = providers.Factory(
        RecordingsUpdateTask,
        logger=logger,
        cdr_repository=cdr_repository,
        call_repository=call_repository,
        assets_repository=assets_repository,
        assets_helper=call_assets_helper,
    )

    assets_service = providers.Factory(
        AssetService, repository=assets_repository, logger=logger
    )

    digital_asset_repository = providers.Factory(
        DigitalAssetRepository,
        session_factory=db.provided.session,
    )

    digital_asset_service = providers.Factory(
        DigitalAssetService,
        digital_asset_repository=digital_asset_repository,
    )

    recordings_task = providers.Factory(
        RecordingsUpdateTask,
        logger=logger,
        cdr_repository=cdr_repository,
        call_repository=call_repository,
        assets_repository=assets_repository,
        assets_helper=call_assets_helper,
    )

    agent_dialplan_resolver = providers.Factory(
        AgentDialPlanResolver,
        maglo_client=maglo_client,
        agent_mapping_repo=call_agent_mapping_repository,
        logger=logger,
    )
    http_client = providers.Singleton(
        httpx.AsyncClient,
    )

    pstn_bridge_service = providers.Factory(
        PSTNBridgeService,
        did_repository=did_repositories,
        logger=logger,
        http_client=http_client,
        call_redis_helper=call_redis_helper,
        call_repository=call_repository,
    )
