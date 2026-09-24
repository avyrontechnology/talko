import random
from dataclasses import dataclass
from typing import Any

from src.components.call_agent_map.repository import TalkoAgentMappingRepository
from src.components.call_management.constant import ORDERBY, SIMULTANEOUS
from src.components.call_management.enums import TalkoInboundType
from src.components.cdr.entity_fields import derive_entity_fields


@dataclass
class TalkoTransferTarget:
    type: str  # "number" | "agent"
    data: list[str]
    ring_type: str = SIMULTANEOUS
    skip_active: bool = False
    # Set only when reassign_inactive_agent kicked in and swapped the caller's
    # agent_id for a different, active one — lets callers update TalkoCDR/event
    # metadata to the agent actually being dialed.
    resolved_agent_id: int | None = None
    # Reassignment bookkeeping (external CRM confirmation removed):
    # priority-2 override slot for the TalkoCDR's lead_id/entity_id, on top
    # of whatever the caller already had on record (priority 1). Always None
    # for now — kept so the field contract is unchanged.
    reassigned_lead_id: int | None = None


class TalkoAgentDialPlanResolver:
    """
    Decides whether to transfer to normal phone numbers or to cloud phonic / agent extensions.
    Resolves from Talko's own agent mappings; external CRM lookups removed.
    """

    ACTIVE_STATUS = "Active"

    def __init__(
        self,
        maglo_client=None,
        agent_mapping_repo: TalkoAgentMappingRepository = None,
        logger=None,
        user_service_client=None,
    ):
        # maglo_client kept as an accepted-but-ignored kwarg for backward
        # compatibility with existing constructions; Maglo integration removed.
        self.__agent_mapping_repo = agent_mapping_repo
        self.__logger = logger
        self.__user_service_client = user_service_client

    async def resolve_for_single_agent(
        self,
        partner_id: int,
        workspace_id: int,
        agent_id: int,
        fallback_agent_number: str | None = None,
        reassign_inactive_agent: bool = False,
        customer_number: str | None = None,
    ) -> TalkoTransferTarget:
        """Resolve transfer target for one known agent (usually from existing TalkoCDR)"""
        self.__logger.debug(f"Resolving dialplan for single agent {agent_id} (partner {partner_id})")

        resolved_agent_id: int | None = None
        reassigned_lead_id: int | None = None
        if reassign_inactive_agent and await self._is_agent_inactive(agent_id):
            new_agent_id, reassigned_lead_id = await self._reassign_to_active_agent(
                partner_id, workspace_id, agent_id, customer_number
            )
            if new_agent_id:
                agent_id = new_agent_id
                resolved_agent_id = new_agent_id

        is_cloud_enabled, extension, agent_id, agent_name, agent_number = await self._get_cloud_phonic_info(
            partner_id, workspace_id, agent_id
        )

        # No live directory exists anymore — resolve the (possibly
        # reassigned) agent's board number from Talko's own mappings so a
        # reassigned call still rings someone.
        if not agent_number and resolved_agent_id is not None:
            agent_number = await self._board_number(partner_id, workspace_id, resolved_agent_id)

        self.__logger.debug(
            f"Cloud phonic info for agent {agent_id}: is_cloud_enabled={is_cloud_enabled}, extension={extension}, agent_name={agent_name}, agent_number={agent_number}"
        )

        if is_cloud_enabled and extension:
            self.__logger.debug(
                f"Transferring to cloud phonic extension {extension} for agent {agent_id} (partner {partner_id})"
            )
            return TalkoTransferTarget(
                type="agent",
                data=[extension],
                ring_type=SIMULTANEOUS,
                skip_active=False,
                resolved_agent_id=resolved_agent_id,
                reassigned_lead_id=reassigned_lead_id,
            )

        # Fallback to normal phone number. Prefer the freshly-looked-up
        # number for the (possibly reassigned) agent over the caller-supplied
        # fallback — the fallback comes from a TalkoCDR field that only gets set
        # once and then copied forward on every later call, so it goes stale
        # whenever the agent's number changes or the assigned agent changes.
        # Only fall back to it when no fresher number is on record.
        number_to_use = agent_number or fallback_agent_number

        if number_to_use:
            self.__logger.debug(
                f"Transferring to fallback agent number {number_to_use} for agent {agent_id} (partner {partner_id})"
            )
            return TalkoTransferTarget(
                type="number",
                data=[number_to_use],
                ring_type=SIMULTANEOUS,
                skip_active=False,
                resolved_agent_id=resolved_agent_id,
                reassigned_lead_id=reassigned_lead_id,
            )

        self.__logger.warning(f"No valid target for agent {agent_id} (partner {partner_id})")
        return TalkoTransferTarget(
            type="number",
            data=[],
            resolved_agent_id=resolved_agent_id,
            reassigned_lead_id=reassigned_lead_id,
        )

    async def resolve_inbound_no_cdr(
        self,
        customer_number: str,
        call_to_number: str,
        partner_id: int,
        workspace_id: int,
        vendor_id: str | None = None,
        vendor_config_id: str | None = None,
        create_lead: bool | None = False,
        reassign_inactive_agent: bool = False,
        enable_inbound_round_robin: bool = False,
        inbound_round_robin_index: int = 0,
    ) -> dict[str, Any]:
        """
        Main entry point for no-TalkoCDR inbound logic.
        Returns dict ready for TalkoCDR creation and dialplan response.
        """
        self.__logger.info(
            f"Resolving inbound no-TalkoCDR call from {customer_number} to DID {call_to_number} "
            + f"(partner {partner_id}, board {workspace_id})"
        )

        assigned_agent_id: int | None = None
        lead_id: int | None = None
        lead_name: str | None = None

        if create_lead:
            lead_id, lead_name, assigned_agent_id = await self._get_or_create_lead(
                customer_number, partner_id, workspace_id
            )

            self.__logger.info(f"Lead resolved: id={lead_id}, name={lead_name}, assigned_agent_id={assigned_agent_id}")

        # Step 2: Resolve transfer target and agent list
        inbound_round_robin_next_index: int | None = None
        if assigned_agent_id:
            target, agent_ids_list = await self._resolve_single_assigned_agent(
                partner_id,
                workspace_id,
                assigned_agent_id,
                reassign_inactive_agent=reassign_inactive_agent,
                customer_number=customer_number,
            )
            # Reflect a possible reassignment so the TalkoCDR and event metadata
            # record the agent actually being dialed, not the stale owner.
            if agent_ids_list:
                assigned_agent_id = agent_ids_list[0]["agent_id"]
            agent_number = agent_ids_list[0]["agent_number"] if agent_ids_list and len(agent_ids_list) == 1 else None
            self.__logger.info(f"Assigned agent resolved: id={assigned_agent_id}, number={agent_number}")
        else:
            target, agent_ids_list, inbound_round_robin_next_index = await self._resolve_all_workspace_agents(
                partner_id,
                workspace_id,
                enable_inbound_round_robin=enable_inbound_round_robin,
                inbound_round_robin_index=inbound_round_robin_index,
            )
            if enable_inbound_round_robin and agent_ids_list:
                # Round robin resolved exactly the cursor agent — report it
                # as the call's agent (id + number) like the assigned-agent
                # flow does, instead of a null agent with a full board list.
                assigned_agent_id = agent_ids_list[0]["agent_id"]
                agent_number = agent_ids_list[0].get("agent_number") or agent_ids_list[0].get("cloud_agent_number")
            else:
                agent_number = None

        self.__logger.info(f"Transfer target resolved: type={target.type}, data={target.data}")

        # Step 3: Final fallback if nothing resolved
        if not target:
            self.__logger.warning(
                f"No agent resolved for {customer_number} → {call_to_number}. " + "Falling back to empty transfer."
            )
            target = TalkoTransferTarget(type="number", data=[])
            agent_ids_list = []

        # Priority 1: the lead_id already resolved via _get_or_create_lead.
        # Priority 2: reassigned_lead_id override when present.
        if target.reassigned_lead_id:
            lead_id = target.reassigned_lead_id

        entity_fields = derive_entity_fields(
            lead_id=lead_id,
            lead_name=lead_name,
        )

        return {
            "lead_id": entity_fields["lead_id"],
            "lead_name": entity_fields["lead_name"],
            "entity_type": entity_fields["entity_type"],
            "entity_id": entity_fields["entity_id"],
            "entity_name": entity_fields["entity_name"],
            "agent_id": assigned_agent_id,
            "agent_number": agent_number or None,
            "agent_ids": agent_ids_list,
            "target": target,
            "partner_id": partner_id,
            "workspace_id": workspace_id,
            "vendor_id": vendor_id,
            "vendor_config_id": vendor_config_id,
            "inbound_round_robin_next_index": inbound_round_robin_next_index,
        }

    async def _resolve_single_assigned_agent(
        self,
        partner_id: int,
        workspace_id: int,
        agent_id: int,
        reassign_inactive_agent: bool = False,
        customer_number: str | None = None,
    ) -> tuple[TalkoTransferTarget, list[dict[str, Any | None]]]:
        """Handle case when lead has one assigned agent."""
        self.__logger.debug(f"Resolving single assigned agent {agent_id} (partner {partner_id})")

        reassigned_lead_id: int | None = None
        reassigned = False
        if reassign_inactive_agent and await self._is_agent_inactive(agent_id):
            new_agent_id, reassigned_lead_id = await self._reassign_to_active_agent(
                partner_id, workspace_id, agent_id, customer_number
            )
            if new_agent_id:
                agent_id = new_agent_id
                reassigned = True

        is_cloud, extension, _, _, agent_number = await self._get_cloud_phonic_info(partner_id, workspace_id, agent_id)

        self.__logger.debug(
            f"Cloud phonic info for agent {agent_id}: is_cloud_enabled={is_cloud}, extension={extension}, agent_number={agent_number}"
        )

        if agent_number is None and reassigned:
            # Reassigned peer has no live number — use its board number from
            # Talko's mappings so the call still rings someone. Untouched
            # agents keep the old behavior (no extra DB hit).
            agent_number = await self._board_number(partner_id, workspace_id, agent_id)

        if is_cloud and extension:
            target = TalkoTransferTarget(
                type="agent",
                data=[extension],
                ring_type=SIMULTANEOUS,
                skip_active=False,
                reassigned_lead_id=reassigned_lead_id,
            )
            cloud_num = extension
        else:
            target = TalkoTransferTarget(
                type="number",
                data=[agent_number] if agent_number else [],
                ring_type=SIMULTANEOUS,
                skip_active=False,
                reassigned_lead_id=reassigned_lead_id,
            )
            cloud_num = None

        self.__logger.debug(f"Resolved target for agent {agent_id}: type={target.type}, data={target.data}")
        agent_ids_list = [
            {
                "agent_id": agent_id,
                "agent_number": agent_number,
                "cloud_agent_number": cloud_num,
            }
        ]

        self.__logger.debug(f"Agent IDs list: {agent_ids_list}")

        return target, agent_ids_list

    async def _resolve_all_workspace_agents(
        self,
        partner_id: int,
        workspace_id: int,
        enable_inbound_round_robin: bool = False,
        inbound_round_robin_index: int = 0,
    ) -> tuple[TalkoTransferTarget, list[dict[str, Any | None]], int | None]:
        """Handle case when no assigned agent → ring board agents.

        Rings everyone at once by default. When inbound round robin is
        enabled, only the cursor agent is rung (single agent_id +
        agent_number reported) and the cursor advances by one, so
        consecutive unknown inbound calls distribute one-per-agent.
        Returns the advanced cursor for persistence.
        """
        self.__logger.debug(f"Resolving all agents for workspace {workspace_id} (partner {partner_id})")
        agents = await self.__agent_mapping_repo.get_agents_by_workspace_id_and_partner_id(
            workspace_id=workspace_id, partner_id=partner_id
        )

        if not agents:
            self.__logger.warning(f"No agents in board {workspace_id} (partner {partner_id})")
            return TalkoTransferTarget(type="number", data=[]), [], None

        self.__logger.debug(f"Found {len(agents)} agents in board {workspace_id} (partner {partner_id})")

        agents_to_ring = await self._filter_active_agents(agents)

        next_index: int | None = None
        ring_type = SIMULTANEOUS
        if enable_inbound_round_robin and agents_to_ring:
            start = inbound_round_robin_index % len(agents_to_ring)
            agents_to_ring = agents_to_ring[start:] + agents_to_ring[:start]
            # Cursor must advance over the FULL active set so the rotation
            # keeps covering every agent — compute before slicing below.
            next_index = (inbound_round_robin_index + 1) % len(agents_to_ring)
            # Round robin rings only the cursor agent (not the whole board
            # in order), so the event/TalkoCDR carry a single agent_id +
            # agent_number.
            agents_to_ring = agents_to_ring[:1]
            ring_type = ORDERBY
            self.__logger.debug(
                "Inbound round robin: partner {} start_index={} next_index={} agent={}".format(
                    partner_id,
                    start,
                    next_index,
                    agents_to_ring[0].get("agent_id"),
                )
            )

        transfer_data: list[str] = []
        agent_ids_list: list[dict[str, Any | None]] = []
        any_cloud = False

        for agent in agents_to_ring:
            agent_id = agent.get("agent_id")
            regular_number = agent.get("agent_number")

            is_cloud, extension, _, _, _ = await self._get_cloud_phonic_info(partner_id, workspace_id, agent_id)

            if is_cloud and extension:
                transfer_data.append(extension)
                any_cloud = True
                cloud_num = extension
            else:
                if regular_number:
                    transfer_data.append(regular_number)
                cloud_num = None

            agent_ids_list.append(
                {
                    "agent_id": agent_id,
                    "agent_number": regular_number,
                    "cloud_agent_number": cloud_num,
                }
            )

        self.__logger.debug(f"Resolved transfer data: {transfer_data}, any_cloud={any_cloud}")

        target_type = "agent" if any_cloud else "number"

        target = TalkoTransferTarget(
            type=target_type,
            data=transfer_data,
            ring_type=ring_type,
            skip_active=False,
        )

        self.__logger.debug(f"Final resolved target: type={target.type}, data={target.data}")

        return target, agent_ids_list, next_index

    async def _filter_active_agents(self, agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Narrows the board's agent list down to ones currently "Active", using a
        single bulk availability lookup. Fails open: if the lookup errors out,
        or an agent has no status on record, or filtering would leave nobody to
        ring, the full original list is used so an inbound call is never dropped.
        """
        self.__logger.debug(f"Entering _filter_active_agents with {len(agents)} agent(s): {agents}")

        if not self.__user_service_client:
            self.__logger.debug(
                "No user_service_client configured. Skipping availability "
                f"filtering and ringing all {len(agents)} agent(s)."
            )
            return agents

        agent_ids = [agent.get("agent_id") for agent in agents]
        self.__logger.debug(f"Fetching availability status for agent_ids: {agent_ids}")

        try:
            availability_map = await self.__user_service_client.get_users_availability_status(agent_ids)
            self.__logger.debug(f"Received availability map for agent_ids {agent_ids}: {availability_map}")
        except Exception as exc:
            self.__logger.warning(
                f"Failed to fetch agent availability status for {agent_ids}: {exc}. Ringing full agent list."
            )
            return agents

        active_agents = [
            agent
            for agent in agents
            if availability_map.get(agent.get("agent_id"), self.ACTIVE_STATUS) == self.ACTIVE_STATUS
        ]
        self.__logger.debug(f"Computed active_agents ({len(active_agents)} of {len(agents)}): {active_agents}")

        if not active_agents:
            self.__logger.info(f"No agents with Active status among {agent_ids}. Ringing full agent list.")
            return agents

        self.__logger.debug(
            f"Filtered to {len(active_agents)} active agent(s) out of {len(agents)}: {availability_map}"
        )
        self.__logger.debug(f"Returning active_agents from _filter_active_agents: {active_agents}")
        return active_agents

    async def _is_agent_inactive(self, agent_id: int) -> bool:
        """
        True only on a confirmed non-Active status. Any uncertainty (no
        client configured, lookup failure, missing status) defaults to
        False so an assigned agent is never bypassed without proof they're
        actually offline.
        """
        if not self.__user_service_client:
            return False

        try:
            availability_map = await self.__user_service_client.get_users_availability_status([agent_id])
        except Exception as exc:
            self.__logger.warning(f"Failed to fetch availability for agent {agent_id}: {exc}. Treating as active.")
            return False

        resolved_status = availability_map.get(agent_id, self.ACTIVE_STATUS)
        self.__logger.debug(
            f"Availability check for agent {agent_id}: resolved_status={resolved_status!r}, "
            f"present_in_response={agent_id in availability_map}, raw_map={availability_map}"
        )

        return resolved_status != self.ACTIVE_STATUS

    async def _board_number(self, partner_id: int, workspace_id: int, agent_id: int) -> str | None:
        """Board number for an agent from Talko's own mappings (None if unknown)."""
        try:
            agents = await self.__agent_mapping_repo.get_agents_by_workspace_id_and_partner_id(
                workspace_id=workspace_id, partner_id=partner_id
            )
            for agent in agents or []:
                if agent.get("agent_id") == agent_id:
                    return agent.get("agent_number") or None
        except Exception as exc:
            self.__logger.warning(f"Board number lookup failed for agent {agent_id}: {exc}")
        return None

    async def _reassign_to_active_agent(
        self,
        partner_id: int,
        workspace_id: int,
        current_agent_id: int,
        customer_number: str | None,
    ) -> tuple[int | None, int | None]:
        """
        Picks a replacement from the board's other active agents.
        Returns (new_agent_id, reassigned_lead_id) — both None if no other
        active agent is available; reassigned_lead_id is always None now
        (external confirmation removed — the agent swap still stands).
        """
        agents = await self.__agent_mapping_repo.get_agents_by_workspace_id_and_partner_id(
            workspace_id=workspace_id, partner_id=partner_id
        )
        candidates = [a for a in agents if a.get("agent_id") != current_agent_id]

        if not candidates:
            self.__logger.warning(
                f"Assigned agent {current_agent_id} inactive but no other agents on board {workspace_id} "
                f"(partner {partner_id}); keeping original assignment."
            )
            return None, None

        active_candidates = await self._filter_active_agents(candidates)

        # Random rather than round-robin: selection must stay correct across
        # multiple service instances without a shared cursor.
        new_agent = random.choice(active_candidates)
        new_agent_id = new_agent.get("agent_id")

        self.__logger.info(
            f"Reassigning lead from inactive agent {current_agent_id} to agent {new_agent_id} (partner {partner_id}, board {workspace_id})"
        )

        reassigned_lead_id: int | None = None
        if customer_number and new_agent_id:
            reassigned_lead_id = await self._notify_maglo_reassignment(
                customer_number, partner_id, workspace_id, new_agent_id
            )

        return new_agent_id, reassigned_lead_id

    async def _notify_maglo_reassignment(
        self,
        customer_number: str,
        partner_id: int,
        workspace_id: int,
        new_agent_id: int,
    ) -> int | None:
        """Maglo integration removed — reassignment is local-only now."""
        self.__logger.info(
            f"Skipping external reassignment notify for {customer_number} (Maglo removed); agent swap stands."
        )
        return None

    def map_transfer_to_inbound_fields(self, target: TalkoTransferTarget | None) -> tuple[str, str | None]:
        """
        Maps TalkoTransferTarget to inbound_type string and cloud_agent_number.

        Args:
            target: TalkoTransferTarget object (or None)

        Returns:
            Tuple[str, Optional[str]]: (inbound_type_str, cloud_agent_number)
        """
        if not target:
            return TalkoInboundType.PHONE_NUMBER.value, None

        if target.type == "number":
            return TalkoInboundType.PHONE_NUMBER.value, None

        if target.type == "agent":
            cloud_number = target.data[0] if target.data else None
            return TalkoInboundType.SOFT_PHONE.value, cloud_number

        self.__logger.warning(f"Unknown transfer type '{target.type}' - defaulting to phone_number")
        return TalkoInboundType.PHONE_NUMBER.value, None

    async def _get_or_create_lead(
        self,
        customer_number: str,
        partner_id: int,
        workspace_id: int,
    ) -> tuple[int | None, str | None, int | None]:
        """Maglo integration removed — no external lead store exists.

        Returns (None, None, None) so callers proceed with workspace-agent
        routing (same as the old Maglo-failure path)."""
        self.__logger.info(f"Skipping external lead upsert for {customer_number} (Maglo removed)")
        return None, None, None

    async def _get_cloud_phonic_info(
        self, partner_id: int, workspace_id: int, agent_id: int
    ) -> tuple[bool, str | None, int | None, str | None, str | None]:
        """Maglo integration removed — cloud-phonic lookup unavailable.

        Returns disabled/empty (same as the old Maglo-failure path), so
        callers fall back to regular phone numbers."""
        self.__logger.debug(f"Skipping cloud phonic lookup for agent {agent_id} (Maglo removed)")
        return False, None, None, None, None


class TalkoDialplanResponseBuilder:
    """
    Helper class that formats the final dialplan response payload.
    Centralizes all response structure logic for consistency and testability.
    """

    @staticmethod
    def build_transfer_response(target: TalkoTransferTarget | None) -> list[dict]:
        """
        Builds the standard transfer block based on a TalkoTransferTarget.
        Returns a list with one transfer object (as expected by the API).
        """
        if not target:
            return TalkoDialplanResponseBuilder.build_empty_response()

        return [
            {
                "transfer": {
                    "type": target.type,
                    "data": target.data or [],
                    "ring_type": target.ring_type,
                    "skip_active": target.skip_active,
                }
            }
        ]

    @staticmethod
    def build_empty_response() -> list[dict]:
        """
        Returns the default/fallback empty transfer response.
        Used when no agents or no valid target is resolved.
        """
        return [
            {
                "transfer": {
                    "type": "number",
                    "data": [],
                    "ring_type": SIMULTANEOUS,
                    "skip_active": False,
                }
            }
        ]
