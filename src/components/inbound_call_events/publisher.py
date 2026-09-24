from src.components.inbound_call_events.connection_manager import TalkoInboundCallEventBroker
from src.components.inbound_call_events.constants import (
    INBOUND_CALL_EVENT_TYPE,
    OUTBOUND_CALL_EVENT_TYPE,
)
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil


class TalkoInboundCallEventPublisher:
    """
    Publishes agent-dialplan resolution results (partner, workspace, DID, agent)
    for an inbound call so subscribed websocket clients get notified in real time.

    Also publishes the same-shaped event for outbound calls (see
    publish_outbound_call) — outbound calls have no dialplan resolution step,
    but dashboard clients need the same real-time notification, over the same
    broker/channel, distinguished only by the "event" field.
    """

    def __init__(self, broker: TalkoInboundCallEventBroker, logger: TalkoServiceLogger):
        self.__broker = broker
        self.__logger = logger

    async def publish_inbound_call(
        self,
        partner_id: int | None,
        workspace_id: int | None,
        dedicated_did: str | None,
        agent_id: int | None,
        agent_ids: list[int] | None = None,
        display_name: str | None = None,
        customer_number: str | None = None,
    ) -> None:
        if not partner_id:
            self.__logger.debug("Skipping inbound call event publish — no partner_id resolved")
            return

        payload = {
            "event": INBOUND_CALL_EVENT_TYPE,
            "partner_id": partner_id,
            "workspace_id": workspace_id,
            "dedicated_did": dedicated_did,
            "agent_id": agent_id,
            "agent_ids": agent_ids or [],
            "display_name": display_name,
            "customer_number": customer_number,
            "timestamp": TalkoDateTimeUtil.get_current_time(),
        }

        try:
            await self.__broker.publish(payload)
            self.__logger.debug(f"Published inbound call event: {payload}")
        except Exception as e:
            self.__logger.error(f"Failed to publish inbound call event for partner {partner_id}: {str(e)}")

    async def publish_outbound_call(
        self,
        partner_id: int | None,
        workspace_id: int | None,
        dedicated_did: str | None,
        agent_id: int | None,
        agent_ids: list[int] | None = None,
        display_name: str | None = None,
        customer_number: str | None = None,
    ) -> None:
        if not partner_id:
            self.__logger.debug("Skipping outbound call event publish — no partner_id resolved")
            return

        payload = {
            "event": OUTBOUND_CALL_EVENT_TYPE,
            "partner_id": partner_id,
            "workspace_id": workspace_id,
            "dedicated_did": dedicated_did,
            "agent_id": agent_id,
            "agent_ids": agent_ids or [],
            "display_name": display_name,
            "customer_number": customer_number,
            "timestamp": TalkoDateTimeUtil.get_current_time(),
        }

        try:
            await self.__broker.publish(payload)
            self.__logger.debug(f"Published outbound call event: {payload}")
        except Exception as e:
            self.__logger.error(f"Failed to publish outbound call event for partner {partner_id}: {str(e)}")

    async def publish_supervisor_event(
        self,
        event: str,
        partner_id: int,
        call_id: str,
        supervisor_id: str = "",
        mode: str = "",
        room_name: str = "",
        extra: dict | None = None,
    ) -> None:
        """Supervisor / attended-transfer signalling over the same WS channel."""
        if not partner_id:
            self.__logger.debug("Skipping supervisor event publish — no partner_id resolved")
            return
        payload = {
            "event": event,
            "partner_id": partner_id,
            "call_id": call_id,
            "supervisor_id": supervisor_id,
            "mode": mode,
            "room_name": room_name,
            "timestamp": TalkoDateTimeUtil.get_current_time(),
        }
        if extra:
            payload.update(extra)
        try:
            await self.__broker.publish(payload)
            self.__logger.debug(f"Published supervisor event: {payload}")
        except Exception as e:
            self.__logger.error(f"Failed to publish supervisor event for partner {partner_id}: {str(e)}")
