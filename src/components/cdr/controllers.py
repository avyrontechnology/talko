import json
from typing import List, Optional, Union

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status

from src.components.cdr import messages as cdr_messages
from src.components.cdr.constants import TalkoEntityType
from src.components.cdr.dto import TalkoContract
from src.components.cdr.services import TalkoCDRService
from src.components.common.constants import TalkoCurrentUserMap, TalkoPaginationConstants
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import TalkoContainer
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.enums import TalkoTimeFilter


class TalkoCDRController:
    cdr_router = APIRouter()

    @staticmethod
    def _parse_id_list_param(
        value: Optional[str], param_name: str
    ) -> Optional[List[int]]:
        """
        Parse a query param that accepts a comma-separated list of integer
        IDs, e.g. "1,2,3". Returns a list of ints, or None if not provided.
        """
        if value is None:
            return None

        parts = [part.strip() for part in value.split(",") if part.strip()]
        if not parts:
            return None

        try:
            return [int(part) for part in parts]
        except ValueError:
            raise ValueError(
                "Invalid value(s) for {}: '{}'. Expected a comma-separated list of integers.".format(
                    param_name, value
                )
            )

    @staticmethod
    def _merge_ids(
        single_id: Optional[int], multi_ids: Optional[List[int]]
    ) -> Optional[Union[int, List[int]]]:
        """
        Merge a scalar ID param with a list ID param into one value: a plain
        int when there's exactly one distinct ID (preserving the prior
        single-ID behavior and query shape untouched), or a list of ints
        when there are multiple.
        """
        combined: List[int] = []
        if single_id is not None:
            combined.append(single_id)
        if multi_ids:
            combined.extend(multi_ids)

        if not combined:
            return None

        deduped = list(dict.fromkeys(combined))
        return deduped[0] if len(deduped) == 1 else deduped

    @cdr_router.get("", response_model=list[TalkoContract.CDRResponse])
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_cdrs(
        request: Request,
        offset: int = Query(
            TalkoPaginationConstants.offset,
            ge=TalkoPaginationConstants.offset,
            description="Page number for pagination",
        ),
        limit: int = Query(
            TalkoPaginationConstants.limit,
            ge=TalkoPaginationConstants.offset,
            le=TalkoPaginationConstants.LIMIT_MAX,
            description="Number of items per page",
        ),
        cdr_service: TalkoCDRService = Depends(Provide[TalkoContainer.cdr_config_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> list[TalkoContract.CDRResponse]:
        try:
            talko_service_logger.info("Retrieving all CDRs")
            current_user_data: dict = request.state.user
            talko_service_logger.info(
                "Current user data: {}, get all cdrs initiated.".format(
                    current_user_data
                )
            )
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, limit: {}, offset: {}, get cdr records api initiated.".format(
                    user_id, partner_id, limit, offset
                )
            )
            cdrs: list[TalkoContract.CDRResponse] = await cdr_service.get_cdrs(
                user_id, partner_id, limit, offset
            )
            talko_service_logger.info("Retrieved {} CDRs".format(len(cdrs)))
            return TalkoSuccessResponse(cdrs)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error retrieving CDRs: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=str(e))

    @cdr_router.get("/agent_call_logs", response_model=TalkoContract.AgentCallLogResponse)
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_agent_call_logs(
        request: Request,
        offset: int = Query(
            TalkoPaginationConstants.offset,
            ge=TalkoPaginationConstants.offset,
            description="Page number for pagination",
        ),
        limit: int = Query(
            TalkoPaginationConstants.limit,
            ge=TalkoPaginationConstants.offset,
            le=TalkoPaginationConstants.LIMIT_MAX,
            description="Number of items per page",
        ),
        entity_type: Optional[TalkoEntityType] = Query(
            None,
            description="Entity type to filter call logs, e.g. Lead or Contact",
        ),
        entity_id: Optional[int] = Query(
            None,
            description="Entity ID to filter call logs",
        ),
        entity_ids: Optional[str] = Query(
            None,
            description="Comma-separated list of Entity IDs to filter call logs, e.g. entity_ids=1,2,3",
        ),
        lead_id: Optional[int] = Query(
            None,
            description="Deprecated: Lead ID to filter call logs",
        ),
        lead_ids: Optional[str] = Query(
            None,
            description="Deprecated: Comma-separated list of Lead IDs to filter call logs, e.g. lead_ids=1,2,3",
        ),
        lead_created_at: Optional[int] = Query(
            None,
            description="Timestamp to filter call logs",
        ),
        filter_by: Optional[TalkoTimeFilter] = Query(
            None,
            description="Time filter: Today, Last week, or Last month",
        ),
        is_masking_enabled: bool = Query(
            False,
            description="Flag to enable masking of sensitive data",
        ),
        custom_fields: Optional[str] = Query(
            None,
            description=(
                "JSON object of custom_fields slug->value exact-match filters, "
                'e.g. custom_fields={"lead_source":"Referral"}. Always used '
                "together with a mandatory entity_id/lead_id, so it never scans "
                "more than one entity's call history."
            ),
        ),
        cdr_service: TalkoCDRService = Depends(Provide[TalkoContainer.cdr_config_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.AgentCallLogResponse:
        try:
            talko_service_logger.info("Retrieving Call logs started.")
            current_user_data: dict = request.state.user
            talko_service_logger.info(
                "Current user data: {}, get call logs api initiated.".format(
                    current_user_data
                )
            )
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)

            try:
                entity_ids_list = TalkoCDRController._parse_id_list_param(
                    entity_ids, "entity_ids"
                )
                lead_ids_list = TalkoCDRController._parse_id_list_param(lead_ids, "lead_ids")
            except ValueError as e:
                return TalkoBadRequestResponse(detail=str(e))

            merged_entity_id = TalkoCDRController._merge_ids(entity_id, entity_ids_list)
            merged_lead_id = TalkoCDRController._merge_ids(lead_id, lead_ids_list)

            normalized_entity_type = entity_type.value if entity_type else None
            normalized_entity_id = merged_entity_id

            # Default entity_type to Lead if not passed
            if normalized_entity_type is None:
                if normalized_entity_id is not None:
                    normalized_entity_type = TalkoEntityType.LEAD.value
                elif merged_lead_id is not None:
                    normalized_entity_type = TalkoEntityType.LEAD.value
                    normalized_entity_id = merged_lead_id

            # Backward compatibility for deprecated lead_id/lead_ids
            if normalized_entity_id is None and merged_lead_id is not None:
                normalized_entity_id = merged_lead_id
                if normalized_entity_type is None:
                    normalized_entity_type = TalkoEntityType.LEAD.value

            if normalized_entity_id is None:
                return TalkoBadRequestResponse(
                    detail="Either entity_id/entity_ids or deprecated lead_id/lead_ids is required"
                )

            parsed_custom_fields: Optional[dict] = None
            if custom_fields:
                try:
                    parsed_custom_fields = json.loads(custom_fields)
                    if not isinstance(parsed_custom_fields, dict):
                        return TalkoBadRequestResponse(
                            detail="custom_fields must be a JSON object, e.g. "
                            '{"lead_source":"Referral"}'
                        )
                except json.JSONDecodeError:
                    return TalkoBadRequestResponse(
                        detail="custom_fields must be a valid JSON object, e.g. "
                        '{"lead_source":"Referral"}'
                    )

            talko_service_logger.info(
                "User: {}, partner: {}, limit: {}, offset: {}, entity_type: {}, entity_id: {}, lead_created_at: {}, filter_by: {}, is_masking_enabled: {}, get call logs api initiated.".format(
                    user_id,
                    partner_id,
                    limit,
                    offset,
                    normalized_entity_type,
                    normalized_entity_id,
                    lead_created_at,
                    filter_by,
                    is_masking_enabled,
                )
            )

            cdrs: TalkoContract.AgentCallLogResponse = await cdr_service.get_agent_call_logs(
                user_id=user_id,
                partner_id=partner_id,
                limit=limit,
                offset=offset,
                lead_id=merged_lead_id,
                created_at=lead_created_at,
                filter_by=filter_by,
                is_masking_enabled=is_masking_enabled,
                entity_type=normalized_entity_type,
                entity_id=normalized_entity_id,
                custom_fields=parsed_custom_fields,
            )
            talko_service_logger.info("Retrieved {} Call logs response".format(cdrs))
            return TalkoSuccessResponse(cdrs)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error retrieving Call Logs Response: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail=str(e))

    @cdr_router.get(
        "/call-record-history", response_model=TalkoContract.AgentCallRecordHistoryResponse
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_call_record_history(
        request: Request,
        offset: int = Query(
            TalkoPaginationConstants.offset,
            ge=TalkoPaginationConstants.offset,
            description="Page number for pagination",
        ),
        limit: int = Query(
            TalkoPaginationConstants.limit,
            ge=TalkoPaginationConstants.offset,
            le=TalkoPaginationConstants.LIMIT_MAX,
            description="Number of items per page",
        ),
        payload: str = Query(
            ...,
            example={
                "entity_type": "Lead",
                "entity_id": 123,
                "lead_id": 123,
                "service_board_id": 3,
                "time_range": "1232323-132213",
                "call_status": ["missed"],
                "agents": [1, 2, 3],
                "phone_number": "1234567890",
                "call_type": "inbound",
                "did_number": "1234560",
            },
            description="Filter criteria for call record history",
        ),
        cdr_service: TalkoCDRService = Depends(Provide[TalkoContainer.cdr_config_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.AgentCallRecordHistoryResponse:
        try:
            talko_service_logger.info("Retrieving call record history started.")
            current_user_data: dict = request.state.user
            talko_service_logger.info(
                "Current user data: {}, get call record history initiated.".format(
                    current_user_data
                )
            )
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, limit: {}, offset: {}, payload: {}, get call record history initiated.".format(
                    user_id,
                    partner_id,
                    limit,
                    offset,
                    payload,
                )
            )

            try:
                if not payload or payload.strip() in ["{}", ""]:
                    data_dict = {}
                else:
                    data_dict = json.loads(payload)
                    if not isinstance(data_dict, dict):
                        return TalkoBadRequestResponse(
                            detail=cdr_messages.PAYLOAD_MUST_BE_A_JSON_OBJECT
                        )

                # Default entity_type to Lead when only entity_id is passed
                if (
                    data_dict.get("entity_type") is None
                    and data_dict.get("entity_id") is not None
                ):
                    data_dict["entity_type"] = TalkoEntityType.LEAD.value

                # Backward compatibility for deprecated lead_id
                if (
                    data_dict.get("entity_type") is None
                    and data_dict.get("entity_id") is None
                    and data_dict.get("lead_id") is not None
                ):
                    data_dict["entity_type"] = TalkoEntityType.LEAD.value
                    data_dict["entity_id"] = data_dict["lead_id"]

                TalkoContract.CallRecordHistoryPayload(**data_dict)

            except json.JSONDecodeError as e:
                talko_service_logger.error(
                    "Error in parsing JSON payload: {}".format(str(e))
                )
                return TalkoBadRequestResponse(
                    detail=(
                        "Payload must be a valid JSON string. Example: "
                        '{"entity_type": "Lead", "entity_id": 123, "lead_id": 123, '
                        '"service_board_id": 3, "time_range": "1232323-132213", '
                        '"call_status": ["missed", "answered"], "agents": [1, 2, 3], '
                        '"phone_number": "1234567890", "call_type": "inbound"}'
                    )
                )
            except ValueError as e:
                talko_service_logger.error(
                    "Validation error in payload: {}".format(str(e))
                )
                return TalkoBadRequestResponse(detail=str(e))

            call_logs: TalkoContract.AgentCallRecordHistoryResponse = (
                await cdr_service.get_call_record_history(
                    user_id,
                    partner_id,
                    limit,
                    offset,
                    data_dict,
                )
            )
            talko_service_logger.info(
                "Retrieved {} call records".format(call_logs.total_count)
            )
            return TalkoSuccessResponse(call_logs)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error retrieving call record history: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail="An unexpected error occurred")

    @cdr_router.post(
        "/{call_id}/custom-fields",
        response_model=TalkoContract.SetCDRCustomFieldsResponse,
        status_code=status.HTTP_200_OK,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def set_cdr_custom_fields(
        request: Request,
        call_id: str,
        payload: TalkoContract.SetCDRCustomFieldsRequest,
        cdr_service: TalkoCDRService = Depends(Provide[TalkoContainer.cdr_config_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.SetCDRCustomFieldsResponse:
        try:
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                "User: {}, partner: {}, call_id: {}, set cdr custom fields api initiated. payload: {}".format(
                    user_id, partner_id, call_id, payload
                )
            )
            response: TalkoContract.SetCDRCustomFieldsResponse = (
                await cdr_service.set_custom_field_values(
                    user_id, partner_id, call_id, payload.custom_fields
                )
            )
            return TalkoSuccessResponse(data=response)
        except TalkoBadRequestError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except TalkoResourceNotFound as e:
            return TalkoResourceNotFoundResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error setting cdr custom fields: {}".format(str(e))
            )
            return TalkoInternalServerErrorResponse(detail="An unexpected error occurred")
