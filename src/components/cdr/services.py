import asyncio
from typing import Any, Dict, List, Optional, Union

from src.components.analytics.date_range_helper import TalkoDateRangeHelper
from src.components.analytics.processor import TalkoAnalyticsProcessor
from src.components.call_assets.helper import TalkoAssetsHelper
from src.components.cdr.constants import TalkoEntityType
from src.components.cdr.dto import TalkoContract
from src.components.cdr.helper import (
    TalkoCallLogQueryHelper,
    TalkoCommonCDRHelper,
    TalkoGetAgentCallLogsHelper,
    TalkoGetCallRecordHistoryHelper,
    TalkoGetCDRsHelper,
)
from src.components.cdr.messages import CDR_NOT_FOUND_FOR_CALL_ID
from src.components.cdr.repository import TalkoCDRRepository
from src.components.custom_field.constants import TalkoCustomFieldEntityType
from src.components.custom_field.validation import TalkoCustomFieldValidator
from src.components.did_management.repositories import TalkoDidRepository
from src.exceptions import TalkoResourceNotFound
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil
from src.utils.enums import TalkoTimeFilter, TalkoUserRoleHierarchy


class TalkoCDRService:
    """
    Service to handle Call Detail Record (TalkoCDR) operations.
    """

    def __init__(
        self,
        repository: TalkoCDRRepository,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
        analytics_processor: TalkoAnalyticsProcessor,
        date_range_helper: TalkoDateRangeHelper,
        did_repository: TalkoDidRepository,
        custom_field_validator: TalkoCustomFieldValidator,
    ):
        """
        Initialize TalkoCDRService with repository, logger, and datetime utility.
        """
        self.__repository: TalkoCDRRepository = repository
        self.__logger: TalkoServiceLogger = logger
        self.__datetime_util: TalkoDateTimeUtil = datetime_util
        self.__analytics_processor: TalkoAnalyticsProcessor = analytics_processor
        self.__date_range_helper: TalkoDateRangeHelper = date_range_helper
        self.__asset_helper: TalkoAssetsHelper = TalkoAssetsHelper(self.__logger)
        self.__did_repository: TalkoDidRepository = did_repository
        self.__custom_field_validator: TalkoCustomFieldValidator = custom_field_validator

    async def get_cdrs(
        self, user_id: int, partner_id: int, limit: int, offset: int
    ) -> list[TalkoContract.CDRResponse]:
        """
        Fetch CDRs by partner ID.

        Args:
            user_id (int): Requesting user's ID.
            partner_id (int): Partner ID for TalkoCDR fetch.

        Returns:
            list[TalkoContract.CDRResponse]: List of CDRs.
        """
        try:
            self.__logger.info(
                "User: {}, partner: {}, get cdrs service methods started.".format(
                    user_id, partner_id
                )
            )
            cdrs: Optional[dict] = (
                await self.__repository.find_all_cdrs_on_the_basis_of_partner_id(
                    partner_id, limit, offset
                )
            )
            self.__logger.debug(
                "User: {}, get cdr data on the basis of partner id. data: {}".format(
                    user_id, cdrs
                )
            )
            cdr_responses = TalkoGetCDRsHelper.process_cdrs(cdrs, self.__logger)

            self.__logger.info(
                "Get all cdrs on the basis of partner id fetched all data successfully."
            )

            return cdr_responses
        except Exception as e:
            self.__logger.error("Failed to retrieve CDRs: {}.".format(str(e)))
            raise

    async def get_agent_call_logs(
        self,
        user_id: int,
        partner_id: int,
        limit: int,
        offset: int,
        lead_id: Optional[Union[int, List[int]]] = None,
        created_at: Optional[int] = None,
        filter_by: Optional[TalkoTimeFilter] = None,
        is_masking_enabled: Optional[bool] = True,
        entity_type: Optional[str] = None,
        entity_id: Optional[Union[int, List[int]]] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
    ) -> TalkoContract.AgentCallLogResponse:
        try:
            self.__logger.info(
                "User: {}, partner: {}, get agent call logs service started.".format(
                    user_id, partner_id
                )
            )

            normalized_entity_type = entity_type
            normalized_entity_id = entity_id

            if (
                normalized_entity_type is None
                and normalized_entity_id is None
                and lead_id is not None
            ):
                normalized_entity_type = TalkoEntityType.LEAD.value
                normalized_entity_id = lead_id

            derived_lead_id = (
                normalized_entity_id
                if normalized_entity_type == TalkoEntityType.LEAD.value
                else None
            )

            self.__logger.debug(
                "Call log filters - lead_id: {}, entity_type: {}, entity_id: {}, created_at: {}, filter_by: {}, partner_id: {}".format(
                    derived_lead_id,
                    normalized_entity_type,
                    normalized_entity_id,
                    created_at,
                    filter_by,
                    partner_id,
                )
            )

            query = TalkoCallLogQueryHelper.build_call_log_query(
                lead_id=derived_lead_id,
                created_at=created_at,
                filter_by=filter_by,
                logger=self.__logger,
                partner_id=partner_id,
                entity_type=normalized_entity_type,
                entity_id=normalized_entity_id,
                custom_fields=custom_fields,
            )
            self.__logger.debug(
                "Get agent call logs service constructed query: {}".format(query)
            )
            cdrs: Optional[dict] = {}
            total_count: int = 0
            cdrs, total_count = (
                await self.__repository.find_all_call_logs_on_the_basis_of_user_id(
                    user_id, limit, offset, query
                )
            )
            self.__logger.debug("User: {}, retrieved CDRs: {}".format(user_id, cdrs))

            if not cdrs:
                return TalkoContract.AgentCallLogResponse(
                    call_histories=[],
                    total_count=total_count,
                )

            for cdr in cdrs:
                self.__logger.info("Getting recording url for agent_call_logs")
                await self.get_url_from_path(cdr)
                self.__logger.info("Generated recording url for agent_call_logs")

            agent_ids: list[int]
            cdr_responses: list[TalkoContract.CallLogResponse]
            agent_ids, cdr_responses = TalkoGetAgentCallLogsHelper.process_cdrs(
                cdrs, is_masking_enabled, self.__logger
            )

            self.__logger.debug(
                "Processed TalkoCDR responses in agent call logs: {}".format(cdr_responses)
            )
            self.__logger.debug(
                "Agent IDs to fetch agent call logs: {}".format(agent_ids)
            )

            did_numbers: list[str] = list(
                {cdr.did_number for cdr in cdr_responses if cdr.did_number}
            )

            grpc_client = TalkoRPCServiceFactory.get_service(TalkoGrpcServices.AUTH)

            # These two lookups are independent of each other — run them
            # concurrently so the display_name lookup adds ~0ms to the
            # critical path instead of stacking on top of the gRPC call.
            agent_data, display_name_map = await asyncio.gather(
                grpc_client.get_service_board_users_details(agent_ids),
                self.__did_repository.get_display_names_by_dids(did_numbers),
            )

            TalkoCommonCDRHelper.attach_agent_names(cdr_responses, agent_data, self.__logger)
            TalkoCommonCDRHelper.attach_display_names(
                cdr_responses, display_name_map, self.__logger
            )

            self.__logger.info(
                "Fetched all CDRs successfully for partner {}.".format(partner_id)
            )

            finally_response: dict = TalkoGetAgentCallLogsHelper.agent_call_log_response(
                cdr_responses, total_count, self.__logger
            )

            self.__logger.debug(
                "User: {}, final response for agent call logs: {}".format(
                    user_id, finally_response
                )
            )
            return TalkoContract.AgentCallLogResponse(**finally_response)

        except Exception as e:
            self.__logger.error("Failed to retrieve CDRs: {}.".format(str(e)))
            raise

    async def get_call_record_history(
        self,
        user_id: int,
        partner_id: int,
        limit: int,
        offset: int,
        payload: dict,
    ) -> TalkoContract.AgentCallRecordHistoryResponse:
        try:
            self.__logger.info(
                "User: {}, partner: {}, get call record history service started.".format(
                    user_id, partner_id
                )
            )
            self.__logger.debug("Payload received: {}".format(payload))

            call_status: str = payload.get("call_status")
            TalkoGetCallRecordHistoryHelper.validate_call_status(call_status, self.__logger)

            board_agent_ids = [user_id]

            board_agent_ids, user_role = (
                await self.__analytics_processor.user_hierarchy_data(
                    request_data=payload, current_user_id=user_id
                )
            )
            if not board_agent_ids:
                return TalkoContract.AgentCallRecordHistoryResponse(
                    call_record=[],
                    total_count=0,
                )

            self.__logger.debug("Board agent IDs for query: {}".format(board_agent_ids))

            lead_id: Optional[int] = payload.get("lead_id")
            entity_type: Optional[str] = payload.get("entity_type")
            entity_id: Optional[int] = payload.get("entity_id")

            if entity_type is None and entity_id is None and lead_id is not None:
                entity_type = TalkoEntityType.LEAD.value
                entity_id = lead_id

            derived_lead_id = (
                entity_id if entity_type == TalkoEntityType.LEAD.value else None
            )

            service_board_id: int = payload.get("service_board_id")
            time_range: str = payload.get("time_range")
            call_status: str = payload.get("call_status")
            phone_number: str = payload.get("phone_number")
            talk_time_range: Optional[list[str]] = payload.get("talk_time_range")
            agents: list = payload.get("agents", [])
            call_type: str = payload.get("call_type", "")
            did_number: str = payload.get("did_number", "")
            is_masking_enabled: bool = payload.get("is_masking_enabled", True)
            custom_fields: Optional[Dict[str, Any]] = payload.get("custom_fields")

            if agents:
                board_agent_ids = agents

            if user_role == TalkoUserRoleHierarchy.MAINTAINER.value and not agents:
                board_agent_ids = []

            start_time: int = 0
            end_time: int = 0
            if time_range:
                start_time, end_time = self.__datetime_util.parse_time_str(time_range)

            if start_time == 0 or end_time == 0:
                start_time, end_time, _ = (
                    self.__date_range_helper.get_default_date_range()
                )

            self.__logger.debug(
                "Filters - lead_id: {}, entity_type: {}, entity_id: {}, service_board_id: {}, start_time: {}, end_time: {}, call_status: {}, phone_number: {}, talk_time_range: {}, call_type: {}, did_number: {}".format(
                    derived_lead_id,
                    entity_type,
                    entity_id,
                    service_board_id,
                    start_time,
                    end_time,
                    call_status,
                    phone_number,
                    talk_time_range,
                    call_type,
                    did_number,
                )
            )

            query: dict = TalkoGetCallRecordHistoryHelper.build_call_record_history_query(
                lead_id=derived_lead_id,
                service_board_id=service_board_id,
                call_status=call_status,
                board_agent_ids=board_agent_ids,
                phone_number=phone_number,
                start_time=start_time,
                end_time=end_time,
                partner_id=partner_id,
                talk_time_range=talk_time_range,
                call_type=call_type,
                did_number=did_number,
                logger=self.__logger,
                entity_type=entity_type,
                entity_id=entity_id,
                custom_fields=custom_fields,
            )

            self.__logger.debug("Constructed query: {}".format(query))

            status_match: Optional[dict] = (
                TalkoGetCallRecordHistoryHelper.build_status_match(
                    call_status, self.__logger
                )
            )

            self.__logger.debug(
                "Constructed query: {}, status_match: {}".format(query, status_match)
            )

            projection: dict = (
                TalkoGetCallRecordHistoryHelper.get_call_record_history_projection()
            )
            cdrs, total_count = (
                await self.__repository.find_all_call_logs_on_the_basis_of_user_id(
                    user_id, limit, offset, query, projection, status_match
                )
            )
            self.__logger.debug("User: {}, retrieved CDRs: {}".format(user_id, cdrs))

            if not cdrs:
                return TalkoContract.AgentCallRecordHistoryResponse(
                    call_record=[],
                    total_count=0,
                )

            agent_ids: list = []
            cdr_responses: list = []
            for cdr in cdrs:
                self.__logger.info("Getting recording url for call_record_history")
                await self.get_url_from_path(cdr)
                self.__logger.info("Generated recording url for call_record_history")

                filtered_cdr = (
                    TalkoGetCallRecordHistoryHelper.handle_call_record_history_data(
                        cdr, call_status, is_masking_enabled, self.__logger
                    )
                )
                if filtered_cdr:
                    cdr_responses.append(
                        TalkoContract.CallRecordHistoryResponse(**filtered_cdr)
                    )
                    agent_ids.append(cdr.get("agent"))

            self.__logger.debug("Processed TalkoCDR responses: {}".format(cdr_responses))
            self.__logger.debug("Agent IDs to fetch: {}".format(agent_ids))

            did_numbers: list[str] = list(
                {cdr.did_number for cdr in cdr_responses if cdr.did_number}
            )

            grpc_client = TalkoRPCServiceFactory.get_service(TalkoGrpcServices.AUTH)

            # Independent lookups — run concurrently instead of sequentially
            # so the display_name lookup doesn't add latency on top of the
            # gRPC agent-details call.
            agent_data, display_name_map = await asyncio.gather(
                grpc_client.get_service_board_users_details(agent_ids),
                self.__did_repository.get_display_names_by_dids(did_numbers),
            )

            self.__logger.debug("Fetched agent data: {}".format(agent_data))
            self.__logger.debug("TalkoCDR responses data: {}".format(cdr_responses))
            TalkoCommonCDRHelper.attach_agent_names(cdr_responses, agent_data, self.__logger)
            TalkoCommonCDRHelper.attach_display_names(
                cdr_responses, display_name_map, self.__logger
            )

            finally_response = (
                TalkoGetCallRecordHistoryHelper.agent_call_record_history_response(
                    cdr_responses, total_count, self.__logger
                )
            )

            self.__logger.info(
                "Fetched all call records successfully for partner {}.".format(
                    partner_id
                )
            )
            return TalkoContract.AgentCallRecordHistoryResponse(**finally_response)
        except Exception as e:
            self.__logger.error("Failed to retrieve call records: {}.".format(str(e)))
            raise

    async def set_custom_field_values(
        self,
        user_id: int,
        partner_id: int,
        call_id: str,
        values: Dict[str, Any],
    ) -> TalkoContract.SetCDRCustomFieldsResponse:
        try:
            self.__logger.info(
                "User: {}, partner: {}, call_id: {}, set cdr custom field values started.".format(
                    user_id, partner_id, call_id
                )
            )

            cdr: Optional[Dict[str, Any]] = await self.__repository.find_cdr_by_call_id(
                call_id
            )
            if not cdr or cdr.get("partner_id") != partner_id:
                self.__logger.error(
                    "TalkoCDR not found for call_id {} and partner {}.".format(
                        call_id, partner_id
                    )
                )
                raise TalkoResourceNotFound(CDR_NOT_FOUND_FOR_CALL_ID.format(call_id))

            normalized_values: Dict[str, Any] = (
                await self.__custom_field_validator.validate_and_normalize_values(
                    partner_id, TalkoCustomFieldEntityType.TalkoCDR.value, values
                )
            )

            updated_at: int = self.__datetime_util.get_current_time()
            updated_cdr: Optional[Dict[str, Any]] = (
                await self.__repository.set_custom_field_values(
                    call_id, normalized_values, updated_at
                )
            )

            self.__logger.info(
                "Set custom field values for call_id {} successfully.".format(call_id)
            )
            return TalkoContract.SetCDRCustomFieldsResponse(
                call_id=call_id,
                custom_fields=(updated_cdr or {}).get("custom_fields") or {},
                message="Custom field values updated successfully.",
            )
        except Exception as e:
            self.__logger.error(
                "Failed to set custom field values for call_id {}: {}.".format(
                    call_id, str(e)
                )
            )
            raise

    async def get_url_from_path(self, cdr: dict):
        try:
            self.__logger.info(
                "TalkoCDR for fetching recording url from path: {}".format(cdr)
            )
            if cdr.get("path_for_recording"):
                cdr["do_recording_url"] = (
                    await self.__asset_helper.get_recording_url_from_path(
                        cdr["path_for_recording"]
                    )
                )
            else:
                self.__logger.info("Path not present for url generation")
        except Exception as e:
            self.__logger.error("Failed to generate URL: {}.".format(str(e)))
            raise
