from typing import Any, Dict, List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request

from src.components.common.constants import CurrentUserMap
from src.components.common.responses import (
    BadRequestResponse,
    InternalServerErrorResponse,
    SuccessResponse,
)
from src.components.did_management.constants import DIDStatus
from src.components.did_management.dto import Contract
from src.components.did_management.messages import (
    PARTNER_CONFIG_NOT_FOUND,
    SOMETHING_WENT_WRONG,
)
from src.components.did_management.services import DidManagementService
from src.components.rbac.permission_dependency import PermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.core.container import Container
from src.exceptions import ResourceNotFound
from src.loggers.holler_service_logger import HollerServiceLogger


class DIDController:
    did_router = APIRouter()

    @did_router.get(
        "/by-service-board",
        response_model=List[Contract.DIDResponse],
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_dids_by_service_board(
        request: Request,
        service_board_id: int = Query(..., description="Service board ID"),
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> List[Contract.DIDResponse]:
        try:
            holler_service_logger.info(
                "Fetching DIDs for service_board_id {}".format(service_board_id)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, Partner: {}, ServiceBoard: {}, fetching DIDs initiated.".format(
                    user_id, partner_id, service_board_id
                )
            )

            dids: List[Contract.DIDResponse] = (
                await did_service.get_dids_by_service_board(service_board_id)
            )

            holler_service_logger.info(
                "Retrieved {} DIDs for service_board_id {}".format(
                    len(dids), service_board_id
                )
            )
            return SuccessResponse(dids)

        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving DIDs for service_board_id {}: {}".format(
                    service_board_id, str(e)
                )
            )
            return InternalServerErrorResponse(detail=str(e))

    @did_router.get(
        "/available-for-assignment",
        response_model=List[Contract.DIDSeriesResponse],
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_dids_available_for_assignment(
        request: Request,
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> List[Contract.DIDSeriesResponse]:
        try:
            holler_service_logger.info("Fetching DIDs available to be assigned")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User: {}, Partner: {}".format(user_id, partner_id)
            )

            dids: List[Contract.DIDSeriesResponse] = (
                await did_service.get_dids_available_for_assignment(partner_id)
            )
            holler_service_logger.info("DIDS available to be assigned: {}".format(dids))

            holler_service_logger.info(
                "Successfully Retrieved DIDs which are available to be assigned"
            )
            return SuccessResponse(data=dids)

        except ValueError as ve:
            holler_service_logger.error("Partner config not found: {}".format(str(ve)))
            return BadRequestResponse(detail=PARTNER_CONFIG_NOT_FOUND)

        except Exception as e:
            holler_service_logger.error(
                "Unexpected error retrieving DIDs availbe for assignment{}".format(
                    str(e)
                )
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/assign-did-numbers",
        response_model=List[Contract.DIDSeriesResponse],
    )
    @permission_check(PermissionDependency)
    @inject
    async def assign_dids_available_for_assignment(
        request: Request,
        assign_did_data: Contract.AssignDIDToPartner,
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> dict:
        try:
            holler_service_logger.info("DIDs received to be assigned: ")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "Assign DID Numbers=> User: {}, Partner: {}, Assign_did_Data: {}".format(
                    user_id, partner_id, assign_did_data
                )
            )

            response: dict = await did_service.assign_dids_available_for_assignment(
                partner_id, assign_did_data
            )
            holler_service_logger.info(
                "Assign DID Numbers=> Response: {}".format(response)
            )

            holler_service_logger.info("Successfully assigned DIDs")
            return SuccessResponse(data=response)

        except ValueError as ve:
            holler_service_logger.error("Partner config not found: {}".format(str(ve)))
            return BadRequestResponse(detail=PARTNER_CONFIG_NOT_FOUND)

        except Exception as e:
            holler_service_logger.error(
                "Unexpected error assigning available DIDs {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/unassign-did-numbers",
        response_model=dict,
    )
    @permission_check(PermissionDependency)
    @inject
    async def unassign_dids_for_partner(
        request: Request,
        payload: Contract.UnassignDIDRequest,
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> dict:
        try:
            holler_service_logger.info(
                "DIDs received to be unassigned: {}".format(payload.did_numbers)
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "Unassign DID Numbers=> User: {}, Partner: {}".format(
                    user_id, partner_id
                )
            )

            response: dict = await did_service.unassign_dids_for_partner(
                partner_id, payload.did_numbers
            )
            holler_service_logger.info(
                "Unassign DID Numbers=> Response: {}".format(response)
            )

            holler_service_logger.info("Successfully unassigned DIDs")
            return SuccessResponse(data=response)

        except ValueError as ve:
            holler_service_logger.error("Partner config not found: {}".format(str(ve)))
            return BadRequestResponse(detail=PARTNER_CONFIG_NOT_FOUND)

        except Exception as e:
            holler_service_logger.error(
                "Unexpected error assigning available DIDs {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.patch(
        "/apply-did-status-update",
        response_model=dict,
    )
    @permission_check(PermissionDependency)
    @inject
    async def apply_did_status_update(
        request: Request,
        payload: Contract.AdminDIDAction,
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> dict:
        try:
            holler_service_logger.info(
                "Action received to update DID status: {}, for DIDs: {}".format(
                    payload.action, payload.did_numbers
                )
            )
            current_user = request.state.user
            user_id = current_user.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "Action {} applying DID status update: {} on {} DIDs".format(
                    user_id, payload.action, len(payload.did_numbers)
                )
            )

            result = await did_service.apply_did_status_update(partner_id, payload)

            summary = result.get("summary", {})
            total = summary.get("total", 0)
            succeeded = summary.get("succeeded", 0)
            failed = summary.get("failed", 0)

            holler_service_logger.info(
                "Action {} successfully applied DID status update: {} on DIDs: {}, Result: {}".format(
                    user_id, payload.action, payload.did_numbers, result
                )
            )
            if failed == 0:
                status_label = "success"
                message = "{} DIDs updated successfully".format(total)

            elif succeeded == 0:
                status_label = "failed"
                message = (
                    "{} DID failed to update".format(total)
                    if total == 1
                    else "{} DIDs failed to update".format(total)
                )

            else:
                status_label = "partial_success"
                message = "{} of {} DIDs updated successfully".format(succeeded, total)

            holler_service_logger.info("{} - {}".format(status_label, message))
            return SuccessResponse(status=status_label, message=message, data=result)

        except ValueError as ve:
            holler_service_logger.error(str(ve))
            return BadRequestResponse(detail=str(ve))
        except Exception as e:
            holler_service_logger.error(
                "Error in apply_did_status_update: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.get(
        "/list-dids",
        response_model=Contract.DIDListResponse,
    )
    @permission_check(PermissionDependency)
    @inject
    async def list_dids(
        request: Request,
        status: Optional[str] = Query(
            None,
            description="Filter by DID status (available, mapped, cooling_period, cooldown_completed)",
        ),
        service_board_id: Optional[int] = Query(
            None, description="Filter by service board ID"
        ),
        did_number: Optional[str] = Query(
            None,
            description="Partial or full DID number search (e.g. 98765 or +9198765)",
        ),
        page: int = Query(1, ge=1, description="Page number"),
        limit: int = Query(20, ge=1, le=2000, description="Items per page"),
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> dict:
        try:
            current_user = request.state.user
            user_id = current_user.get(CurrentUserMap.USER_ID)
            partner_id = current_user.get(CurrentUserMap.PARTNER_ID)
            holler_service_logger.info(
                "User {} calling list_dids - filters: status={}, ".format(
                    user_id, status
                )
                + "partner={}, board={}, did number={}, page={}, limit={}".format(
                    partner_id, service_board_id, did_number, page, limit
                )
            )

            result: Contract.DIDListResponse = await did_service.list_dids(
                status=status,
                partner_id=partner_id,
                service_board_id=service_board_id,
                did_number=did_number,
                page=page,
                limit=limit,
            )

            return SuccessResponse(data=result)

        except ValueError as ve:
            holler_service_logger.error(
                "Validation error in list_dids: {}".format(str(ve))
            )
            return BadRequestResponse(detail=str(ve))
        except Exception as e:
            holler_service_logger.error("Error in list_dids: {}".format(str(e)))
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.get(
        "/status-metadata",
        response_model=Contract.StatusMetadataResponse,
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_did_status_transitions(
        request: Request,
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> List[Contract.StatusMetadataResponse]:
        """
        Retrieve the allowed status transitions for DIDs.

        This API provides metadata about all DID status stages and the
        valid next stages for each status. The frontend uses this information
        to determine which actions are allowed and to disable invalid actions
        in the UI.
        """

        holler_service_logger.info("Fetching DID status transition metadata")

        current_user_data: dict = request.state.user
        user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
        partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)

        holler_service_logger.info(
            "Processing DID status metadata request for user_id={}, partner_id={}".format(
                user_id,
                partner_id,
            )
        )
        transitions = [
            Contract.StatusTransition(
                status=DIDStatus.AVAILABLE.value,
                next_eligible_status=[DIDStatus.MAPPED.value],
            ),
            Contract.StatusTransition(
                status=DIDStatus.MAPPED.value,
                next_eligible_status=[
                    DIDStatus.AVAILABLE.value,
                    DIDStatus.COOLING_PERIOD.value,
                ],
            ),
            Contract.StatusTransition(
                status=DIDStatus.COOLING_PERIOD.value,
                next_eligible_status=[],
            ),
            Contract.StatusTransition(
                status=DIDStatus.COOLDOWN_COMPLETED.value,
                next_eligible_status=[
                    DIDStatus.AVAILABLE.value,
                    DIDStatus.MAPPED.value,
                ],
            ),
        ]

        return Contract.StatusMetadataResponse(
            data=transitions,
            metadata={
                "total_statuses": len(transitions),
                "default_status": DIDStatus.AVAILABLE.value,
                "cooldown_status": [DIDStatus.COOLING_PERIOD.value],
            },
        )

    @did_router.post(
        "/assign-ai-agent",
        response_model=dict,
    )
    @permission_check(PermissionDependency)
    @inject
    async def assign_ai_agent_did(
        request: Request,
        assign_data: Contract.AssignAIAgentDIDRequest,
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> dict:
        try:
            holler_service_logger.info(
                "assign-ai-agent called. partner_id={}, agent_bot_id={}".format(
                    assign_data.partner_id, assign_data.agent_bot_id
                )
            )

            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(CurrentUserMap.PARTNER_ID)

            holler_service_logger.info(
                "User: {}, Partner: {}, assigning AI agent DID".format(
                    user_id, partner_id
                )
            )

            # Verify partner AI agent enabled (add partner_repo dependency if needed)
            did_record: dict = await did_service.assign_ai_agent_did(
                partner_id=assign_data.partner_id,
                agent_bot_id=assign_data.agent_bot_id,
                did_number=assign_data.did_number,
            )

            holler_service_logger.info(
                "AI agent DID assigned: {}".format(did_record["did_number"])
            )
            return SuccessResponse(data=did_record)

        except ResourceNotFound:
            holler_service_logger.error(
                "No available ai_agent DIDs for partner {}".format(
                    assign_data.partner_id
                )
            )
            return BadRequestResponse(detail="No available ai_agent DIDs")
        except Exception as e:
            holler_service_logger.error(
                "Error assigning AI agent DID: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/release-ai-agent",
        response_model=dict,
    )
    @permission_check(PermissionDependency)
    @inject
    async def release_ai_agent_did(
        request: Request,
        release_data: Contract.ReleaseAIAgentDIDRequest,
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> dict:
        try:
            holler_service_logger.info(
                "release-ai-agent called. partner_id={}, agent_bot_id={}".format(
                    release_data.partner_id, release_data.agent_bot_id
                )
            )

            released_dids: List[str] = await did_service.release_ai_agent_did(
                partner_id=release_data.partner_id,
                agent_bot_id=release_data.agent_bot_id,
            )

            holler_service_logger.info(
                "Released {} AI agent DIDs".format(len(released_dids))
            )
            return SuccessResponse(
                data={"released_dids": released_dids, "count": len(released_dids)}
            )

        except Exception as e:
            holler_service_logger.error(
                "Error releasing AI agent DIDs: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/campaign-claim",
        response_model=dict,
    )
    # No @permission_check for now — its permission slug is derived from
    # the route name (holler:claim_campaign_did) and has never been granted
    # to any role, so every caller 403s until RBAC is set up for it. Add it
    # back once that's done; this route is otherwise a live-session-only
    # call from makun-ai (still authenticated, just not permission-gated).
    @inject
    async def claim_campaign_did(
        request: Request,
        claim_data: Contract.ClaimCampaignDIDRequest,
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> dict:
        """
        Marks a DID as Mapped and binds it to the campaign's own
        agent_bot_id (required so holler's own AI-bridge session resolution,
        which reads agent_bot_id straight off the DID, can find an agent) —
        called by makun-ai when a DID is added to a campaign's did_selection.
        See DidManagementService.claim_did_for_campaign.
        """
        try:
            holler_service_logger.info(
                "campaign-claim called. partner_id={}, did_number={}, agent_bot_id={}".format(
                    claim_data.partner_id, claim_data.did_number, claim_data.agent_bot_id
                )
            )
            result: dict = await did_service.claim_did_for_campaign(
                partner_id=claim_data.partner_id,
                did_number=claim_data.did_number,
                agent_bot_id=claim_data.agent_bot_id,
            )
            return SuccessResponse(data=result)
        except ResourceNotFound as e:
            return BadRequestResponse(detail=str(e))
        except ValueError as e:
            return BadRequestResponse(detail=str(e))
        except Exception as e:
            holler_service_logger.error(
                "Error claiming campaign DID: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/campaign-release",
        response_model=dict,
    )
    # No @permission_check for now — same reason as campaign-claim above.
    @inject
    async def release_campaign_did(
        request: Request,
        release_data: Contract.ReleaseCampaignDIDRequest,
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> dict:
        """
        Reverts a campaign-claimed DID back to Available and clears its
        agent_bot_id — called by makun-ai when a DID is removed from a
        campaign's did_selection, or the campaign is deleted/stopped. Only
        acts if the DID is currently bound to exactly this agent_bot_id. See
        DidManagementService.release_campaign_did.
        """
        try:
            holler_service_logger.info(
                "campaign-release called. partner_id={}, did_number={}, agent_bot_id={}".format(
                    release_data.partner_id, release_data.did_number, release_data.agent_bot_id
                )
            )
            result: dict = await did_service.release_campaign_did(
                partner_id=release_data.partner_id,
                did_number=release_data.did_number,
                agent_bot_id=release_data.agent_bot_id,
            )
            return SuccessResponse(data=result)
        except ResourceNotFound as e:
            return BadRequestResponse(detail=str(e))
        except Exception as e:
            holler_service_logger.error(
                "Error releasing campaign DID: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.get(
        "/ai-agent/available",
        response_model=dict,
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_unassigned_available_ai_agent_dids(
        request: Request,
        partner_id: int = Query(..., description="Partner ID to filter DIDs"),
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> dict:
        """
        List ai_agent DIDs that are free (partner_id=0) and status=AVAILABLE
        for the given partner.
        """
        try:
            holler_service_logger.info(
                "get_unassigned_available_ai_agent_dids called. partner_id={}".format(
                    partner_id
                )
            )
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(CurrentUserMap.USER_ID)

            holler_service_logger.info(
                "User {} requesting unassigned available ai_agent DIDs for partner_id={}".format(
                    user_id, partner_id
                )
            )

            dids: List[str] = await did_service.list_unassigned_available_ai_agent_dids(
                partner_id=partner_id,
            )

            holler_service_logger.info(
                "Found {} unassigned available ai_agent DIDs for partner_id={}".format(
                    len(dids), partner_id
                )
            )
            return SuccessResponse(data={"dids": dids})

        except ValueError as ve:
            holler_service_logger.error(
                "Validation error in get_unassigned_available_ai_agent_dids: {}".format(
                    str(ve)
                )
            )
            return BadRequestResponse(detail=str(ve))

        except Exception as e:
            error_msg = f"Error fetching unassigned available ai_agent DIDs: {str(e)}"
            holler_service_logger.error(error_msg)
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.get(
        "/partner-ai-agent-dids",
        response_model=dict,
    )
    @permission_check(PermissionDependency)
    @inject
    async def get_ai_agent_dids(
        request: Request,
        agent_bot_id: int,
        partner_id: int = Query(..., description="Partner ID"),
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> dict:
        try:
            holler_service_logger.info(
                "get-ai-agent-dids called. agent_bot_id={}, partner_id={}".format(
                    agent_bot_id, partner_id
                )
            )

            dids: List[str] = await did_service.get_ai_agent_dids(
                partner_id, agent_bot_id
            )
            primary_did: Optional[str] = dids[0] if dids else None

            data: dict = {
                "agent_bot_id": agent_bot_id,
                "primary_did": primary_did,
                "did_numbers": dids,
                "count": len(dids),
            }

            holler_service_logger.info(
                "Found {} DIDs for AI agent {}".format(len(dids), agent_bot_id)
            )
            return SuccessResponse(data=data)

        except Exception as e:
            holler_service_logger.error(
                "Error fetching AI agent DIDs: {}".format(str(e))
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.get(
        "/list-ai-agent-dids",
        response_model=dict,
    )
    @inject
    async def list_ai_agent_dids(
        request: Request,
        partner_id: int = Query(..., description="Partner ID"),
        did_service: DidManagementService = Depends(Provide[Container.did_service]),
        holler_service_logger: HollerServiceLogger = Depends(Provide[Container.logger]),
    ) -> dict:
        """
        Internal service-to-service endpoint — returns every ai_agent-type DID
        for a partner (assigned or not). Called by makun-ai to enrich its
        agent list response. Not JWT-authenticated (see excluded_paths in
        AuthMiddleware) since it's called server-to-server, not by a user.
        """
        try:
            holler_service_logger.info(
                "list-ai-agent-dids called. partner_id={}".format(partner_id)
            )

            dids: List[Dict[str, Any]] = await did_service.list_ai_agent_dids(
                partner_id
            )

            holler_service_logger.info(
                "Found {} ai_agent DIDs for partner_id={}".format(
                    len(dids), partner_id
                )
            )
            return SuccessResponse(data={"dids": dids})

        except Exception as e:
            holler_service_logger.error(
                "Error listing ai_agent DIDs for partner_id={}: {}".format(
                    partner_id, str(e)
                )
            )
            return InternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
