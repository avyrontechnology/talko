import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.call_management.agent_dialplan_resolver import TransferTarget
from src.components.call_management.constant import AI_BRIDGE_VENDOR_CONFIG_ID
from src.components.call_management.dto import Contract as call_contract
from src.components.call_management.services import CallService
from src.exceptions import ResourceNotFound
from src.utils.enums import VendorType


def make_service(**overrides):
    """Helper to instantiate CallService with default AsyncMock dependencies."""
    defaults = dict(
        repository=AsyncMock(),
        logger=MagicMock(),
        datetime_util=MagicMock(),
        partner_config_repository=AsyncMock(),
        vendor_config_repository=AsyncMock(),
        agent_mapping_service=AsyncMock(),
        agent_mapping_repository=AsyncMock(),
        did_management_service=AsyncMock(),
        cdr_update_task=AsyncMock(),  # <-- new
        vendor_cdr_gateway=AsyncMock(),  # <-- new
        cdr_repository=AsyncMock(),
        call_redis_helper=AsyncMock(),
        did_repository=AsyncMock(),
        inbound_call_event_publisher=AsyncMock(),
    )
    defaults.update(overrides)
    return CallService(**defaults), defaults


class TestCallService:
    @pytest.mark.asyncio
    async def test_generate_dialplan_no_cdr_with_none_agent_values(self):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]
        partner_config_repository = deps["partner_config_repository"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        did_record = {
            "partner_id": 100,
            "service_board_id": 1,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        target = TransferTarget(
            type="number",
            data=["9999999999"],
            ring_type="simultaneous",
            skip_active=False,
        )

        resolve_result = {
            "target": target,
            "partner_id": 100,
            "agent_id": None,
            "service_board_id": 1,
            "agent_number": None,
            "agent_ids": [
                {"agent_id": 50, "agent_number": "111", "cloud_agent_number": None},
                {"agent_id": 51, "agent_number": "222", "cloud_agent_number": None},
            ],
            "lead_id": None,
            "lead_name": None,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        repository.find_cdr_by_numbers = AsyncMock(return_value=None)
        did_management_service.get_dids_by_number = AsyncMock(return_value=did_record)
        partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value={"enable_inbound_lead_creation": False}
        )
        service._CallService__dialplan_resolver.resolve_inbound_no_cdr = AsyncMock(
            return_value=resolve_result
        )
        service._CallService__dialplan_resolver.map_transfer_to_inbound_fields = (
            MagicMock(return_value=("INBOUND", "9999999999"))
        )
        service._CallService__helper.create_incoming_cdr = AsyncMock()

        result = await service.generate_dialplan_response(request)

        assert len(result) == 1
        assert "transfer" in result[0]
        assert result[0]["transfer"]["data"] == ["9999999999"]

        create_cdr_call = service._CallService__helper.create_incoming_cdr.call_args
        assert create_cdr_call[1]["agent_id"] is None
        assert create_cdr_call[1]["agent_number"] is None
        assert create_cdr_call[1]["lead_id"] is None
        assert create_cdr_call[1]["lead_name"] is None

    @pytest.mark.asyncio
    async def test_generate_dialplan_exception_returns_empty(self):
        service, deps = make_service()
        logger = deps["logger"]

        request = AsyncMock()
        request.json.side_effect = Exception("Request parsing error")

        result = await service.generate_dialplan_response(request)

        assert len(result) == 1
        assert "transfer" in result[0]
        assert result[0]["transfer"]["type"] == "number"
        assert result[0]["transfer"]["data"] == []
        logger.error.assert_called()
        error_msg = logger.error.call_args[0][0]
        assert "Error in generate_dialplan_response" in error_msg

    @pytest.mark.asyncio
    async def test_initiate_call_success(self):
        service, deps = make_service()
        repository = deps["repository"]
        datetime_util = deps["datetime_util"]

        call_data = call_contract.CallCreate(
            number_type="primary",
            lead_secret="b3d9c82198869d446788079e5e331146de19fd18470cba2ea3eb1a3a24d04bb2ded255900d4af46db350c36dc01b4d7b89af108c7df4598262ce434475e47bff4b37640334953b102fe93fae4d84218111b4cf56c154013048fd1145dd0f478a44f2dd2158fdbb0698f341190bb605bbeb85faf3f5af0608b5410597417ed48735e13caa48992cc46e94703417c8fdaef88a5424e5fcd567145d2505075c09adfc03f26765c2591f2f08423416a2487c29fee155f1c3e7f3778b7398b4ec8aa4b021fac0baf57314d7aec3cfeb28807b067656fcb2f45ef37f9039b4d64db76515be7d56bfb8836cbc5a01999308073e269669f5a2ef7b14a2839d740eeb9a4b",
            lead_id=1001,
            agent_number="8888888888",
            service_board_id=1,
            encryption_enabled=True,
        )
        to_number = "+919789346723"
        user_id = 123
        partner_id = 456

        partner_config = {
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
            "agent_mapping_dids": ["111"],
            "enable_agent_mapping": True,
        }
        vendor_response = {"call_id": str(uuid.uuid4()), "status": "initiated"}

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value=partner_config
        )
        service._CallService__helper.select_did = AsyncMock(return_value="111")
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.make_call.return_value = vendor_response
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )
        service._CallService__helper.prepare_cdr = MagicMock(
            return_value={
                "id": "cdr123",
                "call_uuid": vendor_response["call_id"],
                "to_number": to_number,
                "from_number": "111",
                "partner_id": partner_id,
                "vendor_id": "vendor123",
                "call_status": "initiated",
                "created_at": 1722945600,
                "updated_at": 1722945600,
            }
        )
        repository.insert_cdr.return_value = "cdr123"
        datetime_util.get_current_time.return_value = 1722945600

        await service.initiate_call(call_data, user_id, partner_id)

    @pytest.mark.asyncio
    async def test_initiate_call_missing_vendor_id(self):
        service, _ = make_service()

        call_data = call_contract.CallCreate(
            number_type="primary",
            lead_secret="b3d9c82198869d446788079e5e331146de19fd18470cba2ea3eb1a3a24d04bb2ded255900d4af46db350c36dc01b4d7b89af108c7df4598262ce434475e47bff4b37640334953b102fe93fae4d84218111b4cf56c154013048fd1145dd0f478a44f2dd2158fdbb0698f341190bb605bbeb85faf3f5af0608b5410597417ed48735e13caa48992cc46e94703417c8fdaef88a5424e5fcd567145d2505075c09adfc03f26765c2591f2f08423416a2487c29fee155f1c3e7f3778b7398b4ec8aa4b021fac0baf57314d7aec3cfeb28807b067656fcb2f45ef37f9039b4d64db76515be7d56bfb8836cbc5a01999308073e269669f5a2ef7b14a2839d740eeb9a4b",
            lead_id=1001,
            call_url="https://test.com",
            agent_number="8888888888",
            service_board_id=1,
            encryption_enabled=True,
        )

        service._CallService__helper.get_partner_config = AsyncMock(return_value={})
        service._CallService__helper.select_did = AsyncMock(return_value="111")

        with pytest.raises(ResourceNotFound):
            await service.initiate_call(call_data, 123, 456)

    @pytest.mark.asyncio
    async def test_get_webhook_handler_valid(self):
        service, _ = make_service()
        handler = service.get_webhook_handler(VendorType.TATA_TELE.value)
        assert handler is not None

    @pytest.mark.asyncio
    async def test_get_webhook_handler_invalid(self):
        service, _ = make_service()
        with pytest.raises(ValueError):
            service.get_webhook_handler("unknown_vendor")

    @pytest.mark.asyncio
    async def test_initiate_call_vendor_raises_value_error_logs_and_raises(self):
        service, deps = make_service()
        logger = deps["logger"]

        call_data = call_contract.CallCreate(
            number_type="primary",
            lead_secret="b3d9c82198869d446788079e5e331146de19fd18470cba2ea3eb1a3a24d04bb2ded255900d4af46db350c36dc01b4d7b89af108c7df4598262ce434475e47bff4b37640334953b102fe93fae4d84218111b4cf56c154013048fd1145dd0f478a44f2dd2158fdbb0698f341190bb605bbeb85faf3f5af0608b5410597417ed48735e13caa48992cc46e94703417c8fdaef88a5424e5fcd567145d2505075c09adfc03f26765c2591f2f08423416a2487c29fee155f1c3e7f3778b7398b4ec8aa4b021fac0baf57314d7aec3cfeb28807b067656fcb2f45ef37f9039b4d64db76515be7d56bfb8836cbc5a01999308073e269669f5a2ef7b14a2839d740eeb9a4b",
            lead_id=1001,
            call_url="https://test.com",
            agent_number="8888888888",
            service_board_id=1,
            encryption_enabled=True,
        )

        partner_config = {
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
            "agent_mapping_dids": ["111"],
            "enable_agent_mapping": True,
        }

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value=partner_config
        )
        service._CallService__helper.select_did = AsyncMock(return_value="111")
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.make_call.side_effect = ValueError("Some vendor error")
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )

        with pytest.raises(ValueError, match="Some vendor error"):
            await service.initiate_call(call_data, 123, 456)

        error_calls = [call[0][0] for call in logger.error.call_args_list]
        assert any(
            "Vendor call failed: Some vendor error" in msg for msg in error_calls
        )
        assert any(
            "Unexpected error in initiate_call: Some vendor error" in msg
            for msg in error_calls
        )

    @pytest.mark.asyncio
    async def test_initiate_call_unexpected_exception_logs_and_raises(self):
        service, deps = make_service()
        logger = deps["logger"]

        call_data = call_contract.CallCreate(
            number_type="primary",
            lead_secret="dummy",
            lead_id=1001,
            call_url="https://test.com",
            agent_number="8888888888",
            service_board_id=1,
            encryption_enabled=True,
        )

        service._CallService__helper.decrypt_lead_data = MagicMock(
            side_effect=RuntimeError("Unexpected decryption error")
        )

        with pytest.raises(RuntimeError, match="Unexpected decryption error"):
            await service.initiate_call(call_data, 123, 456)

        logger.error.assert_called_with(
            "Unexpected error in initiate_call: Unexpected decryption error"
        )

    @pytest.mark.asyncio
    async def test_initiate_call_success_without_encryption(self):
        service, deps = make_service()
        repository = deps["repository"]
        datetime_util = deps["datetime_util"]

        to_number = "+919789346723"
        call_data = call_contract.CallCreate(
            to_number=to_number,
            number_type="primary",
            lead_id=1001,
            agent_number="8888888888",
            service_board_id=1,
        )

        partner_config = {"vendor_id": "vendor123", "vendor_config_id": "config456"}
        vendor_response = {"call_id": str(uuid.uuid4()), "status": "initiated"}

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value=partner_config
        )
        service._CallService__helper.select_did = AsyncMock(return_value="111")
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.make_call.return_value = vendor_response
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )
        service._CallService__helper.prepare_cdr = MagicMock(return_value={})
        repository.insert_cdr.return_value = "cdr123"
        datetime_util.get_current_time.return_value = 1722945600

        response = await service.initiate_call(call_data, 123, 456)
        assert response.id == "cdr123"

    @pytest.mark.asyncio
    async def test_initiate_call_with_cloud_agent_number(self):
        service, deps = make_service()
        repository = deps["repository"]
        datetime_util = deps["datetime_util"]

        to_number = "+919789346723"
        call_data = call_contract.CallCreate(
            to_number=to_number,
            agent_number="8888888888",
            number_type="primary",
            lead_id=1001,
            cloud_agent_number="9999999999",
            service_board_id=1,
            encryption_enabled=False,
        )

        partner_config = {"vendor_id": "vendor123", "vendor_config_id": "config456"}
        vendor_response = {"call_id": str(uuid.uuid4()), "status": "initiated"}

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value=partner_config
        )
        service._CallService__helper.select_did = AsyncMock(return_value="111")
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.make_call.return_value = vendor_response
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )
        service._CallService__helper.prepare_cdr = MagicMock(return_value={})
        repository.insert_cdr.return_value = "cdr123"
        datetime_util.get_current_time.return_value = 1722945600

        await service.initiate_call(call_data, 123, 456)

        mock_vendor_handler.make_call.assert_called_once()
        call_args = mock_vendor_handler.make_call.call_args[0]
        assert call_args[3] == "9999999999"

    @pytest.mark.asyncio
    async def test_initiate_call_ai_bridge_empty_call_id_still_fires_pre_session(self):
        """Live Tata click-to-call never returns call_id synchronously (only
        ref_id) — pre-warm must still fire keyed off to_number, not call_id."""
        import asyncio

        service, deps = make_service()
        repository = deps["repository"]
        datetime_util = deps["datetime_util"]

        to_number = "+919789346723"
        call_data = call_contract.CallCreate(
            to_number=to_number,
            number_type="primary",
            lead_id=1001,
            enable_ai_bridge=True,
            service_board_id=1,
        )

        partner_config = {"vendor_id": "vendor123", "vendor_config_id": "config456"}
        vendor_response = {"status": "initiated", "ref_id": str(uuid.uuid4())}

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value=partner_config
        )
        service._CallService__helper.select_did = AsyncMock(return_value="111")
        service._CallService__helper.validate_given_did = AsyncMock()
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.make_call.return_value = vendor_response
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )
        service._CallService__helper.prepare_cdr = MagicMock(return_value={})
        repository.insert_cdr.return_value = "cdr123"
        datetime_util.get_current_time.return_value = 1722945600

        service._pre_create_session = AsyncMock()

        await service.initiate_call(call_data, 123, 456)
        await asyncio.sleep(0)  # let the fire-and-forget pre-session task run

        service._CallService__helper.validate_given_did.assert_called_once()
        service._pre_create_session.assert_called_once()
        _, kwargs = service._pre_create_session.call_args
        assert kwargs["call_id"] == ""
        assert kwargs["to_number"] == "919789346723"

    @pytest.mark.asyncio
    async def test_initiate_call_injects_cdr_id_into_context_data(self):
        """cdr_id (this CDR row's own _id, not Tata's call_id) must ride
        along in context_data all the way to _pre_create_session — it's
        what _backfill_real_vendor_call_id later uses to fix up this exact
        row once the real vendor call_id resolves (pstn/services.py)."""
        import asyncio

        service, deps = make_service()
        repository = deps["repository"]
        datetime_util = deps["datetime_util"]

        call_data = call_contract.CallCreate(
            to_number="+919789346723",
            number_type="primary",
            lead_id=1001,
            enable_ai_bridge=True,
            service_board_id=1,
            context_data={"campaign_id": "7", "recipient_id": "92"},
        )

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value={"vendor_id": "vendor123", "vendor_config_id": "config456"}
        )
        service._CallService__helper.select_did = AsyncMock(return_value="111")
        service._CallService__helper.validate_given_did = AsyncMock()
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.make_call.return_value = {
            "status": "initiated",
            "ref_id": str(uuid.uuid4()),
        }
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )
        service._CallService__helper.prepare_cdr = MagicMock(return_value={})
        repository.insert_cdr.return_value = "cdr-xyz-789"
        datetime_util.get_current_time.return_value = 1722945600

        service._pre_create_session = AsyncMock()

        await service.initiate_call(call_data, 123, 456)
        await asyncio.sleep(0)  # let the fire-and-forget pre-session task run

        _, kwargs = service._pre_create_session.call_args
        assert kwargs["context_data"] == {
            "campaign_id": "7",
            "recipient_id": "92",
            "cdr_id": "cdr-xyz-789",
        }
        assert kwargs["fallback_payload"]["context_data"] == kwargs["context_data"]

    @pytest.mark.asyncio
    async def test_initiate_call_missing_vendor_config_id(self):
        service, _ = make_service()

        call_data = call_contract.CallCreate(
            to_number="+919789346723",
            number_type="primary",
            lead_id=1001,
            agent_number="8888888888",
            service_board_id=1,
        )

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value={"vendor_id": "vendor123"}
        )
        service._CallService__helper.select_did = AsyncMock(return_value="111")

        with pytest.raises(ResourceNotFound):
            await service.initiate_call(call_data, 123, 456)

    @pytest.mark.asyncio
    async def test_get_webhook_handler_acefhone(self):
        service, _ = make_service()
        handler = service.get_webhook_handler(VendorType.ACEFHONE.value)
        assert handler is not None

    @pytest.mark.asyncio
    async def test_generate_dialplan_with_existing_cdr(self):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        did_management_service.get_dids_by_number = AsyncMock(
            return_value={"display_name": "Sales Line"}
        )

        cdr_data = {
            "partner_id": 100,
            "service_board_id": 1,
            "agent": 50,
            "agent_number": "8888888888",
            "lead_id": 1001,
            "lead_name": "John Doe",
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        target = TransferTarget(
            type="number",
            data=["9999999999"],
            ring_type="simultaneous",
            skip_active=False,
        )

        repository.find_cdr_by_numbers = AsyncMock(return_value=cdr_data)
        service._CallService__dialplan_resolver.resolve_for_single_agent = AsyncMock(
            return_value=target
        )
        service._CallService__dialplan_resolver.map_transfer_to_inbound_fields = (
            MagicMock(return_value=("OUTBOUND", "9999999999"))
        )
        service._CallService__helper.create_incoming_cdr = AsyncMock()

        result = await service.generate_dialplan_response(request)

        assert len(result) == 1
        assert "transfer" in result[0]
        assert result[0]["transfer"]["type"] == "number"
        assert result[0]["transfer"]["data"] == ["9999999999"]
        repository.find_cdr_by_numbers.assert_called_once_with(
            "+911234567890", "+919876543210"
        )
        service._CallService__helper.create_incoming_cdr.assert_called_once()
        did_management_service.get_dids_by_number.assert_called_once_with(
            "+919876543210"
        )

        publisher = deps["inbound_call_event_publisher"]
        publisher.publish_inbound_call.assert_called_once_with(
            partner_id=100,
            service_board_id=1,
            dedicated_did="+919876543210",
            agent_id=50,
            display_name="Sales Line",
            customer_number="+911234567890",
        )

    @pytest.mark.asyncio
    async def test_generate_dialplan_existing_cdr_reassigned_lead_overrides_stale_lead_id(
        self,
    ):
        """Priority 1: the old CDR's lead_id is the baseline. Priority 2: if
        resolve_for_single_agent reassigned the agent and Maglo confirmed a
        lead_request_id, that overrides the stale value on the new CDR."""
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+919355598337",
            "call_to_number": "+919876543210",
        }

        did_management_service.get_dids_by_number = AsyncMock(
            return_value={"display_name": "Sales Line"}
        )

        cdr_data = {
            "partner_id": 100,
            "service_board_id": 1,
            "agent": 4940,
            "agent_number": "8888888888",
            # Real-world shape seen in QA: entity_type was already "Lead"
            # from a prior call, but entity_id/lead_id were never actually
            # populated — reassignment confirms the real lead via Maglo.
            "entity_type": "Lead",
            "entity_id": None,
            "entity_name": None,
            "lead_id": None,
            "lead_name": None,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        target = TransferTarget(
            type="number",
            data=["9999999999"],
            ring_type="simultaneous",
            skip_active=False,
            resolved_agent_id=4957,
            reassigned_lead_id=179245,
        )

        repository.find_cdr_by_numbers = AsyncMock(return_value=cdr_data)
        service._CallService__dialplan_resolver.resolve_for_single_agent = AsyncMock(
            return_value=target
        )
        service._CallService__dialplan_resolver.map_transfer_to_inbound_fields = (
            MagicMock(return_value=("OUTBOUND", "9999999999"))
        )
        service._CallService__helper.create_incoming_cdr = AsyncMock()

        await service.generate_dialplan_response(request)

        service._CallService__helper.create_incoming_cdr.assert_called_once()
        call_kwargs = service._CallService__helper.create_incoming_cdr.call_args.kwargs
        assert call_kwargs["agent_id"] == 4957
        assert call_kwargs["lead_id"] == 179245
        # Regression guard: entity_type was already "Lead" on the old CDR
        # (with entity_id never populated) — the override must still reach
        # entity_id, not just the legacy lead_id field.
        assert call_kwargs["entity_id"] == 179245
        assert call_kwargs["entity_type"] == "Lead"

        publisher = deps["inbound_call_event_publisher"]
        publisher.publish_inbound_call.assert_called_once_with(
            partner_id=100,
            service_board_id=1,
            dedicated_did="+919876543210",
            agent_id=4957,
            display_name="Sales Line",
            customer_number="+919355598337",
        )

    @pytest.mark.asyncio
    async def test_generate_dialplan_no_cdr_with_did_record(self):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]
        partner_config_repository = deps["partner_config_repository"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        did_record = {
            "partner_id": 100,
            "service_board_id": 1,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
            "display_name": "Support Line",
        }

        target = TransferTarget(
            type="number",
            data=["9999999999"],
            ring_type="simultaneous",
            skip_active=False,
        )

        resolve_result = {
            "target": target,
            "partner_id": 100,
            "agent_id": 50,
            "service_board_id": 1,
            "agent_number": "8888888888",
            "agent_ids": [
                {"agent_id": 50, "agent_number": "111", "cloud_agent_number": None},
                {"agent_id": 51, "agent_number": "222", "cloud_agent_number": None},
            ],
            "lead_id": 1001,
            "lead_name": "Jane Doe",
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        repository.find_cdr_by_numbers = AsyncMock(return_value=None)
        did_management_service.get_dids_by_number = AsyncMock(return_value=did_record)
        partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value={"enable_inbound_lead_creation": False}
        )
        service._CallService__dialplan_resolver.resolve_inbound_no_cdr = AsyncMock(
            return_value=resolve_result
        )
        service._CallService__dialplan_resolver.map_transfer_to_inbound_fields = (
            MagicMock(return_value=("INBOUND", "9999999999"))
        )
        service._CallService__helper.create_incoming_cdr = AsyncMock()

        result = await service.generate_dialplan_response(request)

        assert len(result) == 1
        assert "transfer" in result[0]
        assert result[0]["transfer"]["type"] == "number"
        assert result[0]["transfer"]["data"] == ["9999999999"]
        did_management_service.get_dids_by_number.assert_called_once_with(
            "+919876543210"
        )
        service._CallService__dialplan_resolver.resolve_inbound_no_cdr.assert_called_once()

        publisher = deps["inbound_call_event_publisher"]
        publisher.publish_inbound_call.assert_called_once_with(
            partner_id=100,
            service_board_id=1,
            dedicated_did="+919876543210",
            agent_id=50,
            agent_ids=[50, 51],
            display_name="Support Line",
            customer_number="+911234567890",
        )

        repository.update_partner_config_inbound_round_robin_index.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_dialplan_no_cdr_round_robin_persists_next_index(self):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]
        partner_config_repository = deps["partner_config_repository"]
        datetime_util = deps["datetime_util"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        did_record = {
            "partner_id": 100,
            "service_board_id": 1,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
            "display_name": "Support Line",
        }

        target = TransferTarget(
            type="number",
            data=["9999999999"],
            ring_type="order_by",
            skip_active=False,
        )

        resolve_result = {
            "target": target,
            "partner_id": 100,
            "agent_id": None,
            "service_board_id": 1,
            "agent_number": None,
            "agent_ids": [],
            "lead_id": None,
            "lead_name": None,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
            "inbound_round_robin_next_index": 3,
        }

        datetime_util.get_current_time.return_value = 1234567890

        repository.find_cdr_by_numbers = AsyncMock(return_value=None)
        did_management_service.get_dids_by_number = AsyncMock(return_value=did_record)
        partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value={
                "enable_inbound_lead_creation": False,
                "enable_inbound_round_robin": True,
                "inbound_round_robin_index": 2,
            }
        )
        service._CallService__dialplan_resolver.resolve_inbound_no_cdr = AsyncMock(
            return_value=resolve_result
        )
        service._CallService__dialplan_resolver.map_transfer_to_inbound_fields = (
            MagicMock(return_value=("INBOUND", None))
        )
        service._CallService__helper.create_incoming_cdr = AsyncMock()

        await service.generate_dialplan_response(request)

        service._CallService__dialplan_resolver.resolve_inbound_no_cdr.assert_called_once_with(
            customer_number="+911234567890",
            call_to_number="+919876543210",
            partner_id=100,
            service_board_id=1,
            vendor_id="vendor123",
            vendor_config_id="config456",
            create_lead=False,
            reassign_inactive_agent=False,
            enable_inbound_round_robin=True,
            inbound_round_robin_index=2,
        )
        repository.update_partner_config_inbound_round_robin_index.assert_called_once_with(
            100, 3, 1234567890
        )

    @pytest.mark.asyncio
    async def test_generate_dialplan_no_cdr_no_did_record_skips_event_publish(self):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        repository.find_cdr_by_numbers = AsyncMock(return_value=None)
        did_management_service.get_dids_by_number = AsyncMock(return_value=None)

        await service.generate_dialplan_response(request)

        deps["inbound_call_event_publisher"].publish_inbound_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_dialplan_no_cdr_did_without_service_board_skips_event_publish(
        self,
    ):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        did_record = {"partner_id": 100, "vendor_id": "vendor123"}

        repository.find_cdr_by_numbers = AsyncMock(return_value=None)
        did_management_service.get_dids_by_number = AsyncMock(return_value=did_record)

        await service.generate_dialplan_response(request)

        deps["inbound_call_event_publisher"].publish_inbound_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_dialplan_exception_skips_event_publish(self):
        service, deps = make_service()

        request = AsyncMock()
        request.json.side_effect = Exception("Request parsing error")

        await service.generate_dialplan_response(request)

        deps["inbound_call_event_publisher"].publish_inbound_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_dialplan_no_cdr_no_did_record(self):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        repository.find_cdr_by_numbers = AsyncMock(return_value=None)
        did_management_service.get_dids_by_number = AsyncMock(return_value=None)

        result = await service.generate_dialplan_response(request)

        assert len(result) == 1
        assert "transfer" in result[0]
        assert result[0]["transfer"]["type"] == "number"
        assert result[0]["transfer"]["data"] == []

    @pytest.mark.asyncio
    async def test_generate_dialplan_no_cdr_did_without_service_board(self):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]
        logger = deps["logger"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        did_record = {"partner_id": 100, "vendor_id": "vendor123"}

        repository.find_cdr_by_numbers = AsyncMock(return_value=None)
        did_management_service.get_dids_by_number = AsyncMock(return_value=did_record)

        result = await service.generate_dialplan_response(request)

        assert len(result) == 1
        assert "transfer" in result[0]
        assert result[0]["transfer"]["type"] == "number"
        assert result[0]["transfer"]["data"] == []
        logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_create_cdr_if_valid_target_with_empty_data(self):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]
        partner_config_repository = deps["partner_config_repository"]
        logger = deps["logger"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        did_record = {
            "partner_id": 100,
            "service_board_id": 1,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        target = TransferTarget(
            type="number", data=[], ring_type="simultaneous", skip_active=False
        )

        resolve_result = {
            "target": target,
            "partner_id": 100,
            "agent_id": None,
            "service_board_id": 1,
            "agent_number": None,
            "agent_ids": [],
            "lead_id": None,
            "lead_name": None,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        repository.find_cdr_by_numbers = AsyncMock(return_value=None)
        did_management_service.get_dids_by_number = AsyncMock(return_value=did_record)
        partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value={"enable_inbound_lead_creation": False}
        )
        service._CallService__dialplan_resolver.resolve_inbound_no_cdr = AsyncMock(
            return_value=resolve_result
        )
        service._CallService__dialplan_resolver.map_transfer_to_inbound_fields = (
            MagicMock(return_value=("INBOUND", None))
        )
        service._CallService__helper.create_incoming_cdr = AsyncMock()

        result = await service.generate_dialplan_response(request)

        service._CallService__helper.create_incoming_cdr.assert_not_called()
        logger.info.assert_any_call("Skipping CDR creation — no valid transfer targets")

    @pytest.mark.asyncio
    async def test_create_cdr_if_valid_target_with_none_target(self):
        service, deps = make_service()
        repository = deps["repository"]
        logger = deps["logger"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        cdr_data = {
            "partner_id": 100,
            "service_board_id": 1,
            "agent": 50,
            "agent_number": "8888888888",
            "lead_id": 1001,
            "lead_name": "John Doe",
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        repository.find_cdr_by_numbers = AsyncMock(return_value=cdr_data)
        service._CallService__dialplan_resolver.resolve_for_single_agent = AsyncMock(
            return_value=None
        )
        service._CallService__dialplan_resolver.map_transfer_to_inbound_fields = (
            MagicMock(return_value=("OUTBOUND", None))
        )
        service._CallService__helper.create_incoming_cdr = AsyncMock()

        result = await service.generate_dialplan_response(request)

        service._CallService__helper.create_incoming_cdr.assert_not_called()
        logger.info.assert_any_call("Skipping CDR creation — no valid transfer targets")

    @pytest.mark.asyncio
    async def test_should_create_lead_with_none_partner_config(self):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]
        partner_config_repository = deps["partner_config_repository"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        did_record = {
            "partner_id": 100,
            "service_board_id": 1,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        target = TransferTarget(
            type="number",
            data=["9999999999"],
            ring_type="simultaneous",
            skip_active=False,
        )

        resolve_result = {
            "target": target,
            "partner_id": 100,
            "agent_id": None,
            "service_board_id": 1,
            "agent_number": None,
            "agent_ids": [],
            "lead_id": None,
            "lead_name": None,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        repository.find_cdr_by_numbers = AsyncMock(return_value=None)
        did_management_service.get_dids_by_number = AsyncMock(return_value=did_record)
        partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value=None
        )
        service._CallService__dialplan_resolver.resolve_inbound_no_cdr = AsyncMock(
            return_value=resolve_result
        )
        service._CallService__dialplan_resolver.map_transfer_to_inbound_fields = (
            MagicMock(return_value=("INBOUND", None))
        )
        service._CallService__helper.create_incoming_cdr = AsyncMock()

        await service.generate_dialplan_response(request)

        call_args = (
            service._CallService__dialplan_resolver.resolve_inbound_no_cdr.call_args
        )
        assert call_args[1]["create_lead"] is False

    @pytest.mark.asyncio
    async def test_should_use_inbound_round_robin_with_none_partner_config(self):
        service, _ = make_service()
        assert service._should_use_inbound_round_robin(None) is False

    @pytest.mark.asyncio
    async def test_should_use_inbound_round_robin_with_flag_true(self):
        service, _ = make_service()
        assert (
            service._should_use_inbound_round_robin(
                {"enable_inbound_round_robin": True}
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_should_use_inbound_round_robin_with_missing_flag(self):
        service, _ = make_service()
        assert service._should_use_inbound_round_robin({}) is False

    @pytest.mark.asyncio
    async def test_get_webhook_handler_exception_handling(self):
        service, deps = make_service()
        logger = deps["logger"]

        with pytest.raises(ValueError, match="Unsupported vendor_id"):
            service.get_webhook_handler("UNKNOWN_VENDOR")

        logger.error.assert_called()
        error_msg = logger.error.call_args[0][0]
        assert "Unexcpected error in get webhook handler" in error_msg

    @pytest.mark.asyncio
    async def test_should_create_lead_with_flag_false(self):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]
        partner_config_repository = deps["partner_config_repository"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        did_record = {
            "partner_id": 100,
            "service_board_id": 1,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        target = TransferTarget(
            type="number",
            data=["9999999999"],
            ring_type="simultaneous",
            skip_active=False,
        )

        resolve_result = {
            "target": target,
            "partner_id": 100,
            "agent_id": None,
            "service_board_id": 1,
            "agent_number": None,
            "agent_ids": [],
            "lead_id": None,
            "lead_name": None,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        repository.find_cdr_by_numbers = AsyncMock(return_value=None)
        did_management_service.get_dids_by_number = AsyncMock(return_value=did_record)
        partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value={"enable_inbound_lead_creation": False}
        )
        service._CallService__dialplan_resolver.resolve_inbound_no_cdr = AsyncMock(
            return_value=resolve_result
        )
        service._CallService__dialplan_resolver.map_transfer_to_inbound_fields = (
            MagicMock(return_value=("INBOUND", None))
        )
        service._CallService__helper.create_incoming_cdr = AsyncMock()

        await service.generate_dialplan_response(request)

        call_args = (
            service._CallService__dialplan_resolver.resolve_inbound_no_cdr.call_args
        )
        assert call_args[1]["create_lead"] is False

    @pytest.mark.asyncio
    async def test_should_create_lead_with_missing_flag(self):
        service, deps = make_service()
        repository = deps["repository"]
        did_management_service = deps["did_management_service"]
        partner_config_repository = deps["partner_config_repository"]

        request = AsyncMock()
        request.json.return_value = {
            "caller_id_number": "+911234567890",
            "call_to_number": "+919876543210",
        }

        did_record = {
            "partner_id": 100,
            "service_board_id": 1,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        target = TransferTarget(
            type="number",
            data=["9999999999"],
            ring_type="simultaneous",
            skip_active=False,
        )

        resolve_result = {
            "target": target,
            "partner_id": 100,
            "agent_id": None,
            "service_board_id": 1,
            "agent_number": None,
            "agent_ids": [],
            "lead_id": None,
            "lead_name": None,
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }

        repository.find_cdr_by_numbers = AsyncMock(return_value=None)
        did_management_service.get_dids_by_number = AsyncMock(return_value=did_record)
        partner_config_repository.find_partner_config_by_partner_id = AsyncMock(
            return_value={"some_other_key": "some_value"}
        )
        service._CallService__dialplan_resolver.resolve_inbound_no_cdr = AsyncMock(
            return_value=resolve_result
        )
        service._CallService__dialplan_resolver.map_transfer_to_inbound_fields = (
            MagicMock(return_value=("INBOUND", None))
        )
        service._CallService__helper.create_incoming_cdr = AsyncMock()

        await service.generate_dialplan_response(request)

        call_args = (
            service._CallService__dialplan_resolver.resolve_inbound_no_cdr.call_args
        )
        assert call_args[1]["create_lead"] is False


class TestCallServiceHangupCall:
    @pytest.mark.asyncio
    async def test_hangup_call_success(self):
        service, _ = make_service()

        partner_config = {
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }
        vendor_response = {"Success": True, "Message": "Call hangup successfully"}

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value=partner_config
        )
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.hangup_call.return_value = vendor_response
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )

        result = await service.hangup_call("abc123", user_id=123, partner_id=456)

        assert result.success is True
        assert result.message == "Call hangup successfully"
        mock_vendor_handler.hangup_call.assert_awaited_once_with("abc123")
        service._CallService__helper.get_vendor_handler.assert_awaited_once_with(
            "vendor123", "config456"
        )

    @pytest.mark.asyncio
    async def test_hangup_call_success_via_api_key_no_user_id(self):
        service, _ = make_service()

        partner_config = {
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
        }
        vendor_response = {"success": True, "message": "ok"}

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value=partner_config
        )
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.hangup_call.return_value = vendor_response
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )

        result = await service.hangup_call("abc123", user_id=None, partner_id=456)

        assert result.success is True
        assert result.message == "ok"

    @pytest.mark.asyncio
    async def test_hangup_call_missing_vendor_id(self):
        service, _ = make_service()

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value={"vendor_config_id": "config456"}
        )

        with pytest.raises(ResourceNotFound):
            await service.hangup_call("abc123", user_id=123, partner_id=456)

    @pytest.mark.asyncio
    async def test_hangup_call_missing_vendor_config_id(self):
        service, _ = make_service()

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value={"vendor_id": "vendor123"}
        )

        with pytest.raises(ResourceNotFound):
            await service.hangup_call("abc123", user_id=123, partner_id=456)

    @pytest.mark.asyncio
    async def test_hangup_call_ai_bridge_uses_hardcoded_vendor_config_id(self):
        service, _ = make_service()

        partner_config = {
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
            "ai_vendor_config_id": "should-be-ignored",
        }
        vendor_response = {"Success": True, "Message": "Call hangup successfully"}

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value=partner_config
        )
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.hangup_call.return_value = vendor_response
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )

        await service.hangup_call(
            "abc123", user_id=123, partner_id=456, enable_ai_bridge=True
        )

        service._CallService__helper.get_vendor_handler.assert_awaited_once_with(
            "vendor123", AI_BRIDGE_VENDOR_CONFIG_ID
        )

    @pytest.mark.asyncio
    async def test_hangup_call_vendor_raises_value_error(self):
        service, _ = make_service()

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value={"vendor_id": "vendor123", "vendor_config_id": "config456"}
        )
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.hangup_call.side_effect = ValueError("vendor error")
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )

        with pytest.raises(ValueError):
            await service.hangup_call("abc123", user_id=123, partner_id=456)


class TestCallServiceTransferCall:
    @pytest.mark.asyncio
    async def test_transfer_call_uses_partner_vendor_config_id(self):
        service, _ = make_service()

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value={"vendor_id": "vendor123", "vendor_config_id": "config456"}
        )
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.transfer_call.return_value = {"Success": True}
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )

        await service.transfer_call("abc123", "9999999999", partner_id=456)

        service._CallService__helper.get_vendor_handler.assert_awaited_once_with(
            "vendor123", "config456"
        )
        mock_vendor_handler.transfer_call.assert_awaited_once_with(
            "abc123", "9999999999"
        )

    @pytest.mark.asyncio
    async def test_transfer_call_ai_bridge_uses_hardcoded_vendor_config_id(self):
        service, _ = make_service()

        partner_config = {
            "vendor_id": "vendor123",
            "vendor_config_id": "config456",
            "ai_vendor_config_id": "should-be-ignored",
        }
        service._CallService__helper.get_partner_config = AsyncMock(
            return_value=partner_config
        )
        mock_vendor_handler = AsyncMock()
        mock_vendor_handler.transfer_call.return_value = {"Success": True}
        service._CallService__helper.get_vendor_handler = AsyncMock(
            return_value=mock_vendor_handler
        )

        await service.transfer_call(
            "abc123", "9999999999", partner_id=456, enable_ai_bridge=True
        )

        service._CallService__helper.get_vendor_handler.assert_awaited_once_with(
            "vendor123", AI_BRIDGE_VENDOR_CONFIG_ID
        )

    @pytest.mark.asyncio
    async def test_transfer_call_missing_vendor_id(self):
        service, _ = make_service()

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value={"vendor_config_id": "config456"}
        )

        with pytest.raises(ResourceNotFound):
            await service.transfer_call("abc123", "9999999999", partner_id=456)

    @pytest.mark.asyncio
    async def test_transfer_call_missing_vendor_config_id(self):
        service, _ = make_service()

        service._CallService__helper.get_partner_config = AsyncMock(
            return_value={"vendor_id": "vendor123"}
        )

        with pytest.raises(ResourceNotFound):
            await service.transfer_call("abc123", "9999999999", partner_id=456)


class TestPreCreateSessionCallId:
    """
    _pre_create_session no longer polls live_calls or backfills the CDR —
    the real vendor call_id is now resolved and injected entirely from the
    PSTN side (best-effort live_calls poll + LiveKit data-channel backfill
    in pstn/services.py Step 6, merged into context_data by the makun-ai
    worker). This only covers the pass-through of a genuine already-known
    call_id, and confirms an absent one is simply omitted — no polling.
    """

    def _make_did_record(self):
        return {
            "is_active": True,
            "did_type": "normal",
            "agent_id": 555,
            "partner_id": 999,
        }

    def _make_makunai_response(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(
            return_value={
                "data": {
                    "room_name": "room-1",
                    "caller_token": "token-1",
                    "livekit_url": "wss://livekit.example.com",
                    "greeting_audio": None,
                }
            }
        )
        return resp

    @pytest.mark.asyncio
    async def test_missing_call_id_omitted_from_payload(self):
        service, deps = make_service()
        did_repository = deps["did_repository"]
        did_repository.get_did_by_number = AsyncMock(
            return_value=self._make_did_record()
        )

        service._CallService__redis_helper.store_outbound_room = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b"cached-api-key")

        with patch(
            "src.components.cache.redis_client.get_redis_client",
            AsyncMock(return_value=mock_redis),
        ), patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=self._make_makunai_response(),
        ) as mock_post:
            await service._pre_create_session(
                to_number="918103492952",
                vendor_config_id="config456",
                context_data={"lead_id": 42},
                caller_did="917965802977",
                caller_phone="+918103492952",
                fallback_payload={"created_at": 1},
                fallback_store_key="918103492952",
                call_id="None",
            )

        sent_payload = mock_post.call_args.kwargs["json"]
        assert sent_payload["external_call_sid"] is None
        assert sent_payload["partner_id"] == 999
        assert "call_id" not in sent_payload["context_data"]
        assert sent_payload["context_data"]["lead_id"] == 42

    @pytest.mark.asyncio
    async def test_genuine_call_id_passed_through(self):
        service, deps = make_service()
        did_repository = deps["did_repository"]
        did_repository.get_did_by_number = AsyncMock(
            return_value=self._make_did_record()
        )

        service._CallService__redis_helper.store_outbound_room = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b"cached-api-key")

        with patch(
            "src.components.cache.redis_client.get_redis_client",
            AsyncMock(return_value=mock_redis),
        ), patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=self._make_makunai_response(),
        ) as mock_post:
            await service._pre_create_session(
                to_number="918103492952",
                vendor_config_id="config456",
                context_data={},
                caller_did="917965802977",
                caller_phone="+918103492952",
                fallback_payload={"created_at": 1},
                fallback_store_key="918103492952",
                call_id="CAXX-already-known",
            )

        sent_payload = mock_post.call_args.kwargs["json"]
        assert sent_payload["external_call_sid"] == "CAXX-already-known"
        assert sent_payload["partner_id"] == 999
        assert sent_payload["context_data"]["call_id"] == "CAXX-already-known"

    @pytest.mark.asyncio
    async def test_room_payload_carries_context_data(self):
        """The pre-warmed room stored in redis must include context_data
        (with cdr_id) — this is the ONLY path handle_call()'s fast/pre-warmed
        branch reads ctx.context_data from; without it here, that branch
        never has a cdr_id for _backfill_real_vendor_call_id to use."""
        service, deps = make_service()
        did_repository = deps["did_repository"]
        did_repository.get_did_by_number = AsyncMock(
            return_value=self._make_did_record()
        )

        mock_store = AsyncMock()
        service._CallService__redis_helper.store_outbound_room = mock_store

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b"cached-api-key")

        with patch(
            "src.components.cache.redis_client.get_redis_client",
            AsyncMock(return_value=mock_redis),
        ), patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=self._make_makunai_response(),
        ):
            await service._pre_create_session(
                to_number="918103492952",
                vendor_config_id="config456",
                context_data={"cdr_id": "cdr-xyz-789", "campaign_id": "7"},
                caller_did="917965802977",
                caller_phone="+918103492952",
                fallback_payload={"created_at": 1},
                fallback_store_key="918103492952",
                call_id="None",
            )

        mock_store.assert_awaited_once()
        _, kwargs = mock_store.call_args
        stored_payload = mock_store.call_args[0][1]
        assert stored_payload["context_data"]["cdr_id"] == "cdr-xyz-789"
        assert stored_payload["context_data"]["campaign_id"] == "7"
