from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.inbound_call_events.constants import INBOUND_CALL_EVENT_TYPE
from src.components.inbound_call_events.publisher import InboundCallEventPublisher


def make_publisher():
    broker = AsyncMock()
    logger = MagicMock()
    return InboundCallEventPublisher(broker=broker, logger=logger), broker, logger


class TestInboundCallEventPublisher:
    @pytest.mark.asyncio
    async def test_publish_inbound_call_publishes_expected_payload(self):
        publisher, broker, _ = make_publisher()

        await publisher.publish_inbound_call(
            partner_id=100,
            service_board_id=1,
            dedicated_did="+919876543210",
            agent_id=50,
            agent_ids=[50, 51],
            display_name="Sales Line",
            customer_number="+911234567890",
        )

        broker.publish.assert_called_once()
        payload = broker.publish.call_args[0][0]
        assert payload["event"] == INBOUND_CALL_EVENT_TYPE
        assert payload["partner_id"] == 100
        assert payload["service_board_id"] == 1
        assert payload["dedicated_did"] == "+919876543210"
        assert payload["agent_id"] == 50
        assert payload["agent_ids"] == [50, 51]
        assert payload["display_name"] == "Sales Line"
        assert payload["customer_number"] == "+911234567890"
        assert isinstance(payload["timestamp"], int)

    @pytest.mark.asyncio
    async def test_publish_inbound_call_defaults_agent_ids_to_empty_list(self):
        publisher, broker, _ = make_publisher()

        await publisher.publish_inbound_call(
            partner_id=100,
            service_board_id=1,
            dedicated_did="+919876543210",
            agent_id=None,
        )

        payload = broker.publish.call_args[0][0]
        assert payload["agent_ids"] == []
        assert payload["agent_id"] is None
        assert payload["customer_number"] is None

    @pytest.mark.asyncio
    async def test_publish_inbound_call_skips_when_no_partner_id(self):
        publisher, broker, logger = make_publisher()

        await publisher.publish_inbound_call(
            partner_id=None,
            service_board_id=1,
            dedicated_did="+919876543210",
            agent_id=50,
        )

        broker.publish.assert_not_called()
        logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_publish_inbound_call_swallows_broker_errors(self):
        publisher, broker, logger = make_publisher()
        broker.publish.side_effect = Exception("broker down")

        # Must not raise — a broken event bus should never break call routing.
        await publisher.publish_inbound_call(
            partner_id=100,
            service_board_id=1,
            dedicated_did="+919876543210",
            agent_id=50,
        )

        logger.error.assert_called_once()
