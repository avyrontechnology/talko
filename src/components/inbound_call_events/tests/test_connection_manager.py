import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.inbound_call_events.connection_manager import TalkoInboundCallEventBroker
from src.components.inbound_call_events.constants import INBOUND_CALL_EVENTS_CHANNEL


def make_broker():
    redis_pool = MagicMock()
    logger = MagicMock()
    return (
        TalkoInboundCallEventBroker(redis_pool=redis_pool, logger=logger),
        redis_pool,
        logger,
    )


class TestInboundCallEventBrokerRegistration:
    @pytest.mark.asyncio
    async def test_register_adds_websocket_for_partner(self):
        broker, _, _ = make_broker()
        websocket = MagicMock()

        await broker.register(100, websocket)

        assert websocket in broker._TalkoInboundCallEventBroker__connections[100]

    @pytest.mark.asyncio
    async def test_unregister_removes_websocket(self):
        broker, _, _ = make_broker()
        websocket = MagicMock()
        await broker.register(100, websocket)

        broker.unregister(100, websocket)

        assert websocket not in broker._TalkoInboundCallEventBroker__connections[100]

    def test_unregister_unknown_partner_is_noop(self):
        broker, _, _ = make_broker()
        # Should not raise even though partner 999 never registered anything.
        broker.unregister(999, MagicMock())


class TestInboundCallEventBrokerPublish:
    @pytest.mark.asyncio
    async def test_publish_sends_to_redis_channel_not_local_sockets(self):
        broker, redis_pool, _ = make_broker()
        redis_pool.publish = AsyncMock()
        websocket = MagicMock()
        websocket.send_json = AsyncMock()
        await broker.register(100, websocket)

        await broker.publish({"partner_id": 100, "agent_id": 50})

        redis_pool.publish.assert_called_once_with(
            INBOUND_CALL_EVENTS_CHANNEL, json.dumps({"partner_id": 100, "agent_id": 50})
        )
        # publish() only fans out via the listener loop (__dispatch), never directly.
        websocket.send_json.assert_not_called()


class TestInboundCallEventBrokerDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_sends_only_to_matching_partner(self):
        broker, _, _ = make_broker()
        ws_partner_100 = MagicMock()
        ws_partner_100.send_json = AsyncMock()
        ws_partner_200 = MagicMock()
        ws_partner_200.send_json = AsyncMock()

        await broker.register(100, ws_partner_100)
        await broker.register(200, ws_partner_200)

        message = json.dumps({"partner_id": 100, "agent_id": 50})
        await broker._TalkoInboundCallEventBroker__dispatch(message)

        ws_partner_100.send_json.assert_called_once_with(
            {"partner_id": 100, "agent_id": 50}
        )
        ws_partner_200.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_accepts_bytes_payload(self):
        broker, _, _ = make_broker()
        websocket = MagicMock()
        websocket.send_json = AsyncMock()
        await broker.register(100, websocket)

        message = json.dumps({"partner_id": 100}).encode("utf-8")
        await broker._TalkoInboundCallEventBroker__dispatch(message)

        websocket.send_json.assert_called_once_with({"partner_id": 100})

    @pytest.mark.asyncio
    async def test_dispatch_drops_socket_on_send_failure(self):
        broker, _, _ = make_broker()
        websocket = MagicMock()
        websocket.send_json = AsyncMock(side_effect=Exception("connection closed"))
        await broker.register(100, websocket)

        await broker._TalkoInboundCallEventBroker__dispatch(json.dumps({"partner_id": 100}))

        assert websocket not in broker._TalkoInboundCallEventBroker__connections[100]

    @pytest.mark.asyncio
    async def test_dispatch_logs_and_ignores_malformed_message(self):
        broker, _, logger = make_broker()

        # Must not raise on garbage input from the channel.
        await broker._TalkoInboundCallEventBroker__dispatch("not-json")

        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_ignores_partner_with_no_connections(self):
        broker, _, _ = make_broker()

        # No one registered for partner 100 — should be a no-op, not an error.
        await broker._TalkoInboundCallEventBroker__dispatch(json.dumps({"partner_id": 100}))


class TestInboundCallEventBrokerLifecycle:
    @pytest.mark.asyncio
    async def test_start_subscribes_to_channel_and_stop_cancels_task(self):
        broker, redis_pool, _ = make_broker()

        pubsub = MagicMock()
        pubsub.subscribe = AsyncMock()

        async def hanging_listen():
            await asyncio.Event().wait()
            yield  # pragma: no cover — never reached, keeps this an async generator

        pubsub.listen = hanging_listen
        redis_pool.pubsub = MagicMock(return_value=pubsub)

        await broker.start()
        await asyncio.sleep(0)  # let the listener task actually start running

        pubsub.subscribe.assert_called_once_with(INBOUND_CALL_EVENTS_CHANNEL)

        await broker.stop()
        assert broker._TalkoInboundCallEventBroker__listener_task is None

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        broker, redis_pool, _ = make_broker()

        pubsub = MagicMock()
        pubsub.subscribe = AsyncMock()

        async def hanging_listen():
            await asyncio.Event().wait()
            yield  # pragma: no cover

        pubsub.listen = hanging_listen
        redis_pool.pubsub = MagicMock(return_value=pubsub)

        await broker.start()
        first_task = broker._TalkoInboundCallEventBroker__listener_task
        await broker.start()

        assert broker._TalkoInboundCallEventBroker__listener_task is first_task

        await broker.stop()
