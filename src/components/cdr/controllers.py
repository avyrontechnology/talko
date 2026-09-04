import json
from typing import List, Optional, Union

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status

from src.components.cdr import messages as cdr_messages
from src.components.cdr.constants import EntityType
from src.components.cdr.dto import Contract
from src.components.cdr.services import CDRService
from src.components.common.constants import CurrentUserMap, PaginationConstants
from src.components.common.responses import (
    BadRequestResponse,
    InternalServerErrorResponse,
    ResourceNotFoundResponse,
    SuccessResponse,
)
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import BadRequestError, ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.enums import TimeFilter


class CDRController:
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

    @cdr_router.get("", response_model=list[Contract.CDRResponse])
    @permission_check(PermissionDependency)
    @inject
    async def get_cdrs(
        request: Request,
        offset: int = Query(
            PaginationConstants.offset,
            ge=PaginationConstants.offset,
            description="Page number for pagination",
        ),
        limit: int = Query(
            PaginationConstants.limit,
            ge=PaginationConstants.offset,
            le=PaginationConstants.LIMIT_MAX,
            description="Number of items per page",
        ),
        cdr_service: CDRService = Depends(Provide[Container.cdr_config_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> list[Contract.CDRResponse]:
        try:
            holler_service_logger.info("Retrieving all CDRs")
            current_user_data: dict = request.state.user
            holler_service_logger.info(
                "Current user data: {}, get all cdrs initiated.".format(
                    current_user_data
                )
            )
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, limit: {}, offset: {}, get cdr records api initiated.".format(
                    user_id, partner_id, limit, offset
                )
            )
            cdrs: list[Contract.CDRResponse] = await cdr_service.get_cdrs(
                user_id, partner_id, limit, offset
            )
            holler_service_logger.info("Retrieved {} CDRs".format(len(cdrs)))
            return SuccessResponse(cdrs)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving CDRs: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=str(e))

    @cdr_router.get("/agent_call_logs", response_model=Contract.AgentCallLogResponse)
    @permission_check(PermissionDependency)
    @inject
    async def get_agent_call_logs(
        request: Request,
        offset: int = Query(
            PaginationConstants.offset,
            ge=PaginationConstants.offset,
            description="Page number for pagination",
        ),
        limit: int = Query(
            PaginationConstants.limit,
            ge=PaginationConstants.offset,
            le=PaginationConstants.LIMIT_MAX,
            description="Number of items per page",
        ),
        entity_type: Optional[EntityType] = Query(
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
        filter_by: Optional[TimeFilter] = Query(
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
        cdr_service: CDRService = Depends(Provide[Container.cdr_config_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.AgentCallLogResponse:
        try:
            holler_service_logger.info("Retrieving Call logs started.")
            current_user_data: dict = request.state.user
            holler_service_logger.info(
                "Current user data: {}, get call logs api initiated.".format(
                    current_user_data
                )
            )
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)

            try:
                entity_ids_list = CDRController._parse_id_list_param(
                    entity_ids, "entity_ids"
                )
                lead_ids_list = CDRController._parse_id_list_param(lead_ids, "lead_ids")
            except ValueError as e:
                return BadRequestResponse(detail=str(e))

            merged_entity_id = CDRController._merge_ids(entity_id, entity_ids_list)
            merged_lead_id = CDRController._merge_ids(lead_id, lead_ids_list)

            normalized_entity_type = entity_type.value if entity_type else None
            normalized_entity_id = merged_entity_id

            # Default entity_type to Lead if not passed
            if normalized_entity_type is None:
                if normalized_entity_id is not None:
                    normalized_entity_type = EntityType.LEAD.value
                elif merged_lead_id is not None:
                    normalized_entity_type = EntityType.LEAD.value
                    normalized_entity_id = merged_lead_id

            # Backward compatibility for deprecated lead_id/lead_ids
            if normalized_entity_id is None and merged_lead_id is not None:
                normalized_entity_id = merged_lead_id
                if normalized_entity_type is None:
                    normalized_entity_type = EntityType.LEAD.value

            if normalized_entity_id is None:
                return BadRequestResponse(
                    detail="Either entity_id/entity_ids or deprecated lead_id/lead_ids is required"
                )

            parsed_custom_fields: Optional[dict] = None
            if custom_fields:
                try:
                    parsed_custom_fields = json.loads(custom_fields)
                    if not isinstance(parsed_custom_fields, dict):
                        return BadRequestResponse(
                            detail="custom_fields must be a JSON object, e.g. "
                            '{"lead_source":"Referral"}'
                        )
                except json.JSONDecodeError:
                    return BadRequestResponse(
                        detail="custom_fields must be a valid JSON object, e.g. "
                        '{"lead_source":"Referral"}'
                    )

            holler_service_logger.info(
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

            cdrs: Contract.AgentCallLogResponse = await cdr_service.get_agent_call_logs(
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
            holler_service_logger.info("Retrieved {} Call logs response".format(cdrs))
            return SuccessResponse(cdrs)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving Call Logs Response: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=str(e))

    @cdr_router.get(
        "/call-record-history", response_model=Contract.AgentCallRecordHistoryResponse
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_call_record_history(
        request: Request,
        offset: int = Query(
            PaginationConstants.offset,
            ge=PaginationConstants.offset,
            description="Page number for pagination",
        ),
        limit: int = Query(
            PaginationConstants.limit,
            ge=PaginationConstants.offset,
            le=PaginationConstants.LIMIT_MAX,
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
        cdr_service: CDRService = Depends(Provide[Container.cdr_config_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.AgentCallRecordHistoryResponse:
        try:
            holler_service_logger.info("Retrieving call record history started.")
            current_user_data: dict = request.state.user
            holler_service_logger.info(
                "Current user data: {}, get call record history initiated.".format(
                    current_user_data
                )
            )
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
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
                        return BadRequestResponse(
                            detail=cdr_messages.PAYLOAD_MUST_BE_A_JSON_OBJECT
                        )

                # Default entity_type to Lead when only entity_id is passed
                if (
                    data_dict.get("entity_type") is None
                    and data_dict.get("entity_id") is not None
                ):
                    data_dict["entity_type"] = EntityType.LEAD.value

                # Backward compatibility for deprecated lead_id
                if (
                    data_dict.get("entity_type") is None
                    and data_dict.get("entity_id") is None
                    and data_dict.get("lead_id") is not None
                ):
                    data_dict["entity_type"] = EntityType.LEAD.value
                    data_dict["entity_id"] = data_dict["lead_id"]

                Contract.CallRecordHistoryPayload(**data_dict)

            except json.JSONDecodeError as e:
                holler_service_logger.error(
                    "Error in parsing JSON payload: {}".format(str(e))
                )
                return BadRequestResponse(
                    detail=(
                        "Payload must be a valid JSON string. Example: "
                        '{"entity_type": "Lead", "entity_id": 123, "lead_id": 123, '
                        '"service_board_id": 3, "time_range": "1232323-132213", '
                        '"call_status": ["missed", "answered"], "agents": [1, 2, 3], '
                        '"phone_number": "1234567890", "call_type": "inbound"}'
                    )
                )
            except ValueError as e:
                holler_service_logger.error(
                    "Validation error in payload: {}".format(str(e))
                )
                return BadRequestResponse(detail=str(e))

            call_logs: Contract.AgentCallRecordHistoryResponse = (
                await cdr_service.get_call_record_history(
                    user_id,
                    partner_id,
                    limit,
                    offset,
                    data_dict,
                )
            )
            holler_service_logger.info(
                "Retrieved {} call records".format(call_logs.total_count)
            )
            return SuccessResponse(call_logs)
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving call record history: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail="An unexpected error occurred")

    @cdr_router.post(
        "/{call_id}/custom-fields",
        response_model=Contract.SetCDRCustomFieldsResponse,
        status_code=status.HTTP_200_OK,
    )
    @permission_check(PermissionDependency)
    @inject
    async def set_cdr_custom_fields(
        request: Request,
        call_id: str,
        payload: Contract.SetCDRCustomFieldsRequest,
        cdr_service: CDRService = Depends(Provide[Container.cdr_config_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> Contract.SetCDRCustomFieldsResponse:
        try:
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, partner: {}, call_id: {}, set cdr custom fields api initiated. payload: {}".format(
                    user_id, partner_id, call_id, payload
                )
            )
            response: Contract.SetCDRCustomFieldsResponse = (
                await cdr_service.set_custom_field_values(
                    user_id, partner_id, call_id, payload.custom_fields
                )
            )
            return SuccessResponse(data=response)
        except BadRequestError as e:
            return BadRequestResponse(detail=str(e))
        except ResourceNotFound as e:
            return ResourceNotFoundResponse(detail=str(e))
        except Exception as e:
            holler_service_logger.error(
                "Unexpected error setting cdr custom fields: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail="An unexpected error occurred")
