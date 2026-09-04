from typing import List, Optional

from src.components.inbound_call_events.connection_manager import InboundCallEventBroker
from src.components.inbound_call_events.constants import (
    INBOUND_CALL_EVENT_TYPE,
    OUTBOUND_CALL_EVENT_TYPE,
)
from src.loggers.holler_service_logger import HollerServiceLogger
from src.utils.datetime_util import DateTimeUtil


class InboundCallEventPublisher:
    """
    Publishes agent-dialplan resolution results (partner, service board, DID, agent)
    for an inbound call so subscribed websocket clients get notified in real time.

    Also publishes the same-shaped event for outbound calls (see
    publish_outbound_call) — outbound calls have no dialplan resolution step,
    but dashboard clients need the same real-time notification, over the same
    broker/channel, distinguished only by the "event" field.
    """

    def __init__(self, broker: InboundCallEventBroker, logger: HollerServiceLogger):
        self.__broker = broker
        self.__logger = logger

    async def publish_inbound_call(
        self,
        partner_id: Optional[int],
        service_board_id: Optional[int],
        dedicated_did: Optional[str],
        agent_id: Optional[int],
        agent_ids: Optional[List[int]] = None,
        display_name: Optional[str] = None,
        customer_number: Optional[str] = None,
    ) -> None:
        if not partner_id:
            self.__logger.debug(
                "Skipping inbound call event publish — no partner_id resolved"
            )
            return

        payload = {
            "event": INBOUND_CALL_EVENT_TYPE,
            "partner_id": partner_id,
            "service_board_id": service_board_id,
            "dedicated_did": dedicated_did,
            "agent_id": agent_id,
            "agent_ids": agent_ids or [],
            "display_name": display_name,
            "customer_number": customer_number,
            "timestamp": DateTimeUtil.get_current_time(),
        }

        try:
            await self.__broker.publish(payload)
            self.__logger.debug("Published inbound call event: {}".format(payload))
        except Exception as e:
            self.__logger.error(
                "Failed to publish inbound call event for partner {}: {}".format(
                    partner_id, str(e)
                )
            )

    async def publish_outbound_call(
        self,
        partner_id: Optional[int],
        service_board_id: Optional[int],
        dedicated_did: Optional[str],
        agent_id: Optional[int],
        agent_ids: Optional[List[int]] = None,
        display_name: Optional[str] = None,
        customer_number: Optional[str] = None,
    ) -> None:
        if not partner_id:
            self.__logger.debug(
                "Skipping outbound call event publish — no partner_id resolved"
            )
            return

        payload = {
            "event": OUTBOUND_CALL_EVENT_TYPE,
            "partner_id": partner_id,
            "service_board_id": service_board_id,
            "dedicated_did": dedicated_did,
            "agent_id": agent_id,
            "agent_ids": agent_ids or [],
            "display_name": display_name,
            "customer_number": customer_number,
            "timestamp": DateTimeUtil.get_current_time(),
        }

        try:
            await self.__broker.publish(payload)
            self.__logger.debug("Published outbound call event: {}".format(payload))
        except Exception as e:
            self.__logger.error(
                "Failed to publish outbound call event for partner {}: {}".format(
                    partner_id, str(e)
                )
            )
