from typing import List

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, status

from src.components.call_agent_map.dto import TalkoContract
from src.components.call_agent_map.messages import (
    BAD_REQUEST,
    IS_ACTIVE_UPDATE_SUCCESS,
    SOMETHING_WENT_WRONG,
)
from src.components.call_agent_map.services import TalkoAgentMappingService
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoInternalServerErrorResponse,
    TalkoResourceCreatedResponse,
    TalkoResourceNotFoundResponse,
    TalkoSuccessResponse,
)
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import TalkoContainer
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoCallAgentMappingController:
    """Controller to handle call-related API endpoints."""

    router = APIRouter()

    @router.post(
        "",
        response_model=TalkoContract.AgentDidMappingCreationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def create_agent_did_mapping(
        request: Request,
        call_agent_data: TalkoContract.AgentDidMappingCreate,
        call_agent_service: TalkoAgentMappingService = Depends(
            Provide[TalkoContainer.call_agent_mapping_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.AgentDidMappingCreationResponse:
        try:
            talko_service_logger.info(
                "Received call agent mapping creation request: {}".format(
                    call_agent_data
                )
            )
            mapping_response: TalkoContract.AgentDidMappingCreationResponse = (
                await call_agent_service.create_agent_did_mapping(
                    call_agent_data.agent_id,
                    call_agent_data.partner_id,
                )
            )
            return TalkoResourceCreatedResponse(data=mapping_response)
        except ValueError as e:
            talko_service_logger.error(
                "Error in creation of agent mapping: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=SOMETHING_WENT_WRONG)
        except TalkoResourceNotFound as e:
            talko_service_logger.error(
                "Resource not found while creating agent mapping: {}".format(str(e))
            )
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except TalkoBadRequestError as e:
            talko_service_logger.error(
                "Bad request while creating agent mapping: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=BAD_REQUEST)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error occurred while creating agent mapping: {}".format(
                    str(e)
                )
            )
            raise TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @router.get(
        "",
        response_model=List[TalkoContract.AgentDidMappingResponse],
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_all_agent_did_mapping(
        request: Request,
        call_agent_data: TalkoContract.AgentDidMappingCreate,
        call_agent_service: TalkoAgentMappingService = Depends(
            Provide[TalkoContainer.call_agent_mapping_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> List[TalkoContract.AgentDidMappingResponse]:
        try:
            talko_service_logger.info(
                "Call agent mapping get all data request: {}".format(call_agent_data)
            )
            mapping_response: TalkoContract.AgentDidMappingCreationResponse = (
                await call_agent_service.get_all_agent_did_mapping()
            )
            return TalkoSuccessResponse(data=mapping_response)
        except ValueError as e:
            talko_service_logger.error(
                "Error in getting all agent mapping: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=BAD_REQUEST)
        except TalkoResourceNotFound as e:
            talko_service_logger.error(
                "Resource not found while getting all agent mapping: {}".format(str(e))
            )
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except TalkoBadRequestError as e:
            talko_service_logger.error(
                "Bad request while getting all agent mapping: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=BAD_REQUEST)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error occurred while getting all agent mapping: {}".format(
                    str(e)
                )
            )
            raise TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
        
    # routes for agent to service board mapping
    @router.post(
        "/service-board-mapping",
        response_model=TalkoContract.AgentServiceBoardMappingCreationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def create_agent_service_board_mapping(
        request: Request,
        call_agent_data: TalkoContract.AgentServiceBoardMappingCreate,
        call_agent_service: TalkoAgentMappingService = Depends(
            Provide[TalkoContainer.call_agent_mapping_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> TalkoContract.AgentServiceBoardMappingCreationResponse:
        try:
            talko_service_logger.info(
                "Received call agent mapping creation request: {}".format(
                    call_agent_data
                )
            )
            mapping_response: TalkoContract.AgentServiceBoardMappingCreationResponse = (
                await call_agent_service.create_agent_service_board_mapping(
                    call_agent_data.partner_id,
                    call_agent_data.service_board_id,
                    call_agent_data.agent_id,
                    call_agent_data.agent_number
                )
            )
            return TalkoResourceCreatedResponse(data=mapping_response)
        except ValueError as e:
            talko_service_logger.error(
                "Error in creation of agent mapping: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=BAD_REQUEST)
        except TalkoResourceNotFound as e:
            talko_service_logger.error(
                "Resource not found while creating agent mapping: {}".format(str(e))
            )
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except TalkoBadRequestError as e:
            talko_service_logger.error(
                "Bad request while creating agent mapping: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=BAD_REQUEST)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error occurred while creating agent mapping: {}".format(
                    str(e)
                )
            )
            raise TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)    


    @router.get(
        "/service-board-mapping",
        response_model=List[TalkoContract.AgentServiceBoardMappingResponse],
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_agents_by_service_board(
        request: Request,
        service_board_id: int,
        partner_id: int,
        call_agent_service: TalkoAgentMappingService = Depends(
            Provide[TalkoContainer.call_agent_mapping_service]
        ),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> List[TalkoContract.AgentServiceBoardMappingResponse]:
        try:
            talko_service_logger.info(
                "Request received to fetch agents for service_board_id={}, partner_id={}".format(service_board_id, partner_id)
            )
            
            mapping_response: List[TalkoContract.AgentServiceBoardMappingResponse] = (
                await call_agent_service.get_agents_by_service_board(service_board_id, partner_id)
            )
            
            return TalkoSuccessResponse(data=mapping_response)
        
        except ValueError as e:
            talko_service_logger.error(
                "Error fetching agents for service board: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=BAD_REQUEST)
        
        except TalkoResourceNotFound as e:
            talko_service_logger.error(
                "Resource not found while fetching agents: {}".format(str(e))
            )
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        
        except TalkoBadRequestError as e:
            talko_service_logger.error(
                "Bad request while fetching agents: {}".format(str(e))
            )
            return TalkoBadRequestResponse(detail=BAD_REQUEST)
        
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error occurred while fetching agents: {}".format(str(e))
            )
            raise TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)  
        
    @router.patch(
        "/service-board-mapping/{partner_id}/{service_board_id}/status",
        status_code=status.HTTP_200_OK,
    )
    @inject
    async def update_agent_service_board_mapping_status(
        partner_id: int,
        service_board_id: int,
        is_active: bool,
        call_agent_service: TalkoAgentMappingService = Depends(Provide[TalkoContainer.call_agent_mapping_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ):
        """
        Update the 'is_active' field for all agent-service-board mappings 
        for a given partner_id and service_board_id.
        """
        try:
            updated_count = await call_agent_service.update_is_active_by_service_board_and_partner_id(
                partner_id, service_board_id, is_active
            )
            return TalkoSuccessResponse(
                data={
                    "message": IS_ACTIVE_UPDATE_SUCCESS.format(updated_count),
                    "updated_count": updated_count,
                }
            )
        except TalkoResourceNotFound as e:
            talko_service_logger.error(str(e))
            return TalkoResourceNotFoundResponse(detail=SOMETHING_WENT_WRONG)
        except Exception as e:
            talko_service_logger.error(
                "Unexpected error updating 'is_active' for service_board_id={}, partner_id={}: {}".format(service_board_id, partner_id, str(e))
            )
            raise
