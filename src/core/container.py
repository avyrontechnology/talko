import httpx
from dependency_injector import containers, providers

from src.components.analytics.base import TalkoAnalyticsBase
from src.components.analytics.builder import TalkoQueryBuilder
from src.components.analytics.date_range_helper import TalkoDateRangeHelper
from src.components.analytics.processor import TalkoAnalyticsProcessor
from src.components.analytics.repositories import TalkoAnalyticsRepository
from src.components.analytics.services import TalkoAnalyticsService
from src.components.cache.helper import TalkoCacheHelper
from src.components.call_agent_map.repository import TalkoAgentMappingRepository
from src.components.call_agent_map.services import TalkoAgentMappingService
from src.components.call_agent_map.validation import TalkoAgentMapperValidator
from src.components.call_assets.helper import TalkoAssetsHelper
from src.components.call_assets.repository import TalkoAssetRepository
from src.components.call_assets.services import TalkoAssetService
from src.components.call_assets.update_recordings import TalkoRecordingsUpdateTask
from src.components.call_management.agent_dialplan_resolver import TalkoAgentDialPlanResolver
from src.components.call_management.redis_helper import TalkoCallRedisHelper
from src.components.call_management.repository import TalkoCallRepository
from src.components.call_management.services import TalkoCallService
from src.components.call_operation.cdr_update import TalkoCDRUpdateTask
from src.components.call_operation.vendor_cdr_gateway import TalkoVendorCDRGateway
from src.components.call_record.repositories import TalkoCallRecordRepository
from src.components.call_record.services import TalkoCallRecordService
from src.components.cdr.repository import TalkoCDRRepository
from src.components.cdr.services import TalkoCDRService
from src.components.common.user_hierarchy import TalkoUserHierarchy
from src.components.custom_field.repository import TalkoCustomFieldRepository
from src.components.custom_field.services import TalkoCustomFieldService
from src.components.custom_field.validation import TalkoCustomFieldValidator
from src.components.dialer.services import TalkoDialerService
from src.components.did_management.repositories import TalkoDidRepository
from src.components.did_management.services import TalkoDidManagementService
from src.components.did_management.validator import TalkoDidValidator
from src.components.digital_assets.repositories import TalkoDigitalAssetRepository
from src.components.digital_assets.services import TalkoDigitalAssetService
from src.components.email_service.services import TalkoEmailService
from src.components.inbound_call_events.connection_manager import TalkoInboundCallEventBroker
from src.components.inbound_call_events.publisher import TalkoInboundCallEventPublisher
from src.components.integrations.console.maglo_client import TalkoMagloClient
from src.components.partner_auth.rate_limiter import TalkoPartnerApiKeyRateLimiter
from src.components.partner_auth.repository import TalkoPartnerApiKeyRepository
from src.components.partner_auth.services import TalkoPartnerApiKeyService
from src.components.partner_auth.validation import TalkoPartnerApiKeyValidator
from src.components.user_auth.repository import TalkoUserRepository
from src.components.user_auth.services import TalkoUserAuthService
from src.components.partner_config.repository import TalkoPartnerConfigRepository
from src.components.partner_config.services import TalkoPartnerConfigService
from src.components.partner_config.validation import TalkoPartnerConfigValidator
from src.components.partner_webhook.crypto import TalkoWebhookSecretCipher
from src.components.partner_webhook.repository import TalkoPartnerWebhookRepository
from src.components.partner_webhook.services import TalkoPartnerWebhookService
from src.components.partner_webhook.validation import TalkoPartnerWebhookValidator
from src.components.pstn.services import TalkoPSTNBridgeService
from src.components.reports.daily_lead_report.lead_connection_service import (
    TalkoLeadConnectionReportService,
)
from src.components.vendor.repository import TalkoVendorRepository
from src.components.vendor.services import TalkoVendorService
from src.components.vendor.validation import TalkoVendorValidator
from src.components.vendor_config.repository import TalkoVendorConfigRepository
from src.components.vendor_config.services import TalkoVendorConfigService
from src.components.vendor_config.validation import TalkoVendorConfigValidator
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.core.environment import TalkoENV
from src.core.redis import TalkoRedisCache
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil
from src.components.call_management.agent_dialplan_resolver import TalkoAgentDialPlanResolver

logger = TalkoServiceLogger.get_logger()


class TalkoContainer(containers.DeclarativeContainer):

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
                "src.components.partner_auth.controllers",
                "src.components.partner_webhook.controllers",
                "src.components.user_auth.controllers",
            ]
        )

    wiring_config = __add_wiring()

    logger = providers.Singleton(TalkoServiceLogger)

    db = providers.Singleton(TalkoDocDatabaseSessionManager, logger=logger)

    email_service = providers.Singleton(
        TalkoEmailService,
        logger=logger,
        api_url=TalkoENV.MAILMG_API_URL,
        channel_key=TalkoENV.MAILMG_CHANNEL_KEY,
        sender_email=TalkoENV.MAILMG_CLIENT_NAME,
        template_env="",
    )

    redis_pool = providers.Resource(
        TalkoRedisCache.init_redis_pool,
    )

    cache_helper = providers.Singleton(
        TalkoCacheHelper,
        redis_pool=redis_pool,
        talko_service_logger=logger,
    )

    call_redis_helper = providers.Singleton(
        TalkoCallRedisHelper,
        logger=logger,
    )

    # grpc
    grpc_client = providers.Singleton(
        TalkoRPCServiceFactory.get_service,
        TalkoGrpcServices.AUTH,
    )

    # maglo client
    maglo_client = providers.Factory(
        TalkoMagloClient,
        logger=logger,
    )

    # analytics query builder
    analytics_query_builder = providers.Factory(TalkoQueryBuilder, logger=logger)

    # user hierarchy
    user_hierarchy = providers.Factory(
        TalkoUserHierarchy, grpc_client=grpc_client, logger=logger
    )

    # helper
    date_range_helper = providers.Factory(TalkoDateRangeHelper, logger=logger)

    # Repositories
    call_record_repo = providers.Factory(
        TalkoCallRecordRepository, session_factory=db, logger=logger
    )
    vendor_repo = providers.Factory(TalkoVendorRepository, session_factory=db, logger=logger)
    vendor_config_repo = providers.Factory(
        TalkoVendorConfigRepository, db_manager=db, logger=logger
    )
    partner_config_repo = providers.Factory(
        TalkoPartnerConfigRepository, db_manager=db, logger=logger
    )
    partner_api_key_repo = providers.Factory(
        TalkoPartnerApiKeyRepository, db_manager=db, logger=logger
    )
    talko_user_repo = providers.Factory(
        TalkoUserRepository, db_manager=db, logger=logger
    )
    user_auth_service = providers.Factory(
        TalkoUserAuthService, repository=talko_user_repo, logger=logger
    )
    partner_webhook_repo = providers.Factory(
        TalkoPartnerWebhookRepository, db_manager=db, logger=logger
    )
    cdr_repository = providers.Factory(TalkoCDRRepository, db_manager=db, logger=logger)
    custom_field_repository = providers.Factory(
        TalkoCustomFieldRepository, db_manager=db, logger=logger
    )
    call_repository = providers.Factory(TalkoCallRepository, db_manager=db, logger=logger)
    call_agent_mapping_repository = providers.Factory(
        TalkoAgentMappingRepository, db_manager=db, logger=logger
    )
    analytics_repositories = providers.Factory(
        TalkoAnalyticsRepository,
        db_manager=db,
        logger=logger,
        analytics_query_builder=analytics_query_builder,
    )
    did_repositories = providers.Factory(TalkoDidRepository, db_manager=db, logger=logger)
    assets_repository = providers.Factory(TalkoAssetRepository, db_manager=db, logger=logger)

    # validation
    did_validator = providers.Factory(
        TalkoDidValidator,
        vendor_config_repository=vendor_config_repo,
        partner_config_repository=partner_config_repo,
        logger=logger,
    )
    vendor_validator = providers.Factory(
        TalkoVendorValidator,
        repository=vendor_repo,
        logger=logger,
    )
    vendor_config_validator = providers.Factory(
        TalkoVendorConfigValidator,
        repository=vendor_repo,
        logger=logger,
        vendor_config_repository=vendor_config_repo,
    )
    partner_config_validator = providers.Factory(
        TalkoPartnerConfigValidator,
        logger=logger,
        partner_config_repository=partner_config_repo,
    )
    partner_api_key_validator = providers.Factory(
        TalkoPartnerApiKeyValidator, logger=logger, repository=partner_api_key_repo
    )
    partner_api_key_rate_limiter = providers.Factory(
        TalkoPartnerApiKeyRateLimiter, cache_helper=cache_helper, logger=logger
    )
    partner_webhook_validator = providers.Factory(
        TalkoPartnerWebhookValidator, logger=logger, repository=partner_webhook_repo
    )
    webhook_secret_cipher = providers.Singleton(
        TalkoWebhookSecretCipher, master_key=TalkoENV.WEBHOOK_SECRET_MASTER_KEY
    )
    call_agent_mapping_validation = providers.Factory(
        TalkoAgentMapperValidator, logger=logger, repository=call_agent_mapping_repository
    )
    custom_field_validator = providers.Factory(
        TalkoCustomFieldValidator,
        repository=custom_field_repository,
        logger=logger,
    )

    # processor
    analytics_processor = providers.Factory(
        TalkoAnalyticsProcessor,
        analytics_repository=analytics_repositories,
        logger=logger,
        grpc_client=grpc_client,
        user_hierarchy=user_hierarchy,
    )

    # base
    analytics_base = providers.Factory(
        TalkoAnalyticsBase, analytics_processor=analytics_processor, logger=logger
    )

    # Services
    did_service = providers.Factory(
        TalkoDidManagementService,
        did_repository=did_repositories,
        logger=logger,
        datetime_util=TalkoDateTimeUtil,
        validator=did_validator,
        partner_config_repository=partner_config_repo,
    )
    call_record_service = providers.Factory(
        TalkoCallRecordService,
        call_record_repo=call_record_repo,
        logger=logger,
    )
    vendor_service = providers.Factory(
        TalkoVendorService,
        vendor_repo=vendor_repo,
        logger=logger,
        datetime_util=TalkoDateTimeUtil,
        validator=vendor_validator,
    )
    vendor_config_service = providers.Factory(
        TalkoVendorConfigService,
        repository=vendor_config_repo,
        logger=logger,
        datetime_util=TalkoDateTimeUtil,
        validator=vendor_config_validator,
        did_management_service=did_service,
        vendor_repository=vendor_repo,
    )
    partner_config_service = providers.Factory(
        TalkoPartnerConfigService,
        repository=partner_config_repo,
        logger=logger,
        datetime_util=TalkoDateTimeUtil,
        validator=vendor_validator,
        vendor_config_service=vendor_config_service,
        vendor_config_validator=vendor_config_validator,
        vendor_config_repository=vendor_config_repo,
        partner_config_validator=partner_config_validator,
        did_management_service=did_service,
    )
    partner_api_key_service = providers.Factory(
        TalkoPartnerApiKeyService,
        repository=partner_api_key_repo,
        validator=partner_api_key_validator,
        rate_limiter=partner_api_key_rate_limiter,
        logger=logger,
        datetime_util=TalkoDateTimeUtil,
    )
    partner_webhook_service = providers.Factory(
        TalkoPartnerWebhookService,
        repository=partner_webhook_repo,
        validator=partner_webhook_validator,
        cipher=webhook_secret_cipher,
        logger=logger,
        datetime_util=TalkoDateTimeUtil,
    )
    custom_field_service = providers.Factory(
        TalkoCustomFieldService,
        repository=custom_field_repository,
        logger=logger,
        datetime_util=TalkoDateTimeUtil,
        validator=custom_field_validator,
    )
    cdr_config_service = providers.Factory(
        TalkoCDRService,
        repository=cdr_repository,
        logger=logger,
        datetime_util=TalkoDateTimeUtil,
        analytics_processor=analytics_processor,
        date_range_helper=date_range_helper,
        did_repository=did_repositories,
        custom_field_validator=custom_field_validator,
    )
    call_agent_mapping_service = providers.Factory(
        TalkoAgentMappingService,
        repository=call_agent_mapping_repository,
        logger=logger,
        datetime_util=TalkoDateTimeUtil,
        partner_config_repository=partner_config_repo,
        validation=call_agent_mapping_validation,
    )

    # TalkoCDR UPDATE TASK
    cdr_update_task = providers.Factory(
        TalkoCDRUpdateTask,
        cdr_repository=cdr_repository,
        vendor_config_repository=vendor_config_repo,
        call_repository=call_repository,
        logger=logger,
    )

    # TalkoCDR GATEWAY
    vendor_cdr_gateway = providers.Factory(
        TalkoVendorCDRGateway,
        cdr_update_task=cdr_update_task,
        logger=logger,
    )

    # INBOUND CALL EVENTS (websocket: partner_id, service_board_id, dedicated_did, agent_id)
    # Redis-backed fanout — see TalkoInboundCallEventBroker's docstring for why this pod
    # needs to hear about events published from other pods.
    inbound_call_event_broker = providers.Singleton(
        TalkoInboundCallEventBroker,
        redis_pool=redis_pool,
        logger=logger,
    )
    inbound_call_event_publisher = providers.Factory(
        TalkoInboundCallEventPublisher,
        broker=inbound_call_event_broker,
        logger=logger,
    )

    # CALL SERVICE
    call_service = providers.Factory(
        TalkoCallService,
        repository=call_repository,
        logger=logger,
        datetime_util=TalkoDateTimeUtil,
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
        TalkoAnalyticsService, analytics_base=analytics_base, logger=logger
    )
    dialer_service = providers.Factory(
        TalkoDialerService,
        partner_config_repository=partner_config_repo,
        vendor_config_repository=vendor_config_repo,
        logger=logger,
    )

    lead_connection_report_service = providers.Factory(
        TalkoLeadConnectionReportService,
        maglo_client=maglo_client,
        db=db,
        logger=logger,
    )

    call_assets_helper = providers.Factory(TalkoAssetsHelper, logger=logger)

    save_and_update_unsaved_recorings_task = providers.Factory(
        TalkoRecordingsUpdateTask,
        logger=logger,
        cdr_repository=cdr_repository,
        call_repository=call_repository,
        assets_repository=assets_repository,
        assets_helper=call_assets_helper,
    )

    assets_service = providers.Factory(
        TalkoAssetService, repository=assets_repository, logger=logger
    )

    digital_asset_repository = providers.Factory(
        TalkoDigitalAssetRepository,
        session_factory=db.provided.session,
    )

    digital_asset_service = providers.Factory(
        TalkoDigitalAssetService,
        digital_asset_repository=digital_asset_repository,
    )

    recordings_task = providers.Factory(
        TalkoRecordingsUpdateTask,
        logger=logger,
        cdr_repository=cdr_repository,
        call_repository=call_repository,
        assets_repository=assets_repository,
        assets_helper=call_assets_helper,
    )

    agent_dialplan_resolver = providers.Factory(
        TalkoAgentDialPlanResolver,
        maglo_client=maglo_client,
        agent_mapping_repo=call_agent_mapping_repository,
        logger=logger,
    )
    http_client = providers.Singleton(
        httpx.AsyncClient,
    )

    pstn_bridge_service = providers.Factory(
        TalkoPSTNBridgeService,
        did_repository=did_repositories,
        logger=logger,
        http_client=http_client,
        call_redis_helper=call_redis_helper,
        call_repository=call_repository,
    )
