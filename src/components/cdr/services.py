import asyncio
from typing import Any

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

    async def get_cdrs(self, user_id: int, partner_id: int, limit: int, offset: int) -> list[TalkoContract.CDRResponse]:
        """
        Fetch CDRs by partner ID.

        Args:
            user_id (int): Requesting user's ID.
            partner_id (int): Partner ID for TalkoCDR fetch.

        Returns:
            list[TalkoContract.CDRResponse]: List of CDRs.
        """
        try:
            self.__logger.info(f"User: {user_id}, partner: {partner_id}, get cdrs service methods started.")
            cdrs: dict | None = await self.__repository.find_all_cdrs_on_the_basis_of_partner_id(
                partner_id, limit, offset
            )
            self.__logger.debug(f"User: {user_id}, get cdr data on the basis of partner id. data: {cdrs}")
            cdr_responses = TalkoGetCDRsHelper.process_cdrs(cdrs, self.__logger)

            self.__logger.info("Get all cdrs on the basis of partner id fetched all data successfully.")

            return cdr_responses
        except Exception as e:
            self.__logger.error(f"Failed to retrieve CDRs: {str(e)}.")
            raise

    async def get_agent_call_logs(
        self,
        user_id: int,
        partner_id: int,
        limit: int,
        offset: int,
        lead_id: int | list[int] | None = None,
        created_at: int | None = None,
        filter_by: TalkoTimeFilter | None = None,
        is_masking_enabled: bool | None = True,
        entity_type: str | None = None,
        entity_id: int | list[int] | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> TalkoContract.AgentCallLogResponse:
        try:
            self.__logger.info(f"User: {user_id}, partner: {partner_id}, get agent call logs service started.")

            normalized_entity_type = entity_type
            normalized_entity_id = entity_id

            if normalized_entity_type is None and normalized_entity_id is None and lead_id is not None:
                normalized_entity_type = TalkoEntityType.LEAD.value
                normalized_entity_id = lead_id

            derived_lead_id = normalized_entity_id if normalized_entity_type == TalkoEntityType.LEAD.value else None

            self.__logger.debug(
                f"Call log filters - lead_id: {derived_lead_id}, entity_type: {normalized_entity_type}, entity_id: {normalized_entity_id}, created_at: {created_at}, filter_by: {filter_by}, partner_id: {partner_id}"
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
            self.__logger.debug(f"Get agent call logs service constructed query: {query}")
            cdrs: dict | None = {}
            total_count: int = 0
            cdrs, total_count = await self.__repository.find_all_call_logs_on_the_basis_of_user_id(
                user_id, limit, offset, query
            )
            self.__logger.debug(f"User: {user_id}, retrieved CDRs: {cdrs}")

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
            agent_ids, cdr_responses = TalkoGetAgentCallLogsHelper.process_cdrs(cdrs, is_masking_enabled, self.__logger)

            self.__logger.debug(f"Processed TalkoCDR responses in agent call logs: {cdr_responses}")
            self.__logger.debug(f"Agent IDs to fetch agent call logs: {agent_ids}")

            did_numbers: list[str] = list({cdr.did_number for cdr in cdr_responses if cdr.did_number})

            grpc_client = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.AUTH)

            # These two lookups are independent of each other — run them
            # concurrently so the display_name lookup adds ~0ms to the
            # critical path instead of stacking on top of the gRPC call.
            # gRPC disabled → agent names stay blank (fail-open enrichment).
            if grpc_client is None:
                agent_data = {}
                display_name_map = await self.__did_repository.get_display_names_by_dids(did_numbers)
            else:
                agent_data, display_name_map = await asyncio.gather(
                    grpc_client.get_workspace_users_details(agent_ids),
                    self.__did_repository.get_display_names_by_dids(did_numbers),
                )

            TalkoCommonCDRHelper.attach_agent_names(cdr_responses, agent_data, self.__logger)
            TalkoCommonCDRHelper.attach_display_names(cdr_responses, display_name_map, self.__logger)

            self.__logger.info(f"Fetched all CDRs successfully for partner {partner_id}.")

            finally_response: dict = TalkoGetAgentCallLogsHelper.agent_call_log_response(
                cdr_responses, total_count, self.__logger
            )

            self.__logger.debug(f"User: {user_id}, final response for agent call logs: {finally_response}")
            return TalkoContract.AgentCallLogResponse(**finally_response)

        except Exception as e:
            self.__logger.error(f"Failed to retrieve CDRs: {str(e)}.")
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
            self.__logger.info(f"User: {user_id}, partner: {partner_id}, get call record history service started.")
            self.__logger.debug(f"Payload received: {payload}")

            call_status: str = payload.get("call_status")
            TalkoGetCallRecordHistoryHelper.validate_call_status(call_status, self.__logger)

            workspace_agent_ids = [user_id]

            workspace_agent_ids, user_role = await self.__analytics_processor.user_hierarchy_data(
                request_data=payload, current_user_id=user_id
            )
            if not workspace_agent_ids:
                return TalkoContract.AgentCallRecordHistoryResponse(
                    call_record=[],
                    total_count=0,
                )

            self.__logger.debug(f"Workspace agent IDs for query: {workspace_agent_ids}")

            lead_id: int | None = payload.get("lead_id")
            entity_type: str | None = payload.get("entity_type")
            entity_id: int | None = payload.get("entity_id")

            if entity_type is None and entity_id is None and lead_id is not None:
                entity_type = TalkoEntityType.LEAD.value
                entity_id = lead_id

            derived_lead_id = entity_id if entity_type == TalkoEntityType.LEAD.value else None

            workspace_id: int = payload.get("workspace_id")
            time_range: str = payload.get("time_range")
            call_status: str = payload.get("call_status")
            phone_number: str = payload.get("phone_number")
            talk_time_range: list[str] | None = payload.get("talk_time_range")
            agents: list = payload.get("agents", [])
            call_type: str = payload.get("call_type", "")
            did_number: str = payload.get("did_number", "")
            is_masking_enabled: bool = payload.get("is_masking_enabled", True)
            custom_fields: dict[str, Any] | None = payload.get("custom_fields")

            if agents:
                workspace_agent_ids = agents

            if user_role == TalkoUserRoleHierarchy.MAINTAINER.value and not agents:
                workspace_agent_ids = []

            start_time: int = 0
            end_time: int = 0
            if time_range:
                start_time, end_time = self.__datetime_util.parse_time_str(time_range)

            if start_time == 0 or end_time == 0:
                start_time, end_time, _ = self.__date_range_helper.get_default_date_range()

            self.__logger.debug(
                f"Filters - lead_id: {derived_lead_id}, entity_type: {entity_type}, entity_id: {entity_id}, workspace_id: {workspace_id}, start_time: {start_time}, end_time: {end_time}, call_status: {call_status}, phone_number: {phone_number}, talk_time_range: {talk_time_range}, call_type: {call_type}, did_number: {did_number}"
            )

            query: dict = TalkoGetCallRecordHistoryHelper.build_call_record_history_query(
                lead_id=derived_lead_id,
                workspace_id=workspace_id,
                call_status=call_status,
                workspace_agent_ids=workspace_agent_ids,
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

            self.__logger.debug(f"Constructed query: {query}")

            status_match: dict | None = TalkoGetCallRecordHistoryHelper.build_status_match(call_status, self.__logger)

            self.__logger.debug(f"Constructed query: {query}, status_match: {status_match}")

            projection: dict = TalkoGetCallRecordHistoryHelper.get_call_record_history_projection()
            cdrs, total_count = await self.__repository.find_all_call_logs_on_the_basis_of_user_id(
                user_id, limit, offset, query, projection, status_match
            )
            self.__logger.debug(f"User: {user_id}, retrieved CDRs: {cdrs}")

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

                filtered_cdr = TalkoGetCallRecordHistoryHelper.handle_call_record_history_data(
                    cdr, call_status, is_masking_enabled, self.__logger
                )
                if filtered_cdr:
                    cdr_responses.append(TalkoContract.CallRecordHistoryResponse(**filtered_cdr))
                    agent_ids.append(cdr.get("agent"))

            self.__logger.debug(f"Processed TalkoCDR responses: {cdr_responses}")
            self.__logger.debug(f"Agent IDs to fetch: {agent_ids}")

            did_numbers: list[str] = list({cdr.did_number for cdr in cdr_responses if cdr.did_number})

            grpc_client = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.AUTH)

            # Independent lookups — run concurrently instead of sequentially
            # so the display_name lookup doesn't add latency on top of the
            # gRPC agent-details call. gRPC disabled → names stay blank.
            if grpc_client is None:
                agent_data = {}
                display_name_map = await self.__did_repository.get_display_names_by_dids(did_numbers)
            else:
                agent_data, display_name_map = await asyncio.gather(
                    grpc_client.get_workspace_users_details(agent_ids),
                    self.__did_repository.get_display_names_by_dids(did_numbers),
                )

            self.__logger.debug(f"Fetched agent data: {agent_data}")
            self.__logger.debug(f"TalkoCDR responses data: {cdr_responses}")
            TalkoCommonCDRHelper.attach_agent_names(cdr_responses, agent_data, self.__logger)
            TalkoCommonCDRHelper.attach_display_names(cdr_responses, display_name_map, self.__logger)

            finally_response = TalkoGetCallRecordHistoryHelper.agent_call_record_history_response(
                cdr_responses, total_count, self.__logger
            )

            self.__logger.info(f"Fetched all call records successfully for partner {partner_id}.")
            return TalkoContract.AgentCallRecordHistoryResponse(**finally_response)
        except Exception as e:
            self.__logger.error(f"Failed to retrieve call records: {str(e)}.")
            raise

    async def set_custom_field_values(
        self,
        user_id: int,
        partner_id: int,
        call_id: str,
        values: dict[str, Any],
    ) -> TalkoContract.SetCDRCustomFieldsResponse:
        try:
            self.__logger.info(
                f"User: {user_id}, partner: {partner_id}, call_id: {call_id}, set cdr custom field values started."
            )

            cdr: dict[str, Any] | None = await self.__repository.find_cdr_by_call_id(call_id)
            if not cdr or cdr.get("partner_id") != partner_id:
                self.__logger.error(f"TalkoCDR not found for call_id {call_id} and partner {partner_id}.")
                raise TalkoResourceNotFound(CDR_NOT_FOUND_FOR_CALL_ID.format(call_id))

            normalized_values: dict[str, Any] = await self.__custom_field_validator.validate_and_normalize_values(
                partner_id, TalkoCustomFieldEntityType.TalkoCDR.value, values
            )

            updated_at: int = self.__datetime_util.get_current_time()
            updated_cdr: dict[str, Any] | None = await self.__repository.set_custom_field_values(
                call_id, normalized_values, updated_at
            )

            self.__logger.info(f"Set custom field values for call_id {call_id} successfully.")
            return TalkoContract.SetCDRCustomFieldsResponse(
                call_id=call_id,
                custom_fields=(updated_cdr or {}).get("custom_fields") or {},
                message="Custom field values updated successfully.",
            )
        except Exception as e:
            self.__logger.error(f"Failed to set custom field values for call_id {call_id}: {str(e)}.")
            raise

    async def get_url_from_path(self, cdr: dict):
        try:
            self.__logger.info(f"TalkoCDR for fetching recording url from path: {cdr}")
            if cdr.get("path_for_recording"):
                cdr["do_recording_url"] = await self.__asset_helper.get_recording_url_from_path(
                    cdr["path_for_recording"]
                )
            else:
                self.__logger.info("Path not present for url generation")
        except Exception as e:
            self.__logger.error(f"Failed to generate URL: {str(e)}.")
            raise
