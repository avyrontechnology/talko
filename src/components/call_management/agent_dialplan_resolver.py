import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.components.call_agent_map.repository import TalkoAgentMappingRepository
from src.components.call_management.constant import ORDERBY, SIMULTANEOUS
from src.components.call_management.enums import TalkoInboundType
from src.components.cdr.entity_fields import derive_entity_fields
from src.components.integrations.console.maglo_constants import TalkoMagloApiConstants


@dataclass
class TalkoTransferTarget:
    type: str  # "number" | "agent"
    data: List[str]
    ring_type: str = SIMULTANEOUS
    skip_active: bool = False
    # Set only when reassign_inactive_agent kicked in and swapped the caller's
    # agent_id for a different, active one — lets callers update TalkoCDR/event
    # metadata to the agent actually being dialed.
    resolved_agent_id: Optional[int] = None
    # Set only when a reassignment happened AND Maglo confirmed the lead
    # tied to that phone number (its lead_request_id) — priority-2 override
    # for the TalkoCDR's lead_id/entity_id, on top of whatever the caller already
    # had on record (priority 1).
    reassigned_lead_id: Optional[int] = None


class TalkoAgentDialPlanResolver:
    """
    Decides whether to transfer to normal phone numbers or to cloud phonic / agent extensions.
    Fetches configuration directly from Maglo (Tata Smartflo) at runtime — no caching.
    """

    ACTIVE_STATUS = "Active"

    def __init__(
        self,
        maglo_client,
        agent_mapping_repo: TalkoAgentMappingRepository,
        logger,
        user_service_client=None,
    ):
        self.__maglo_client = maglo_client
        self.__agent_mapping_repo = agent_mapping_repo
        self.__logger = logger
        self.__user_service_client = user_service_client

    async def resolve_for_single_agent(
        self,
        partner_id: int,
        service_board_id: int,
        agent_id: int,
        fallback_agent_number: Optional[str] = None,
        reassign_inactive_agent: bool = False,
        customer_number: Optional[str] = None,
    ) -> TalkoTransferTarget:
        """Resolve transfer target for one known agent (usually from existing TalkoCDR)"""
        self.__logger.debug(
            "Resolving dialplan for single agent {} (partner {})".format(
                agent_id, partner_id
            )
        )

        resolved_agent_id: Optional[int] = None
        reassigned_lead_id: Optional[int] = None
        if reassign_inactive_agent and await self._is_agent_inactive(agent_id):
            new_agent_id, reassigned_lead_id = await self._reassign_to_active_agent(
                partner_id, service_board_id, agent_id, customer_number
            )
            if new_agent_id:
                agent_id = new_agent_id
                resolved_agent_id = new_agent_id

        is_cloud_enabled, extension, agent_id, agent_name, agent_number = (
            await self._get_cloud_phonic_info(partner_id, service_board_id, agent_id)
        )

        self.__logger.debug(
            "Cloud phonic info for agent {}: is_cloud_enabled={}, extension={}, agent_name={}, agent_number={}".format(
                agent_id, is_cloud_enabled, extension, agent_name, agent_number
            )
        )

        if is_cloud_enabled and extension:
            self.__logger.debug(
                "Transferring to cloud phonic extension {} for agent {} (partner {})".format(
                    extension, agent_id, partner_id
                )
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
        # Only fall back to it when Maglo has no number on record at all.
        number_to_use = agent_number or fallback_agent_number

        if number_to_use:
            self.__logger.debug(
                "Transferring to fallback agent number {} for agent {} (partner {})".format(
                    number_to_use, agent_id, partner_id
                )
            )
            return TalkoTransferTarget(
                type="number",
                data=[number_to_use],
                ring_type=SIMULTANEOUS,
                skip_active=False,
                resolved_agent_id=resolved_agent_id,
                reassigned_lead_id=reassigned_lead_id,
            )

        self.__logger.warning(
            "No valid target for agent {} (partner {})".format(agent_id, partner_id)
        )
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
        service_board_id: int,
        vendor_id: Optional[str] = None,
        vendor_config_id: Optional[str] = None,
        create_lead: Optional[bool] = False,
        reassign_inactive_agent: bool = False,
        enable_inbound_round_robin: bool = False,
        inbound_round_robin_index: int = 0,
    ) -> Dict[str, Any]:
        """
        Main entry point for no-TalkoCDR inbound logic.
        Returns dict ready for TalkoCDR creation and dialplan response.
        """
        self.__logger.info(
            "Resolving inbound no-TalkoCDR call from {} to DID {} ".format(
                customer_number, call_to_number
            )
            + "(partner {}, board {})".format(partner_id, service_board_id)
        )

        assigned_agent_id: Optional[int] = None
        lead_id: Optional[int] = None
        lead_name: Optional[str] = None

        if create_lead:
            lead_id, lead_name, assigned_agent_id = await self._get_or_create_lead(
                customer_number, partner_id, service_board_id
            )

            self.__logger.info(
                "Lead resolved: id={}, name={}, assigned_agent_id={}".format(
                    lead_id, lead_name, assigned_agent_id
                )
            )

        # Step 2: Resolve transfer target and agent list
        inbound_round_robin_next_index: Optional[int] = None
        if assigned_agent_id:
            target, agent_ids_list = await self._resolve_single_assigned_agent(
                partner_id,
                service_board_id,
                assigned_agent_id,
                reassign_inactive_agent=reassign_inactive_agent,
                customer_number=customer_number,
            )
            # Reflect a possible reassignment so the TalkoCDR and event metadata
            # record the agent actually being dialed, not the stale owner.
            if agent_ids_list:
                assigned_agent_id = agent_ids_list[0]["agent_id"]
            agent_number = (
                agent_ids_list[0]["agent_number"]
                if agent_ids_list and len(agent_ids_list) == 1
                else None
            )
            self.__logger.info(
                "Assigned agent resolved: id={}, number={}".format(
                    assigned_agent_id, agent_number
                )
            )
        else:
            target, agent_ids_list, inbound_round_robin_next_index = (
                await self._resolve_all_service_board_agents(
                    partner_id,
                    service_board_id,
                    enable_inbound_round_robin=enable_inbound_round_robin,
                    inbound_round_robin_index=inbound_round_robin_index,
                )
            )
            if enable_inbound_round_robin and agent_ids_list:
                # Round robin resolved exactly the cursor agent — report it
                # as the call's agent (id + number) like the assigned-agent
                # flow does, instead of a null agent with a full board list.
                assigned_agent_id = agent_ids_list[0]["agent_id"]
                agent_number = agent_ids_list[0].get(
                    "agent_number"
                ) or agent_ids_list[0].get("cloud_agent_number")
            else:
                agent_number = None

        self.__logger.info(
            "Transfer target resolved: type={}, data={}".format(
                target.type, target.data
            )
        )

        # Step 3: Final fallback if nothing resolved
        if not target:
            self.__logger.warning(
                "No agent resolved for {} → {}. ".format(
                    customer_number, call_to_number
                )
                + "Falling back to empty transfer."
            )
            target = TalkoTransferTarget(type="number", data=[])
            agent_ids_list = []

        # Priority 1: the lead_id already resolved via _get_or_create_lead.
        # Priority 2: if a reassignment happened this call and Maglo confirmed
        # a lead_request_id, that's the freshest data — use it instead.
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
            "service_board_id": service_board_id,
            "vendor_id": vendor_id,
            "vendor_config_id": vendor_config_id,
            "inbound_round_robin_next_index": inbound_round_robin_next_index,
        }

    async def _resolve_single_assigned_agent(
        self,
        partner_id: int,
        service_board_id: int,
        agent_id: int,
        reassign_inactive_agent: bool = False,
        customer_number: Optional[str] = None,
    ) -> Tuple[TalkoTransferTarget, List[Dict[str, Optional[Any]]]]:
        """Handle case when lead has one assigned agent."""
        self.__logger.debug(
            "Resolving single assigned agent {} (partner {})".format(
                agent_id, partner_id
            )
        )

        reassigned_lead_id: Optional[int] = None
        if reassign_inactive_agent and await self._is_agent_inactive(agent_id):
            new_agent_id, reassigned_lead_id = await self._reassign_to_active_agent(
                partner_id, service_board_id, agent_id, customer_number
            )
            if new_agent_id:
                agent_id = new_agent_id

        is_cloud, extension, _, _, agent_number = await self._get_cloud_phonic_info(
            partner_id, service_board_id, agent_id
        )

        self.__logger.debug(
            "Cloud phonic info for agent {}: is_cloud_enabled={}, extension={}, agent_number={}".format(
                agent_id, is_cloud, extension, agent_number
            )
        )

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

        self.__logger.debug(
            "Resolved target for agent {}: type={}, data={}".format(
                agent_id, target.type, target.data
            )
        )
        agent_ids_list = [
            {
                "agent_id": agent_id,
                "agent_number": agent_number,
                "cloud_agent_number": cloud_num,
            }
        ]

        self.__logger.debug("Agent IDs list: {}".format(agent_ids_list))

        return target, agent_ids_list

    async def _resolve_all_service_board_agents(
        self,
        partner_id: int,
        service_board_id: int,
        enable_inbound_round_robin: bool = False,
        inbound_round_robin_index: int = 0,
    ) -> Tuple[TalkoTransferTarget, List[Dict[str, Optional[Any]]], Optional[int]]:
        """Handle case when no assigned agent → ring board agents.

        Rings everyone at once by default. When inbound round robin is
        enabled, only the cursor agent is rung (single agent_id +
        agent_number reported) and the cursor advances by one, so
        consecutive unknown inbound calls distribute one-per-agent.
        Returns the advanced cursor for persistence.
        """
        self.__logger.debug(
            "Resolving all agents for service board {} (partner {})".format(
                service_board_id, partner_id
            )
        )
        agents = await self.__agent_mapping_repo.get_agents_by_service_board_id_and_partner_id(
            service_board_id=service_board_id, partner_id=partner_id
        )

        if not agents:
            self.__logger.warning(
                "No agents in board {} (partner {})".format(
                    service_board_id, partner_id
                )
            )
            return TalkoTransferTarget(type="number", data=[]), [], None

        self.__logger.debug(
            "Found {} agents in board {} (partner {})".format(
                len(agents), service_board_id, partner_id
            )
        )

        agents_to_ring = await self._filter_active_agents(agents)

        next_index: Optional[int] = None
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

        transfer_data: List[str] = []
        agent_ids_list: List[Dict[str, Optional[Any]]] = []
        any_cloud = False

        for agent in agents_to_ring:
            agent_id = agent.get("agent_id")
            regular_number = agent.get("agent_number")

            is_cloud, extension, _, _, _ = await self._get_cloud_phonic_info(
                partner_id, service_board_id, agent_id
            )

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

        self.__logger.debug(
            "Resolved transfer data: {}, any_cloud={}".format(transfer_data, any_cloud)
        )

        target_type = "agent" if any_cloud else "number"

        target = TalkoTransferTarget(
            type=target_type,
            data=transfer_data,
            ring_type=ring_type,
            skip_active=False,
        )

        self.__logger.debug(
            "Final resolved target: type={}, data={}".format(target.type, target.data)
        )

        return target, agent_ids_list, next_index

    async def _filter_active_agents(
        self, agents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Narrows the board's agent list down to ones currently "Active", using a
        single bulk availability lookup. Fails open: if the lookup errors out,
        or an agent has no status on record, or filtering would leave nobody to
        ring, the full original list is used so an inbound call is never dropped.
        """
        self.__logger.debug(
            "Entering _filter_active_agents with {} agent(s): {}".format(
                len(agents), agents
            )
        )

        if not self.__user_service_client:
            self.__logger.debug(
                "No user_service_client configured. Skipping availability "
                "filtering and ringing all {} agent(s).".format(len(agents))
            )
            return agents

        agent_ids = [agent.get("agent_id") for agent in agents]
        self.__logger.debug(
            "Fetching availability status for agent_ids: {}".format(agent_ids)
        )

        try:
            availability_map = (
                await self.__user_service_client.get_users_availability_status(
                    agent_ids
                )
            )
            self.__logger.debug(
                "Received availability map for agent_ids {}: {}".format(
                    agent_ids, availability_map
                )
            )
        except Exception as exc:
            self.__logger.warning(
                "Failed to fetch agent availability status for {}: {}. "
                "Ringing full agent list.".format(agent_ids, exc)
            )
            return agents

        active_agents = [
            agent
            for agent in agents
            if availability_map.get(agent.get("agent_id"), self.ACTIVE_STATUS)
            == self.ACTIVE_STATUS
        ]
        self.__logger.debug(
            "Computed active_agents ({} of {}): {}".format(
                len(active_agents), len(agents), active_agents
            )
        )

        if not active_agents:
            self.__logger.info(
                "No agents with Active status among {}. Ringing full agent list.".format(
                    agent_ids
                )
            )
            return agents

        self.__logger.debug(
            "Filtered to {} active agent(s) out of {}: {}".format(
                len(active_agents), len(agents), availability_map
            )
        )
        self.__logger.debug(
            "Returning active_agents from _filter_active_agents: {}".format(
                active_agents
            )
        )
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
            availability_map = (
                await self.__user_service_client.get_users_availability_status(
                    [agent_id]
                )
            )
        except Exception as exc:
            self.__logger.warning(
                "Failed to fetch availability for agent {}: {}. "
                "Treating as active.".format(agent_id, exc)
            )
            return False

        resolved_status = availability_map.get(agent_id, self.ACTIVE_STATUS)
        self.__logger.debug(
            "Availability check for agent {}: resolved_status={!r}, "
            "present_in_response={}, raw_map={}".format(
                agent_id,
                resolved_status,
                agent_id in availability_map,
                availability_map,
            )
        )

        return resolved_status != self.ACTIVE_STATUS

    async def _reassign_to_active_agent(
        self,
        partner_id: int,
        service_board_id: int,
        current_agent_id: int,
        customer_number: Optional[str],
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        Picks a replacement from the board's other active agents and notifies
        Maglo of the reassignment, awaiting its response so the confirmed
        lead_request_id can flow back onto this call's TalkoCDR. Returns
        (new_agent_id, reassigned_lead_id) — both None if no other active
        agent is available; reassigned_lead_id is None if the Maglo call
        fails (the agent swap still stands, just without a confirmed lead id).
        """
        agents = await self.__agent_mapping_repo.get_agents_by_service_board_id_and_partner_id(
            service_board_id=service_board_id, partner_id=partner_id
        )
        candidates = [a for a in agents if a.get("agent_id") != current_agent_id]

        if not candidates:
            self.__logger.warning(
                "Assigned agent {} inactive but no other agents on board {} "
                "(partner {}); keeping original assignment.".format(
                    current_agent_id, service_board_id, partner_id
                )
            )
            return None, None

        active_candidates = await self._filter_active_agents(candidates)

        # Random rather than round-robin: selection must stay correct across
        # multiple service instances without a shared cursor.
        new_agent = random.choice(active_candidates)
        new_agent_id = new_agent.get("agent_id")

        self.__logger.info(
            "Reassigning lead from inactive agent {} to agent {} (partner {}, board {})".format(
                current_agent_id, new_agent_id, partner_id, service_board_id
            )
        )

        reassigned_lead_id: Optional[int] = None
        if customer_number and new_agent_id:
            reassigned_lead_id = await self._notify_maglo_reassignment(
                customer_number, partner_id, service_board_id, new_agent_id
            )

        return new_agent_id, reassigned_lead_id

    async def _notify_maglo_reassignment(
        self,
        customer_number: str,
        partner_id: int,
        service_board_id: int,
        new_agent_id: int,
    ) -> Optional[int]:
        """Notifies Maglo of the reassignment and returns the confirmed
        lead_request_id from its response, or None on failure."""
        try:
            result = await self.__maglo_client.reassign_lead_by_phone(
                phone_number=customer_number,
                partner_id=partner_id,
                service_board_id=service_board_id,
                agent_id=new_agent_id,
            )
            return (result or {}).get("lead_request_id")
        except Exception as exc:
            self.__logger.error(
                "Failed to notify Maglo of lead reassignment to agent {} for {}: {}".format(
                    new_agent_id, customer_number, exc
                )
            )

    def map_transfer_to_inbound_fields(
        self, target: Optional[TalkoTransferTarget]
    ) -> Tuple[str, Optional[str]]:
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

        self.__logger.warning(
            "Unknown transfer type '{}' - defaulting to phone_number".format(
                target.type
            )
        )
        return TalkoInboundType.PHONE_NUMBER.value, None

    async def _get_or_create_lead(
        self,
        customer_number: str,
        partner_id: int,
        service_board_id: int,
    ) -> Tuple[Optional[int], Optional[str], Optional[int]]:
        try:
            response_data = await self.__maglo_client.upsert_ivr_lead(
                partner_id=partner_id,
                service_board_id=service_board_id,
                phone_number=customer_number,
            )

            self.__logger.debug(
                "Maglo lead upsert response for number {}: {}".format(
                    customer_number, response_data
                )
            )

            lead_id = response_data.get(TalkoMagloApiConstants.FIELD_AGENT_ID) or None
            lead_name = response_data.get(TalkoMagloApiConstants.FIELD_AGENT_NAME) or ""
            lead_request_id = (
                response_data.get(TalkoMagloApiConstants.FIELD_LEAD_REQUEST_ID) or None
            )

            assigned_agent_id = response_data.get(
                TalkoMagloApiConstants.LEAD_RESPONSE_ASSIGNED_TO
            )

            self.__logger.info(
                "Lead upsert result: lead_id={}, lead_request_id={}, name={}, assigned_to={}".format(
                    lead_id, lead_request_id, lead_name, assigned_agent_id
                )
            )

            id_data = lead_request_id if lead_request_id is not None else lead_id

            return id_data, lead_name, assigned_agent_id

        except Exception as e:
            self.__logger.error(
                "Lead upsert failed for {}: {}".format(customer_number, str(e))
            )
            return None, None, None

    async def _get_cloud_phonic_info(
        self, partner_id: int, service_board_id: int, agent_id: int
    ) -> Tuple[bool, Optional[str], Optional[int], Optional[str], Optional[str]]:
        """Fetch from Maglo whether cloud phonic is enabled and get the extension username"""
        try:
            self.__logger.debug(
                "Fetching cloud phonic info for agent {} (partner {})".format(
                    agent_id, partner_id
                )
            )

            response = await self.__maglo_client.get_agent_details(
                agent_id=agent_id,
                service_board_id=service_board_id,
            )

            self.__logger.debug(
                "Maglo agent details response for agent {}: {}".format(
                    agent_id, response
                )
            )

            # Check if response is a dict and extract the nested 'data' key
            if isinstance(response, dict) and "data" in response:
                data = response.get("data") or {}
            else:
                data = response if isinstance(response, dict) else {}

            self.__logger.debug(
                "Extracted data for agent {}: {}".format(agent_id, data)
            )

            # Now these .get() calls will find the nested values correctly
            is_cloud_enabled = bool(data.get("internet_calling_enable", False))
            extension = data.get("extension") or None
            agent_id_val = data.get("id")
            agent_name = data.get("name")
            agent_number = data.get("number")

            self.__logger.debug(
                "Parsed cloud phonic info for agent {}: is_cloud_enabled={}, extension={}, agent_name={}, agent_number={}".format(
                    agent_id_val, is_cloud_enabled, extension, agent_name, agent_number
                )
            )
            return is_cloud_enabled, extension, agent_id_val, agent_name, agent_number

        except ValueError as ve:
            # TalkoMagloClient raises ValueError on non-200 status (including 404)
            error_str = str(ve)
            if "404" in error_str and "Service board with id" in error_str:
                self.__logger.warning(
                    "Maglo service board {} not found for agent {} (partner {}) → ".format(
                        service_board_id, agent_id, partner_id
                    )
                    + "falling back to regular phone number"
                )
            else:
                self.__logger.error(
                    "Maglo API error for agent {}: {}".format(agent_id, error_str)
                )

            return False, None, None, None, None

        except Exception as e:
            self.__logger.error(
                "Failed to fetch cloud phonic info for agent {} (partner {}): {}".format(
                    agent_id, partner_id, str(e)
                )
            )
            return False, None, None, None, None


class TalkoDialplanResponseBuilder:
    """
    Helper class that formats the final dialplan response payload.
    Centralizes all response structure logic for consistency and testability.
    """

    @staticmethod
    def build_transfer_response(target: Optional[TalkoTransferTarget]) -> List[dict]:
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
    def build_empty_response() -> List[dict]:
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
