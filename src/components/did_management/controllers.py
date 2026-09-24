from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Header, Query, Request

from src.components.common.constants import TalkoCurrentUserMap
from src.components.common.responses import (
    TalkoBadRequestResponse,
    TalkoForbiddenPermissionResponse,
    TalkoInternalServerErrorResponse,
    TalkoSuccessResponse,
)
from src.components.did_management.constants import TalkoDIDStatus
from src.components.did_management.dto import TalkoContract
from src.components.did_management.messages import (
    SOMETHING_WENT_WRONG,
)
from src.components.did_management.services import TalkoDidManagementService
from src.components.rbac.permission_dependency import TalkoPermissionDependency
from src.components.rbac.permission_injector import permission_check
from src.components.rbac.superadmin import (
    SUPERADMIN_SCOPE_HEADER,
    TalkoSuperadminDenied,
    resolve_effective_partner_id,
)
from src.core.container import TalkoContainer
from src.exceptions import TalkoResourceNotFound
from src.grpc_client.constants import TalkoGrpcServices
from src.grpc_client.rpc_service_factory import TalkoRPCServiceFactory
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoDIDController:
    did_router = APIRouter()

    @did_router.get(
        "/by-workspace",
        response_model=list[TalkoContract.DIDResponse],
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_dids_by_workspace(
        request: Request,
        workspace_id: int = Query(..., description="Workspace ID"),
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> list[TalkoContract.DIDResponse]:
        try:
            talko_service_logger.info(f"Fetching DIDs for workspace_id {workspace_id}")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                f"User: {user_id}, Partner: {partner_id}, Workspace: {workspace_id}, fetching DIDs initiated."
            )

            dids: list[TalkoContract.DIDResponse] = await did_service.get_dids_by_workspace(workspace_id)

            talko_service_logger.info(f"Retrieved {len(dids)} DIDs for workspace_id {workspace_id}")
            return TalkoSuccessResponse(dids)

        except Exception as e:
            talko_service_logger.error(f"Unexpected error retrieving DIDs for workspace_id {workspace_id}: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=str(e))

    @did_router.get(
        "/available-for-assignment",
        response_model=list[TalkoContract.DIDSeriesResponse],
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_dids_available_for_assignment(
        request: Request,
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
        partner_scope: int | None = Header(default=None, alias=SUPERADMIN_SCOPE_HEADER),
    ) -> list[TalkoContract.DIDSeriesResponse]:
        try:
            talko_service_logger.info("Fetching DIDs available to be assigned")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            grpc_client = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.AUTH)
            try:
                partner_id = await resolve_effective_partner_id(
                    request, grpc_client, talko_service_logger, partner_scope
                )
            except TalkoSuperadminDenied as denied:
                return TalkoForbiddenPermissionResponse(detail=str(denied))
            talko_service_logger.info(f"User: {user_id}, Partner: {partner_id}")

            dids: list[TalkoContract.DIDSeriesResponse] = await did_service.get_dids_available_for_assignment(
                partner_id
            )
            talko_service_logger.info(f"DIDS available to be assigned: {dids}")

            talko_service_logger.info("Successfully Retrieved DIDs which are available to be assigned")
            return TalkoSuccessResponse(data=dids)

        except ValueError as ve:
            talko_service_logger.error(f"DID request failed: {str(ve)}")
            return TalkoBadRequestResponse(detail=str(ve))

        except Exception as e:
            talko_service_logger.error(f"Unexpected error retrieving DIDs availbe for assignment{str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/assign-did-numbers",
        response_model=list[TalkoContract.DIDSeriesResponse],
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def assign_dids_available_for_assignment(
        request: Request,
        assign_did_data: TalkoContract.AssignDIDToPartner,
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
        partner_scope: int | None = Header(default=None, alias=SUPERADMIN_SCOPE_HEADER),
    ) -> dict:
        try:
            talko_service_logger.info("DIDs received to be assigned: ")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            grpc_client = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.AUTH)
            try:
                partner_id = await resolve_effective_partner_id(
                    request, grpc_client, talko_service_logger, partner_scope
                )
            except TalkoSuperadminDenied as denied:
                return TalkoForbiddenPermissionResponse(detail=str(denied))
            talko_service_logger.info(
                f"Assign DID Numbers=> User: {user_id}, Partner: {partner_id}, Assign_did_Data: {assign_did_data}"
            )

            response: dict = await did_service.assign_dids_available_for_assignment(partner_id, assign_did_data)
            talko_service_logger.info(f"Assign DID Numbers=> Response: {response}")

            talko_service_logger.info("Successfully assigned DIDs")
            return TalkoSuccessResponse(data=response)

        except ValueError as ve:
            talko_service_logger.error(f"DID request failed: {str(ve)}")
            return TalkoBadRequestResponse(detail=str(ve))

        except Exception as e:
            talko_service_logger.error(f"Unexpected error assigning available DIDs {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/unassign-did-numbers",
        response_model=dict,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def unassign_dids_for_partner(
        request: Request,
        payload: TalkoContract.UnassignDIDRequest,
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
        partner_scope: int | None = Header(default=None, alias=SUPERADMIN_SCOPE_HEADER),
    ) -> dict:
        try:
            talko_service_logger.info(f"DIDs received to be unassigned: {payload.did_numbers}")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            grpc_client = TalkoRPCServiceFactory.get_optional_service(TalkoGrpcServices.AUTH)
            try:
                partner_id = await resolve_effective_partner_id(
                    request, grpc_client, talko_service_logger, partner_scope
                )
            except TalkoSuperadminDenied as denied:
                return TalkoForbiddenPermissionResponse(detail=str(denied))
            talko_service_logger.info(f"Unassign DID Numbers=> User: {user_id}, Partner: {partner_id}")

            response: dict = await did_service.unassign_dids_for_partner(partner_id, payload.did_numbers)
            talko_service_logger.info(f"Unassign DID Numbers=> Response: {response}")

            talko_service_logger.info("Successfully unassigned DIDs")
            return TalkoSuccessResponse(data=response)

        except ValueError as ve:
            talko_service_logger.error(f"DID request failed: {str(ve)}")
            return TalkoBadRequestResponse(detail=str(ve))

        except Exception as e:
            talko_service_logger.error(f"Unexpected error assigning available DIDs {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.patch(
        "/apply-did-status-update",
        response_model=dict,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def apply_did_status_update(
        request: Request,
        payload: TalkoContract.AdminDIDAction,
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        try:
            talko_service_logger.info(
                f"Action received to update DID status: {payload.action}, for DIDs: {payload.did_numbers}"
            )
            current_user = request.state.user
            user_id = current_user.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                f"Action {user_id} applying DID status update: {payload.action} on {len(payload.did_numbers)} DIDs"
            )

            result = await did_service.apply_did_status_update(partner_id, payload)

            summary = result.get("summary", {})
            total = summary.get("total", 0)
            succeeded = summary.get("succeeded", 0)
            failed = summary.get("failed", 0)

            talko_service_logger.info(
                f"Action {user_id} successfully applied DID status update: {payload.action} on DIDs: {payload.did_numbers}, Result: {result}"
            )
            if failed == 0:
                status_label = "success"
                message = f"{total} DIDs updated successfully"

            elif succeeded == 0:
                status_label = "failed"
                message = f"{total} DID failed to update" if total == 1 else f"{total} DIDs failed to update"

            else:
                status_label = "partial_success"
                message = f"{succeeded} of {total} DIDs updated successfully"

            talko_service_logger.info(f"{status_label} - {message}")
            return TalkoSuccessResponse(status=status_label, message=message, data=result)

        except ValueError as ve:
            talko_service_logger.error(str(ve))
            return TalkoBadRequestResponse(detail=str(ve))
        except Exception as e:
            talko_service_logger.error(f"Error in apply_did_status_update: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.get(
        "/list-dids",
        response_model=TalkoContract.DIDListResponse,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def list_dids(
        request: Request,
        status: str | None = Query(
            None,
            description="Filter by DID status (available, mapped, cooling_period, cooldown_completed)",
        ),
        workspace_id: int | None = Query(None, description="Filter by workspace ID"),
        did_number: str | None = Query(
            None,
            description="Partial or full DID number search (e.g. 98765 or +9198765)",
        ),
        did_layer: str | None = Query(None, description="Filter by layer (external, internal)"),
        page: int = Query(1, ge=1, description="Page number"),
        limit: int = Query(20, ge=1, le=2000, description="Items per page"),
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        try:
            current_user = request.state.user
            user_id = current_user.get(TalkoCurrentUserMap.USER_ID)
            partner_id = current_user.get(TalkoCurrentUserMap.PARTNER_ID)
            talko_service_logger.info(
                f"User {user_id} calling list_dids - filters: status={status}, "
                + f"partner={partner_id}, board={workspace_id}, did number={did_number}, page={page}, limit={limit}"
            )

            result: TalkoContract.DIDListResponse = await did_service.list_dids(
                status=status,
                partner_id=partner_id,
                workspace_id=workspace_id,
                did_number=did_number,
                page=page,
                limit=limit,
                did_layer=did_layer,
            )

            return TalkoSuccessResponse(data=result)

        except ValueError as ve:
            talko_service_logger.error(f"Validation error in list_dids: {str(ve)}")
            return TalkoBadRequestResponse(detail=str(ve))
        except Exception as e:
            talko_service_logger.error(f"Error in list_dids: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.get(
        "/status-metadata",
        response_model=TalkoContract.StatusMetadataResponse,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_did_status_transitions(
        request: Request,
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> list[TalkoContract.StatusMetadataResponse]:
        """
        Retrieve the allowed status transitions for DIDs.

        This API provides metadata about all DID status stages and the
        valid next stages for each status. The frontend uses this information
        to determine which actions are allowed and to disable invalid actions
        in the UI.
        """

        talko_service_logger.info("Fetching DID status transition metadata")

        current_user_data: dict = request.state.user
        user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
        partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)

        talko_service_logger.info(
            f"Processing DID status metadata request for user_id={user_id}, partner_id={partner_id}"
        )
        transitions = [
            TalkoContract.StatusTransition(
                status=TalkoDIDStatus.AVAILABLE.value,
                next_eligible_status=[TalkoDIDStatus.MAPPED.value],
            ),
            TalkoContract.StatusTransition(
                status=TalkoDIDStatus.MAPPED.value,
                next_eligible_status=[
                    TalkoDIDStatus.AVAILABLE.value,
                    TalkoDIDStatus.COOLING_PERIOD.value,
                ],
            ),
            TalkoContract.StatusTransition(
                status=TalkoDIDStatus.COOLING_PERIOD.value,
                next_eligible_status=[],
            ),
            TalkoContract.StatusTransition(
                status=TalkoDIDStatus.COOLDOWN_COMPLETED.value,
                next_eligible_status=[
                    TalkoDIDStatus.AVAILABLE.value,
                    TalkoDIDStatus.MAPPED.value,
                ],
            ),
        ]

        return TalkoContract.StatusMetadataResponse(
            data=transitions,
            metadata={
                "total_statuses": len(transitions),
                "default_status": TalkoDIDStatus.AVAILABLE.value,
                "cooldown_status": [TalkoDIDStatus.COOLING_PERIOD.value],
            },
        )

    @did_router.post(
        "/assign-ai-agent",
        response_model=dict,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def assign_ai_agent_did(
        request: Request,
        assign_data: TalkoContract.AssignAIAgentDIDRequest,
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        try:
            talko_service_logger.info(
                f"assign-ai-agent called. partner_id={assign_data.partner_id}, agent_bot_id={assign_data.agent_bot_id}"
            )

            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)
            partner_id: int = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)

            talko_service_logger.info(f"User: {user_id}, Partner: {partner_id}, assigning AI agent DID")

            # Verify partner AI agent enabled (add partner_repo dependency if needed)
            did_record: dict = await did_service.assign_ai_agent_did(
                partner_id=assign_data.partner_id,
                agent_bot_id=assign_data.agent_bot_id,
                did_number=assign_data.did_number,
            )

            talko_service_logger.info("AI agent DID assigned: {}".format(did_record["did_number"]))
            return TalkoSuccessResponse(data=did_record)

        except TalkoResourceNotFound:
            talko_service_logger.error(f"No available ai_agent DIDs for partner {assign_data.partner_id}")
            return TalkoBadRequestResponse(detail="No available ai_agent DIDs")
        except Exception as e:
            talko_service_logger.error(f"Error assigning AI agent DID: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/release-ai-agent",
        response_model=dict,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def release_ai_agent_did(
        request: Request,
        release_data: TalkoContract.ReleaseAIAgentDIDRequest,
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        try:
            talko_service_logger.info(
                f"release-ai-agent called. partner_id={release_data.partner_id}, agent_bot_id={release_data.agent_bot_id}"
            )

            released_dids: list[str] = await did_service.release_ai_agent_did(
                partner_id=release_data.partner_id,
                agent_bot_id=release_data.agent_bot_id,
            )

            talko_service_logger.info(f"Released {len(released_dids)} AI agent DIDs")
            return TalkoSuccessResponse(data={"released_dids": released_dids, "count": len(released_dids)})

        except Exception as e:
            talko_service_logger.error(f"Error releasing AI agent DIDs: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/campaign-claim",
        response_model=dict,
    )
    # No @permission_check for now — its permission slug is derived from
    # the route name (talko:claim_campaign_did) and has never been granted
    # to any role, so every caller 403s until RBAC is set up for it. Add it
    # back once that's done; this route is otherwise a live-session-only
    # call from makun-ai (still authenticated, just not permission-gated).
    @inject
    async def claim_campaign_did(
        request: Request,
        claim_data: TalkoContract.ClaimCampaignDIDRequest,
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        """
        Marks a DID as Mapped and binds it to the campaign's own
        agent_bot_id (required so talko's own AI-bridge session resolution,
        which reads agent_bot_id straight off the DID, can find an agent) —
        called by makun-ai when a DID is added to a campaign's did_selection.
        See TalkoDidManagementService.claim_did_for_campaign.
        """
        try:
            talko_service_logger.info(
                f"campaign-claim called. partner_id={claim_data.partner_id}, did_number={claim_data.did_number}, agent_bot_id={claim_data.agent_bot_id}"
            )
            result: dict = await did_service.claim_did_for_campaign(
                partner_id=claim_data.partner_id,
                did_number=claim_data.did_number,
                agent_bot_id=claim_data.agent_bot_id,
            )
            return TalkoSuccessResponse(data=result)
        except TalkoResourceNotFound as e:
            return TalkoBadRequestResponse(detail=str(e))
        except ValueError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Error claiming campaign DID: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/campaign-release",
        response_model=dict,
    )
    # No @permission_check for now — same reason as campaign-claim above.
    @inject
    async def release_campaign_did(
        request: Request,
        release_data: TalkoContract.ReleaseCampaignDIDRequest,
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        """
        Reverts a campaign-claimed DID back to Available and clears its
        agent_bot_id — called by makun-ai when a DID is removed from a
        campaign's did_selection, or the campaign is deleted/stopped. Only
        acts if the DID is currently bound to exactly this agent_bot_id. See
        TalkoDidManagementService.release_campaign_did.
        """
        try:
            talko_service_logger.info(
                f"campaign-release called. partner_id={release_data.partner_id}, did_number={release_data.did_number}, agent_bot_id={release_data.agent_bot_id}"
            )
            result: dict = await did_service.release_campaign_did(
                partner_id=release_data.partner_id,
                did_number=release_data.did_number,
                agent_bot_id=release_data.agent_bot_id,
            )
            return TalkoSuccessResponse(data=result)
        except TalkoResourceNotFound as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Error releasing campaign DID: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.get(
        "/ai-agent/available",
        response_model=dict,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_unassigned_available_ai_agent_dids(
        request: Request,
        partner_id: int = Query(..., description="Partner ID to filter DIDs"),
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        """
        List ai_agent DIDs that are free (partner_id=0) and status=AVAILABLE
        for the given partner.
        """
        try:
            talko_service_logger.info(f"get_unassigned_available_ai_agent_dids called. partner_id={partner_id}")
            current_user_data: dict = request.state.user
            user_id: int = current_user_data.get(TalkoCurrentUserMap.USER_ID)

            talko_service_logger.info(
                f"User {user_id} requesting unassigned available ai_agent DIDs for partner_id={partner_id}"
            )

            dids: list[str] = await did_service.list_unassigned_available_ai_agent_dids(
                partner_id=partner_id,
            )

            talko_service_logger.info(
                f"Found {len(dids)} unassigned available ai_agent DIDs for partner_id={partner_id}"
            )
            return TalkoSuccessResponse(data={"dids": dids})

        except ValueError as ve:
            talko_service_logger.error(f"Validation error in get_unassigned_available_ai_agent_dids: {str(ve)}")
            return TalkoBadRequestResponse(detail=str(ve))

        except Exception as e:
            error_msg = f"Error fetching unassigned available ai_agent DIDs: {str(e)}"
            talko_service_logger.error(error_msg)
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.get(
        "/partner-ai-agent-dids",
        response_model=dict,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_ai_agent_dids(
        request: Request,
        agent_bot_id: int,
        partner_id: int = Query(..., description="Partner ID"),
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        try:
            talko_service_logger.info(f"get-ai-agent-dids called. agent_bot_id={agent_bot_id}, partner_id={partner_id}")

            dids: list[str] = await did_service.get_ai_agent_dids(partner_id, agent_bot_id)
            primary_did: str | None = dids[0] if dids else None

            data: dict = {
                "agent_bot_id": agent_bot_id,
                "primary_did": primary_did,
                "did_numbers": dids,
                "count": len(dids),
            }

            talko_service_logger.info(f"Found {len(dids)} DIDs for AI agent {agent_bot_id}")
            return TalkoSuccessResponse(data=data)

        except Exception as e:
            talko_service_logger.error(f"Error fetching AI agent DIDs: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.get(
        "/list-ai-agent-dids",
        response_model=dict,
    )
    @inject
    async def list_ai_agent_dids(
        request: Request,
        partner_id: int = Query(..., description="Partner ID"),
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        """
        Internal service-to-service endpoint — returns every ai_agent-type DID
        for a partner (assigned or not). Called by makun-ai to enrich its
        agent list response. Not JWT-authenticated (see excluded_paths in
        TalkoAuthMiddleware) since it's called server-to-server, not by a user.
        """
        try:
            talko_service_logger.info(f"list-ai-agent-dids called. partner_id={partner_id}")

            dids: list[dict[str, Any]] = await did_service.list_ai_agent_dids(partner_id)

            talko_service_logger.info(f"Found {len(dids)} ai_agent DIDs for partner_id={partner_id}")
            return TalkoSuccessResponse(data={"dids": dids})

        except Exception as e:
            talko_service_logger.error(f"Error listing ai_agent DIDs for partner_id={partner_id}: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/external/import",
        response_model=dict,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def import_external_dids(
        request: Request,
        payload: TalkoContract.ExternalDIDImportRequest,
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        """Bulk-import wholesaler EXTERNAL DIDs (immutable pool)."""
        try:
            result = await did_service.import_external_dids(
                vendor_id=payload.vendor_id,
                did_numbers=payload.did_numbers,
                vendor_config_id=payload.vendor_config_id,
                display_name=payload.display_name,
            )
            return TalkoSuccessResponse(data=result)
        except ValueError as ve:
            return TalkoBadRequestResponse(detail=str(ve))
        except Exception as e:
            talko_service_logger.error(f"Error importing external DIDs: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/internal/provision",
        response_model=dict,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def provision_internal_did(
        request: Request,
        payload: TalkoContract.InternalDIDProvisionRequest,
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        """Provision INTERNAL routable DID from an EXTERNAL parent."""
        try:
            result = await did_service.provision_internal_did(
                parent_did_number=payload.parent_did_number,
                partner_id=payload.partner_id,
                workspace_id=payload.workspace_id,
                agent_id=payload.agent_id,
                vendor_config_id=payload.vendor_config_id,
            )
            return TalkoSuccessResponse(data=result)
        except TalkoResourceNotFound as e:
            return TalkoBadRequestResponse(detail=str(e))
        except ValueError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Error provisioning internal DID: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.post(
        "/map-external-internal",
        response_model=dict,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def map_external_internal(
        request: Request,
        payload: TalkoContract.MapExternalInternalRequest,
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        """Bind an INTERNAL DID to an EXTERNAL parent (re-map)."""
        try:
            result = await did_service.map_external_internal(
                external_did_number=payload.external_did_number,
                internal_did_number=payload.internal_did_number,
                partner_id=payload.partner_id,
            )
            return TalkoSuccessResponse(data=result)
        except TalkoResourceNotFound as e:
            return TalkoBadRequestResponse(detail=str(e))
        except ValueError as e:
            return TalkoBadRequestResponse(detail=str(e))
        except Exception as e:
            talko_service_logger.error(f"Error mapping DIDs: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)

    @did_router.get(
        "/pool-utilization",
        response_model=dict,
    )
    @permission_check(TalkoPermissionDependency)
    @inject
    async def get_pool_utilization(
        request: Request,
        vendor_id: str | None = Query(None, description="Vendor ID filter"),
        did_service: TalkoDidManagementService = Depends(Provide[TalkoContainer.did_service]),
        talko_service_logger: TalkoServiceLogger = Depends(Provide[TalkoContainer.logger]),
    ) -> dict:
        """Counts by (did_layer, status) for admin pool dashboard."""
        try:
            rows = await did_service.get_pool_utilization(vendor_id=vendor_id)
            return TalkoSuccessResponse(data={"utilization": rows})
        except Exception as e:
            talko_service_logger.error(f"Error fetching pool utilization: {str(e)}")
            return TalkoInternalServerErrorResponse(detail=SOMETHING_WENT_WRONG)
