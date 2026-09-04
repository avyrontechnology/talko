import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from src.components.call_management.agent_dialplan_resolver import (
    AgentDialPlanResolver,
    DialplanResponseBuilder,
    TransferTarget,
)
from src.components.call_management.enums import InboundType


@pytest.fixture
def mock_logger():
    """Mock logger"""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.debug = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    return logger


@pytest.fixture
def mock_maglo_client():
    """Mock MagloClient"""
    client = MagicMock()
    client.get_agent_details = AsyncMock()
    client.upsert_ivr_lead = AsyncMock()
    client.reassign_lead_by_phone = AsyncMock()
    return client


@pytest.fixture
def mock_agent_mapping_repo():
    """Mock AgentMappingRepository"""
    repo = MagicMock()
    repo.get_agents_by_service_board_id_and_partner_id = AsyncMock()
    return repo


@pytest.fixture
def mock_user_service_client():
    """Mock UserServiceClient"""
    client = MagicMock()
    client.get_users_availability_status = AsyncMock()
    return client


@pytest_asyncio.fixture
async def resolver(mock_maglo_client, mock_agent_mapping_repo, mock_logger):
    """Create AgentDialPlanResolver instance"""
    return AgentDialPlanResolver(
        maglo_client=mock_maglo_client,
        agent_mapping_repo=mock_agent_mapping_repo,
        logger=mock_logger,
    )


@pytest_asyncio.fixture
async def resolver_with_availability(
    mock_maglo_client, mock_agent_mapping_repo, mock_logger, mock_user_service_client
):
    """Create AgentDialPlanResolver instance wired with a user_service_client"""
    return AgentDialPlanResolver(
        maglo_client=mock_maglo_client,
        agent_mapping_repo=mock_agent_mapping_repo,
        logger=mock_logger,
        user_service_client=mock_user_service_client,
    )


class TestTransferTarget:
    """Tests for TransferTarget dataclass"""

    def test_transfer_target_creation(self):
        """Test creating a TransferTarget with all fields"""
        target = TransferTarget(
            type="agent",
            data=["ext123"],
            ring_type="simultaneous",
            skip_active=True,
        )

        assert target.type == "agent"
        assert target.data == ["ext123"]
        assert target.ring_type == "simultaneous"
        assert target.skip_active is True

    def test_transfer_target_defaults(self):
        """Test TransferTarget default values"""
        target = TransferTarget(type="number", data=["1234567890"])

        assert target.ring_type == "simultaneous"
        assert target.skip_active is False

    def test_transfer_target_empty_data(self):
        """Test TransferTarget with empty data list"""
        target = TransferTarget(type="number", data=[])

        assert target.data == []
        assert target.type == "number"


class TestAgentDialPlanResolver:
    """Tests for AgentDialPlanResolver"""

    @pytest.mark.asyncio
    async def test_resolve_for_single_agent_with_cloud_enabled(
        self, resolver, mock_maglo_client, mock_logger
    ):
        """Test resolving single agent with cloud phonic enabled"""
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "name": "Test Agent",
            "number": "+919876543210",
            "extension": "ext123",
            "internet_calling_enable": True,
        }

        result = await resolver.resolve_for_single_agent(
            partner_id=12,
            service_board_id=70,
            agent_id=33,
            fallback_agent_number="+919876543210",
        )

        assert result.type == "agent"
        assert result.data == ["ext123"]
        assert result.ring_type == "simultaneous"
        assert result.skip_active is False

    @pytest.mark.asyncio
    async def test_resolve_for_single_agent_cloud_disabled(
        self, resolver, mock_maglo_client
    ):
        """Test resolving single agent with cloud phonic disabled"""
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "name": "Test Agent",
            "number": "+919876543210",
            "extension": "ext123",
            "internet_calling_enable": False,
        }

        result = await resolver.resolve_for_single_agent(
            partner_id=12,
            service_board_id=70,
            agent_id=33,
            fallback_agent_number="+919876543210",
        )

        assert result.type == "number"
        assert result.data == ["+919876543210"]

    @pytest.mark.asyncio
    async def test_resolve_for_single_agent_no_extension(
        self, resolver, mock_maglo_client
    ):
        """Test resolving single agent with cloud enabled but no extension"""
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "name": "Test Agent",
            "number": "+919876543210",
            "extension": None,
            "internet_calling_enable": True,
        }

        result = await resolver.resolve_for_single_agent(
            partner_id=12,
            service_board_id=70,
            agent_id=33,
            fallback_agent_number="+919876543210",
        )

        assert result.type == "number"
        assert result.data == ["+919876543210"]

    @pytest.mark.asyncio
    async def test_resolve_for_single_agent_no_fallback(
        self, resolver, mock_maglo_client, mock_logger
    ):
        """Test resolving single agent with neither a live Maglo number nor a
        fallback number available"""
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "name": "Test Agent",
            "number": None,
            "extension": None,
            "internet_calling_enable": False,
        }

        result = await resolver.resolve_for_single_agent(
            partner_id=12,
            service_board_id=70,
            agent_id=33,
            fallback_agent_number=None,
        )

        assert result.type == "number"
        assert result.data == []
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_resolve_for_single_agent_prefers_live_number_over_stale_fallback(
        self, resolver, mock_maglo_client
    ):
        """Regression test: the CDR-cached fallback number can go stale (e.g.
        after the assigned agent changes) while Maglo still has the current
        agent's real number — the live number must win."""
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "name": "Test Agent",
            "number": "+918839749767",
            "extension": None,
            "internet_calling_enable": False,
        }

        result = await resolver.resolve_for_single_agent(
            partner_id=12,
            service_board_id=70,
            agent_id=33,
            # Stale number left over from a previous agent/CDR — must be
            # ignored in favor of the live Maglo number above.
            fallback_agent_number="+919311634345",
        )

        assert result.type == "number"
        assert result.data == ["+918839749767"]

    @pytest.mark.asyncio
    async def test_resolve_inbound_no_cdr_with_assigned_agent(
        self, resolver, mock_maglo_client
    ):
        """Test resolve_inbound_no_cdr when lead has assigned agent"""
        mock_maglo_client.upsert_ivr_lead.return_value = {
            "id": 100,
            "name": "Test Lead",
            "lead_request_id": 100,  # This is what gets returned as lead_id
            "assigned_to": 33,
        }

        # Mock agent details
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "name": "Test Agent",
            "number": "+919876543210",
            "extension": "ext123",
            "internet_calling_enable": True,
        }

        result = await resolver.resolve_inbound_no_cdr(
            customer_number="+919999999999",
            call_to_number="+918888888888",
            partner_id=12,
            service_board_id=70,
            create_lead=True,
        )

        assert result["lead_id"] == 100
        assert result["lead_name"] == "Test Lead"
        assert result["agent_id"] == 33
        assert result["target"].type == "agent"
        assert result["target"].data == ["ext123"]
        assert len(result["agent_ids"]) == 1
        assert result["agent_ids"][0]["agent_id"] == 33

    @pytest.mark.asyncio
    async def test_resolve_inbound_no_cdr_no_assigned_agent(
        self, resolver, mock_maglo_client, mock_agent_mapping_repo
    ):
        """Test resolve_inbound_no_cdr when no agent is assigned"""
        mock_maglo_client.upsert_ivr_lead.return_value = {
            "id": 100,
            "name": "Test Lead",
            "lead_request_id": 100,  # This is what gets returned as lead_id
            "assigned_to": None,
        }

        # Mock service board agents
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]

        # Mock agent details for multiple agents
        mock_maglo_client.get_agent_details.side_effect = [
            {
                "id": 33,
                "name": "Agent 1",
                "number": "+919876543210",
                "extension": "ext123",
                "internet_calling_enable": True,
            },
            {
                "id": 34,
                "name": "Agent 2",
                "number": "+919876543211",
                "extension": None,
                "internet_calling_enable": False,
            },
        ]

        result = await resolver.resolve_inbound_no_cdr(
            customer_number="+919999999999",
            call_to_number="+918888888888",
            partner_id=12,
            service_board_id=70,
            create_lead=True,
        )

        assert result["lead_id"] == 100
        assert result["agent_id"] is None
        assert result["target"].type == "agent"
        assert len(result["agent_ids"]) == 2
        assert "ext123" in result["target"].data
        assert result["inbound_round_robin_next_index"] is None

    @pytest.mark.asyncio
    async def test_resolve_inbound_no_cdr_round_robin_returns_next_index(
        self, resolver, mock_maglo_client, mock_agent_mapping_repo
    ):
        """When inbound round robin is enabled, the advanced cursor flows through to the result"""
        mock_maglo_client.upsert_ivr_lead.return_value = {
            "id": 100,
            "name": "Test Lead",
            "lead_request_id": 100,
            "assigned_to": None,
        }
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]
        mock_maglo_client.get_agent_details.side_effect = [
            {"id": 34, "extension": None, "internet_calling_enable": False},
            {"id": 33, "extension": None, "internet_calling_enable": False},
        ]

        result = await resolver.resolve_inbound_no_cdr(
            customer_number="+919999999999",
            call_to_number="+918888888888",
            partner_id=12,
            service_board_id=70,
            create_lead=True,
            enable_inbound_round_robin=True,
            inbound_round_robin_index=1,
        )

        assert result["target"].ring_type == "order_by"
        assert result["target"].data == ["+919876543211"]
        assert result["agent_id"] == 34
        assert result["agent_number"] == "+919876543211"
        assert [a["agent_id"] for a in result["agent_ids"]] == [34]
        assert result["inbound_round_robin_next_index"] == 0

    @pytest.mark.asyncio
    async def test_resolve_inbound_no_cdr_lead_upsert_fails(
        self, resolver, mock_maglo_client, mock_agent_mapping_repo, mock_logger
    ):
        """Test resolve_inbound_no_cdr when lead upsert fails"""
        # Mock lead creation failure
        mock_maglo_client.upsert_ivr_lead.side_effect = Exception("API Error")

        # Mock service board agents (fallback path)
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"}
        ]

        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "name": "Agent",
            "number": "+919876543210",
            "extension": None,
            "internet_calling_enable": False,
        }

        # FIXED: Added create_lead=True to trigger the lead creation code path
        result = await resolver.resolve_inbound_no_cdr(
            customer_number="+919999999999",
            call_to_number="+918888888888",
            partner_id=12,
            service_board_id=70,
            create_lead=True,
        )

        assert result["lead_id"] is None
        assert result["lead_name"] is None
        assert result["agent_id"] is None
        mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_resolve_single_assigned_agent_cloud_enabled(
        self, resolver, mock_maglo_client
    ):
        """Test _resolve_single_assigned_agent with cloud enabled"""
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "name": "Test Agent",
            "number": "+919876543210",
            "extension": "ext123",
            "internet_calling_enable": True,
        }

        target, agent_ids = await resolver._resolve_single_assigned_agent(
            partner_id=12, service_board_id=70, agent_id=33
        )

        assert target.type == "agent"
        assert target.data == ["ext123"]
        assert len(agent_ids) == 1
        assert agent_ids[0]["agent_id"] == 33
        assert agent_ids[0]["cloud_agent_number"] == "ext123"

    @pytest.mark.asyncio
    async def test_resolve_single_assigned_agent_cloud_disabled(
        self, resolver, mock_maglo_client
    ):
        """Test _resolve_single_assigned_agent with cloud disabled"""
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "name": "Test Agent",
            "number": "+919876543210",
            "extension": None,
            "internet_calling_enable": False,
        }

        target, agent_ids = await resolver._resolve_single_assigned_agent(
            partner_id=12, service_board_id=70, agent_id=33
        )

        assert target.type == "number"
        assert target.data == ["+919876543210"]
        assert agent_ids[0]["cloud_agent_number"] is None

    @pytest.mark.asyncio
    async def test_resolve_all_service_board_agents_mixed_cloud(
        self, resolver, mock_maglo_client, mock_agent_mapping_repo
    ):
        """Test _resolve_all_service_board_agents with mix of cloud and regular"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]

        mock_maglo_client.get_agent_details.side_effect = [
            {
                "id": 33,
                "extension": "ext123",
                "internet_calling_enable": True,
                "number": "+919876543210",
            },
            {
                "id": 34,
                "extension": None,
                "internet_calling_enable": False,
                "number": "+919876543211",
            },
        ]

        target, agent_ids, _ = await resolver._resolve_all_service_board_agents(
            partner_id=12, service_board_id=70
        )

        assert target.type == "agent"
        assert "ext123" in target.data
        assert "+919876543211" in target.data
        assert target.ring_type == "simultaneous"
        assert len(agent_ids) == 2

    @pytest.mark.asyncio
    async def test_resolve_all_service_board_agents_no_agents(
        self, resolver, mock_agent_mapping_repo, mock_logger
    ):
        """Test _resolve_all_service_board_agents when no agents exist"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = (
            []
        )

        target, agent_ids, _ = await resolver._resolve_all_service_board_agents(
            partner_id=12, service_board_id=70
        )

        assert target.type == "number"
        assert target.data == []
        assert agent_ids == []
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_resolve_all_service_board_agents_round_robin_disabled_by_default(
        self, resolver, mock_maglo_client, mock_agent_mapping_repo
    ):
        """Without enable_inbound_round_robin, ring order and ring_type are unchanged"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]
        mock_maglo_client.get_agent_details.side_effect = [
            {"id": 33, "extension": None, "internet_calling_enable": False},
            {"id": 34, "extension": None, "internet_calling_enable": False},
        ]

        target, agent_ids, next_index = (
            await resolver._resolve_all_service_board_agents(
                partner_id=12, service_board_id=70
            )
        )

        assert target.ring_type == "simultaneous"
        assert target.data == ["+919876543210", "+919876543211"]
        assert next_index is None

    @pytest.mark.asyncio
    async def test_resolve_all_service_board_agents_round_robin_rotates_from_index(
        self, resolver, mock_maglo_client, mock_agent_mapping_repo
    ):
        """With round robin enabled, only the cursor agent is rung and ring_type is order_by"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
            {"agent_id": 35, "agent_number": "+919876543212"},
        ]
        mock_maglo_client.get_agent_details.side_effect = [
            {"id": 34, "extension": None, "internet_calling_enable": False},
            {"id": 35, "extension": None, "internet_calling_enable": False},
            {"id": 33, "extension": None, "internet_calling_enable": False},
        ]

        target, agent_ids, next_index = (
            await resolver._resolve_all_service_board_agents(
                partner_id=12,
                service_board_id=70,
                enable_inbound_round_robin=True,
                inbound_round_robin_index=1,
            )
        )

        assert target.ring_type == "order_by"
        assert target.data == ["+919876543211"]
        assert [a["agent_id"] for a in agent_ids] == [34]
        assert next_index == 2

    @pytest.mark.asyncio
    async def test_resolve_all_service_board_agents_round_robin_wraps_index(
        self, resolver, mock_maglo_client, mock_agent_mapping_repo
    ):
        """The cursor wraps modulo the current agent count"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]
        mock_maglo_client.get_agent_details.side_effect = [
            {"id": 33, "extension": None, "internet_calling_enable": False},
            {"id": 34, "extension": None, "internet_calling_enable": False},
        ]

        target, agent_ids, next_index = (
            await resolver._resolve_all_service_board_agents(
                partner_id=12,
                service_board_id=70,
                enable_inbound_round_robin=True,
                inbound_round_robin_index=5,
            )
        )

        # 5 % 2 == 1, so the cursor agent is the second one; only it is rung.
        assert target.data == ["+919876543211"]
        assert [a["agent_id"] for a in agent_ids] == [34]
        assert next_index == 0

    @pytest.mark.asyncio
    async def test_resolve_all_service_board_agents_round_robin_no_agents_returns_none_index(
        self, resolver, mock_agent_mapping_repo
    ):
        """Round robin cursor stays unset when there's nobody to ring"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = (
            []
        )

        target, agent_ids, next_index = (
            await resolver._resolve_all_service_board_agents(
                partner_id=12,
                service_board_id=70,
                enable_inbound_round_robin=True,
                inbound_round_robin_index=0,
            )
        )

        assert target.data == []
        assert next_index is None

    @pytest.mark.asyncio
    async def test_resolve_all_service_board_agents_all_cloud(
        self, resolver, mock_maglo_client, mock_agent_mapping_repo
    ):
        """Test _resolve_all_service_board_agents when all agents use cloud"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]

        mock_maglo_client.get_agent_details.side_effect = [
            {
                "id": 33,
                "extension": "ext123",
                "internet_calling_enable": True,
            },
            {
                "id": 34,
                "extension": "ext456",
                "internet_calling_enable": True,
            },
        ]

        target, agent_ids, _ = await resolver._resolve_all_service_board_agents(
            partner_id=12, service_board_id=70
        )

        assert target.type == "agent"
        assert target.data == ["ext123", "ext456"]

    @pytest.mark.asyncio
    async def test_no_user_service_client_rings_everyone_unfiltered(
        self, resolver, mock_maglo_client, mock_agent_mapping_repo
    ):
        """Without a user_service_client wired, no availability filtering happens"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]
        mock_maglo_client.get_agent_details.side_effect = [
            {"id": 33, "extension": None, "internet_calling_enable": False},
            {"id": 34, "extension": None, "internet_calling_enable": False},
        ]

        target, agent_ids, _ = await resolver._resolve_all_service_board_agents(
            partner_id=12, service_board_id=70
        )

        assert len(agent_ids) == 2
        assert set(target.data) == {"+919876543210", "+919876543211"}

    @pytest.mark.asyncio
    async def test_filters_out_inactive_agents(
        self,
        resolver_with_availability,
        mock_maglo_client,
        mock_agent_mapping_repo,
        mock_user_service_client,
    ):
        """Agents whose status isn't Active are excluded from the ring list"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]
        mock_user_service_client.get_users_availability_status.return_value = {
            33: "Active",
            34: "On Break",
        }
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "extension": None,
            "internet_calling_enable": False,
        }

        target, agent_ids, _ = (
            await resolver_with_availability._resolve_all_service_board_agents(
                partner_id=12, service_board_id=70
            )
        )

        mock_user_service_client.get_users_availability_status.assert_awaited_once_with(
            [33, 34]
        )
        assert len(agent_ids) == 1
        assert agent_ids[0]["agent_id"] == 33
        assert target.data == ["+919876543210"]

    @pytest.mark.asyncio
    async def test_missing_status_defaults_to_active(
        self,
        resolver_with_availability,
        mock_maglo_client,
        mock_agent_mapping_repo,
        mock_user_service_client,
    ):
        """Agents absent from the availability map are treated as Active"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]
        # Only agent 33 has a known status; 34 is missing from the response.
        mock_user_service_client.get_users_availability_status.return_value = {
            33: "Active",
        }
        mock_maglo_client.get_agent_details.side_effect = [
            {"id": 33, "extension": None, "internet_calling_enable": False},
            {"id": 34, "extension": None, "internet_calling_enable": False},
        ]

        target, agent_ids, _ = (
            await resolver_with_availability._resolve_all_service_board_agents(
                partner_id=12, service_board_id=70
            )
        )

        assert len(agent_ids) == 2
        assert set(target.data) == {"+919876543210", "+919876543211"}

    @pytest.mark.asyncio
    async def test_all_agents_unavailable_rings_everyone(
        self,
        resolver_with_availability,
        mock_maglo_client,
        mock_agent_mapping_repo,
        mock_user_service_client,
        mock_logger,
    ):
        """If every agent on the board is unavailable, fail open and ring all of them"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]
        mock_user_service_client.get_users_availability_status.return_value = {
            33: "On Break",
            34: "Offline",
        }
        mock_maglo_client.get_agent_details.side_effect = [
            {"id": 33, "extension": None, "internet_calling_enable": False},
            {"id": 34, "extension": None, "internet_calling_enable": False},
        ]

        target, agent_ids, _ = (
            await resolver_with_availability._resolve_all_service_board_agents(
                partner_id=12, service_board_id=70
            )
        )

        assert len(agent_ids) == 2
        assert set(target.data) == {"+919876543210", "+919876543211"}
        mock_logger.info.assert_any_call(
            "No agents with Active status among {}. Ringing full agent list.".format(
                [33, 34]
            )
        )

    @pytest.mark.asyncio
    async def test_availability_lookup_failure_rings_everyone(
        self,
        resolver_with_availability,
        mock_maglo_client,
        mock_agent_mapping_repo,
        mock_user_service_client,
        mock_logger,
    ):
        """If the availability gRPC call raises, fail open and ring the full board"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]
        mock_user_service_client.get_users_availability_status.side_effect = Exception(
            "console-service unavailable"
        )
        mock_maglo_client.get_agent_details.side_effect = [
            {"id": 33, "extension": None, "internet_calling_enable": False},
            {"id": 34, "extension": None, "internet_calling_enable": False},
        ]

        target, agent_ids, _ = (
            await resolver_with_availability._resolve_all_service_board_agents(
                partner_id=12, service_board_id=70
            )
        )

        assert len(agent_ids) == 2
        assert set(target.data) == {"+919876543210", "+919876543211"}
        mock_logger.warning.assert_called()

    def test_map_transfer_to_inbound_fields_number_type(self, resolver):
        """Test mapping transfer target with type 'number'"""
        target = TransferTarget(type="number", data=["+919876543210"])

        inbound_type, cloud_number = resolver.map_transfer_to_inbound_fields(target)

        assert inbound_type == InboundType.PHONE_NUMBER.value
        assert cloud_number is None

    def test_map_transfer_to_inbound_fields_agent_type(self, resolver):
        """Test mapping transfer target with type 'agent'"""
        target = TransferTarget(type="agent", data=["ext123"])

        inbound_type, cloud_number = resolver.map_transfer_to_inbound_fields(target)

        assert inbound_type == InboundType.SOFT_PHONE.value
        assert cloud_number == "ext123"

    def test_map_transfer_to_inbound_fields_agent_empty_data(self, resolver):
        """Test mapping transfer target with agent type but empty data"""
        target = TransferTarget(type="agent", data=[])

        inbound_type, cloud_number = resolver.map_transfer_to_inbound_fields(target)

        assert inbound_type == InboundType.SOFT_PHONE.value
        assert cloud_number is None

    def test_map_transfer_to_inbound_fields_none_target(self, resolver):
        """Test mapping when target is None"""
        inbound_type, cloud_number = resolver.map_transfer_to_inbound_fields(None)

        assert inbound_type == InboundType.PHONE_NUMBER.value
        assert cloud_number is None

    def test_map_transfer_to_inbound_fields_unknown_type(self, resolver, mock_logger):
        """Test mapping transfer target with unknown type"""
        target = TransferTarget(type="unknown", data=["data"])

        inbound_type, cloud_number = resolver.map_transfer_to_inbound_fields(target)

        assert inbound_type == InboundType.PHONE_NUMBER.value
        assert cloud_number is None
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_get_or_create_lead_success(self, resolver, mock_maglo_client):
        """Test successful lead upsert"""
        mock_maglo_client.upsert_ivr_lead.return_value = {
            "id": 100,
            "name": "Test Lead",
            "assigned_to": 33,
        }

        lead_id, lead_name, assigned_agent_id = await resolver._get_or_create_lead(
            customer_number="+919999999999",
            partner_id=12,
            service_board_id=70,
        )

        assert lead_id == 100
        assert lead_name == "Test Lead"
        assert assigned_agent_id == 33

    @pytest.mark.asyncio
    async def test_get_or_create_lead_failure(
        self, resolver, mock_maglo_client, mock_logger
    ):
        """Test lead upsert failure"""
        mock_maglo_client.upsert_ivr_lead.side_effect = Exception("API Error")

        lead_id, lead_name, assigned_agent_id = await resolver._get_or_create_lead(
            customer_number="+919999999999",
            partner_id=12,
            service_board_id=70,
        )

        assert lead_id is None
        assert lead_name is None
        assert assigned_agent_id is None
        mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_cloud_phonic_info_success(self, resolver, mock_maglo_client):
        """Test successful cloud phonic info retrieval"""
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "name": "Test Agent",
            "number": "+919876543210",
            "extension": "ext123",
            "internet_calling_enable": True,
        }

        (
            is_cloud,
            extension,
            agent_id,
            agent_name,
            agent_number,
        ) = await resolver._get_cloud_phonic_info(
            partner_id=12, service_board_id=70, agent_id=33
        )

        assert is_cloud is True
        assert extension == "ext123"
        assert agent_id == 33
        assert agent_name == "Test Agent"
        assert agent_number == "+919876543210"

    @pytest.mark.asyncio
    async def test_get_cloud_phonic_info_404_error(
        self, resolver, mock_maglo_client, mock_logger
    ):
        """Test cloud phonic info with 404 error"""
        mock_maglo_client.get_agent_details.side_effect = ValueError(
            "Maglo error 404: Service board with id not found"
        )

        result = await resolver._get_cloud_phonic_info(
            partner_id=12, service_board_id=70, agent_id=33
        )

        assert result == (False, None, None, None, None)
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_get_cloud_phonic_info_general_error(
        self, resolver, mock_maglo_client, mock_logger
    ):
        """Test cloud phonic info with general error"""
        mock_maglo_client.get_agent_details.side_effect = Exception("Connection error")

        result = await resolver._get_cloud_phonic_info(
            partner_id=12, service_board_id=70, agent_id=33
        )

        assert result == (False, None, None, None, None)
        mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_cloud_phonic_info_missing_fields(
        self, resolver, mock_maglo_client
    ):
        """Test cloud phonic info with missing optional fields"""
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
        }

        (
            is_cloud,
            extension,
            agent_id,
            agent_name,
            agent_number,
        ) = await resolver._get_cloud_phonic_info(
            partner_id=12, service_board_id=70, agent_id=33
        )

        assert is_cloud is False
        assert extension is None
        assert agent_id == 33
        assert agent_name is None
        assert agent_number is None


class TestIsAgentInactive:
    """Tests for AgentDialPlanResolver._is_agent_inactive"""

    @pytest.mark.asyncio
    async def test_no_user_service_client_defaults_to_not_inactive(self, resolver):
        """Without a client wired, we can't confirm inactivity, so fail open"""
        assert await resolver._is_agent_inactive(33) is False

    @pytest.mark.asyncio
    async def test_confirmed_active_is_not_inactive(
        self, resolver_with_availability, mock_user_service_client
    ):
        mock_user_service_client.get_users_availability_status.return_value = {
            33: "Active"
        }

        assert await resolver_with_availability._is_agent_inactive(33) is False

    @pytest.mark.asyncio
    async def test_confirmed_non_active_is_inactive(
        self, resolver_with_availability, mock_user_service_client
    ):
        mock_user_service_client.get_users_availability_status.return_value = {
            33: "On Break"
        }

        assert await resolver_with_availability._is_agent_inactive(33) is True

    @pytest.mark.asyncio
    async def test_missing_status_defaults_to_not_inactive(
        self, resolver_with_availability, mock_user_service_client
    ):
        mock_user_service_client.get_users_availability_status.return_value = {}

        assert await resolver_with_availability._is_agent_inactive(33) is False

    @pytest.mark.asyncio
    async def test_lookup_failure_defaults_to_not_inactive(
        self, resolver_with_availability, mock_user_service_client, mock_logger
    ):
        mock_user_service_client.get_users_availability_status.side_effect = Exception(
            "console-service unavailable"
        )

        assert await resolver_with_availability._is_agent_inactive(33) is False
        mock_logger.warning.assert_called()


class TestReassignToActiveAgent:
    """Tests for AgentDialPlanResolver._reassign_to_active_agent"""

    @pytest.mark.asyncio
    async def test_no_other_agents_on_board_keeps_original(
        self, resolver, mock_agent_mapping_repo, mock_logger
    ):
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"}
        ]

        new_agent_id, reassigned_lead_id = await resolver._reassign_to_active_agent(
            partner_id=12,
            service_board_id=70,
            current_agent_id=33,
            customer_number="+919999999999",
        )

        assert new_agent_id is None
        assert reassigned_lead_id is None
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_picks_active_peer_and_fires_maglo_notification(
        self,
        resolver_with_availability,
        mock_agent_mapping_repo,
        mock_user_service_client,
        mock_maglo_client,
        monkeypatch,
    ):
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
            {"agent_id": 35, "agent_number": "+919876543212"},
        ]
        # Agent 33 is the (inactive) current owner and is excluded from
        # candidates before filtering; of the remaining two, only 34 is Active.
        mock_user_service_client.get_users_availability_status.return_value = {
            34: "Active",
            35: "On Break",
        }
        mock_maglo_client.reassign_lead_by_phone.return_value = {
            "lead_request_id": 179245,
            "lead_name": "Saurav Singh",
            "assigned_to": 34,
            "phone_number": "+919999999999",
        }

        new_agent_id, reassigned_lead_id = (
            await resolver_with_availability._reassign_to_active_agent(
                partner_id=12,
                service_board_id=70,
                current_agent_id=33,
                customer_number="+919999999999",
            )
        )

        assert new_agent_id == 34
        # The Maglo call is now awaited inline so its confirmed lead_request_id
        # can flow back onto the current call's CDR.
        assert reassigned_lead_id == 179245

        mock_maglo_client.reassign_lead_by_phone.assert_awaited_once_with(
            phone_number="+919999999999",
            partner_id=12,
            service_board_id=70,
            agent_id=34,
        )

    @pytest.mark.asyncio
    async def test_no_customer_number_skips_maglo_notification(
        self,
        resolver_with_availability,
        mock_agent_mapping_repo,
        mock_user_service_client,
        mock_maglo_client,
    ):
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]
        mock_user_service_client.get_users_availability_status.return_value = {
            34: "Active"
        }

        new_agent_id, reassigned_lead_id = (
            await resolver_with_availability._reassign_to_active_agent(
                partner_id=12,
                service_board_id=70,
                current_agent_id=33,
                customer_number=None,
            )
        )

        assert new_agent_id == 34
        assert reassigned_lead_id is None
        mock_maglo_client.reassign_lead_by_phone.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_maglo_notification_failure_is_swallowed(
        self,
        resolver_with_availability,
        mock_agent_mapping_repo,
        mock_user_service_client,
        mock_maglo_client,
        mock_logger,
    ):
        """A failed CRM update must never bubble up and affect the live call"""
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]
        mock_user_service_client.get_users_availability_status.return_value = {
            34: "Active"
        }
        mock_maglo_client.reassign_lead_by_phone.side_effect = Exception(
            "Maglo API down"
        )

        new_agent_id, reassigned_lead_id = (
            await resolver_with_availability._reassign_to_active_agent(
                partner_id=12,
                service_board_id=70,
                current_agent_id=33,
                customer_number="+919999999999",
            )
        )

        assert new_agent_id == 34
        assert reassigned_lead_id is None
        mock_logger.error.assert_called()


class TestResolveSingleAssignedAgentReassignment:
    """Tests for the reassign_inactive_agent branch of _resolve_single_assigned_agent"""

    @pytest.mark.asyncio
    async def test_flag_off_never_checks_availability(
        self, resolver_with_availability, mock_maglo_client, mock_user_service_client
    ):
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "number": "+919876543210",
            "extension": None,
            "internet_calling_enable": False,
        }

        target, agent_ids = (
            await resolver_with_availability._resolve_single_assigned_agent(
                partner_id=12,
                service_board_id=70,
                agent_id=33,
                reassign_inactive_agent=False,
            )
        )

        assert agent_ids[0]["agent_id"] == 33
        mock_user_service_client.get_users_availability_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_flag_on_active_agent_not_reassigned(
        self,
        resolver_with_availability,
        mock_maglo_client,
        mock_user_service_client,
        mock_agent_mapping_repo,
    ):
        mock_user_service_client.get_users_availability_status.return_value = {
            33: "Active"
        }
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "number": "+919876543210",
            "extension": None,
            "internet_calling_enable": False,
        }

        target, agent_ids = (
            await resolver_with_availability._resolve_single_assigned_agent(
                partner_id=12,
                service_board_id=70,
                agent_id=33,
                reassign_inactive_agent=True,
                customer_number="+919999999999",
            )
        )

        assert agent_ids[0]["agent_id"] == 33
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_flag_on_inactive_agent_reassigned_to_peer(
        self,
        resolver_with_availability,
        mock_maglo_client,
        mock_user_service_client,
        mock_agent_mapping_repo,
    ):
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]

        # First availability lookup is the single-agent _is_agent_inactive
        # check (agent 33, "On Break" → inactive); second is the board-wide
        # filter inside _reassign_to_active_agent (agent 34 is Active).
        mock_user_service_client.get_users_availability_status.side_effect = [
            {33: "On Break"},
            {34: "Active"},
        ]
        mock_maglo_client.get_agent_details.return_value = {
            "id": 34,
            "number": "+919876543211",
            "extension": "ext456",
            "internet_calling_enable": True,
        }

        target, agent_ids = (
            await resolver_with_availability._resolve_single_assigned_agent(
                partner_id=12,
                service_board_id=70,
                agent_id=33,
                reassign_inactive_agent=True,
                customer_number="+919999999999",
            )
        )

        assert agent_ids[0]["agent_id"] == 34
        assert target.type == "agent"
        assert target.data == ["ext456"]
        # Agent details should have been fetched for the *new* agent, not
        # the original inactive one.
        mock_maglo_client.get_agent_details.assert_awaited_once_with(
            agent_id=34, service_board_id=70
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        mock_maglo_client.reassign_lead_by_phone.assert_awaited_once_with(
            phone_number="+919999999999",
            partner_id=12,
            service_board_id=70,
            agent_id=34,
        )

    @pytest.mark.asyncio
    async def test_flag_on_inactive_agent_no_peer_keeps_original(
        self,
        resolver_with_availability,
        mock_maglo_client,
        mock_user_service_client,
        mock_agent_mapping_repo,
    ):
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"}
        ]
        mock_user_service_client.get_users_availability_status.return_value = {
            33: "On Break"
        }
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "number": "+919876543210",
            "extension": None,
            "internet_calling_enable": False,
        }

        target, agent_ids = (
            await resolver_with_availability._resolve_single_assigned_agent(
                partner_id=12,
                service_board_id=70,
                agent_id=33,
                reassign_inactive_agent=True,
                customer_number="+919999999999",
            )
        )

        assert agent_ids[0]["agent_id"] == 33
        mock_maglo_client.reassign_lead_by_phone.assert_not_awaited()


class TestResolveForSingleAgentReassignment:
    """Tests for the reassign_inactive_agent branch of resolve_for_single_agent
    (the existing-CDR path)"""

    @pytest.mark.asyncio
    async def test_flag_off_never_checks_availability(
        self, resolver_with_availability, mock_maglo_client, mock_user_service_client
    ):
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "number": "+919876543210",
            "extension": None,
            "internet_calling_enable": False,
        }

        result = await resolver_with_availability.resolve_for_single_agent(
            partner_id=12,
            service_board_id=70,
            agent_id=33,
            fallback_agent_number="+919876543210",
            reassign_inactive_agent=False,
        )

        assert result.data == ["+919876543210"]
        assert result.resolved_agent_id is None
        mock_user_service_client.get_users_availability_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_flag_on_active_agent_not_reassigned(
        self,
        resolver_with_availability,
        mock_maglo_client,
        mock_user_service_client,
        mock_agent_mapping_repo,
    ):
        mock_user_service_client.get_users_availability_status.return_value = {
            33: "Active"
        }
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "number": "+919876543210",
            "extension": None,
            "internet_calling_enable": False,
        }

        result = await resolver_with_availability.resolve_for_single_agent(
            partner_id=12,
            service_board_id=70,
            agent_id=33,
            fallback_agent_number="+919876543210",
            reassign_inactive_agent=True,
            customer_number="+919999999999",
        )

        assert result.data == ["+919876543210"]
        assert result.resolved_agent_id is None
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_flag_on_inactive_agent_reassigned_to_peer(
        self,
        resolver_with_availability,
        mock_maglo_client,
        mock_user_service_client,
        mock_agent_mapping_repo,
    ):
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]

        # First availability lookup is the single-agent _is_agent_inactive
        # check (agent 33, "On Break" → inactive); second is the board-wide
        # filter inside _reassign_to_active_agent (agent 34 is Active).
        mock_user_service_client.get_users_availability_status.side_effect = [
            {33: "On Break"},
            {34: "Active"},
        ]
        mock_maglo_client.get_agent_details.return_value = {
            "id": 34,
            "number": "+919876543211",
            "extension": None,
            "internet_calling_enable": False,
        }
        mock_maglo_client.reassign_lead_by_phone.return_value = {
            "lead_request_id": 179245,
            "lead_name": "Saurav Singh",
            "assigned_to": 34,
            "phone_number": "+919999999999",
        }

        result = await resolver_with_availability.resolve_for_single_agent(
            partner_id=12,
            service_board_id=70,
            agent_id=33,
            # Stale fallback number belonging to the original (now inactive)
            # agent 33 — must NOT be used once reassignment happens.
            fallback_agent_number="+919876543210",
            reassign_inactive_agent=True,
            customer_number="+919999999999",
        )

        assert result.type == "number"
        assert result.data == ["+919876543211"]
        assert result.resolved_agent_id == 34
        # Maglo's confirmed lead_request_id must flow back onto the target so
        # the caller can prioritize it over whatever the old CDR had on record.
        assert result.reassigned_lead_id == 179245
        # Agent details should have been fetched for the *new* agent, not
        # the original inactive one.
        mock_maglo_client.get_agent_details.assert_awaited_once_with(
            agent_id=34, service_board_id=70
        )
        mock_maglo_client.reassign_lead_by_phone.assert_awaited_once_with(
            phone_number="+919999999999",
            partner_id=12,
            service_board_id=70,
            agent_id=34,
        )

    @pytest.mark.asyncio
    async def test_flag_on_inactive_agent_no_peer_keeps_original(
        self,
        resolver_with_availability,
        mock_maglo_client,
        mock_user_service_client,
        mock_agent_mapping_repo,
    ):
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"}
        ]
        mock_user_service_client.get_users_availability_status.return_value = {
            33: "On Break"
        }
        mock_maglo_client.get_agent_details.return_value = {
            "id": 33,
            "number": "+919876543210",
            "extension": None,
            "internet_calling_enable": False,
        }

        result = await resolver_with_availability.resolve_for_single_agent(
            partner_id=12,
            service_board_id=70,
            agent_id=33,
            fallback_agent_number="+919876543210",
            reassign_inactive_agent=True,
            customer_number="+919999999999",
        )

        assert result.data == ["+919876543210"]
        assert result.resolved_agent_id is None
        mock_maglo_client.reassign_lead_by_phone.assert_not_awaited()


class TestResolveInboundNoCdrReassignment:
    """End-to-end reassignment through resolve_inbound_no_cdr"""

    @pytest.mark.asyncio
    async def test_result_reflects_reassigned_agent(
        self,
        resolver_with_availability,
        mock_maglo_client,
        mock_user_service_client,
        mock_agent_mapping_repo,
    ):
        mock_maglo_client.upsert_ivr_lead.return_value = {
            "id": 100,
            "name": "Test Lead",
            "lead_request_id": 100,
            "assigned_to": 33,
        }
        mock_agent_mapping_repo.get_agents_by_service_board_id_and_partner_id.return_value = [
            {"agent_id": 33, "agent_number": "+919876543210"},
            {"agent_id": 34, "agent_number": "+919876543211"},
        ]
        mock_user_service_client.get_users_availability_status.side_effect = [
            {33: "On Break"},
            {34: "Active"},
        ]
        mock_maglo_client.get_agent_details.return_value = {
            "id": 34,
            "number": "+919876543211",
            "extension": "ext456",
            "internet_calling_enable": True,
        }

        result = await resolver_with_availability.resolve_inbound_no_cdr(
            customer_number="+919999999999",
            call_to_number="+918888888888",
            partner_id=12,
            service_board_id=70,
            create_lead=True,
            reassign_inactive_agent=True,
        )

        # agent_id in the result (used for CDR + websocket event metadata)
        # must be the new agent, not the stale Maglo-assigned owner.
        assert result["agent_id"] == 34
        assert result["agent_ids"][0]["agent_id"] == 34
        assert result["target"].data == ["ext456"]


class TestDialplanResponseBuilder:
    """Tests for DialplanResponseBuilder"""

    def test_build_transfer_response_agent_type(self):
        """Test building transfer response for agent type"""
        target = TransferTarget(
            type="agent",
            data=["ext123"],
            ring_type="simultaneous",
            skip_active=False,
        )

        response = DialplanResponseBuilder.build_transfer_response(target)

        assert len(response) == 1
        assert "transfer" in response[0]
        assert response[0]["transfer"]["type"] == "agent"
        assert response[0]["transfer"]["data"] == ["ext123"]
        assert response[0]["transfer"]["ring_type"] == "simultaneous"
        assert response[0]["transfer"]["skip_active"] is False

    def test_build_transfer_response_number_type(self):
        """Test building transfer response for number type"""
        target = TransferTarget(
            type="number",
            data=["+919876543210"],
            ring_type="order_by",
            skip_active=True,
        )

        response = DialplanResponseBuilder.build_transfer_response(target)

        assert response[0]["transfer"]["type"] == "number"
        assert response[0]["transfer"]["data"] == ["+919876543210"]
        assert response[0]["transfer"]["ring_type"] == "order_by"
        assert response[0]["transfer"]["skip_active"] is True

    def test_build_transfer_response_empty_data(self):
        """Test building transfer response with empty data"""
        target = TransferTarget(type="number", data=[])

        response = DialplanResponseBuilder.build_transfer_response(target)

        assert response[0]["transfer"]["data"] == []

    def test_build_transfer_response_none_target(self):
        """Test building transfer response when target is None"""
        response = DialplanResponseBuilder.build_transfer_response(None)

        assert len(response) == 1
        assert response[0]["transfer"]["type"] == "number"
        assert response[0]["transfer"]["data"] == []

    def test_build_empty_response(self):
        """Test building empty response"""
        response = DialplanResponseBuilder.build_empty_response()

        assert len(response) == 1
        assert "transfer" in response[0]
        assert response[0]["transfer"]["type"] == "number"
        assert response[0]["transfer"]["data"] == []
        assert response[0]["transfer"]["ring_type"] == "simultaneous"
        assert response[0]["transfer"]["skip_active"] is False

    def test_build_transfer_response_multiple_data_items(self):
        """Test building transfer response with multiple data items"""
        target = TransferTarget(
            type="agent",
            data=["ext123", "ext456", "ext789"],
            ring_type="order_by",
        )

        response = DialplanResponseBuilder.build_transfer_response(target)

        assert len(response[0]["transfer"]["data"]) == 3
        assert "ext123" in response[0]["transfer"]["data"]
        assert "ext456" in response[0]["transfer"]["data"]
        assert "ext789" in response[0]["transfer"]["data"]

    def test_build_transfer_response_none_data(self):
        """Test building transfer response when data is None"""
        target = TransferTarget(type="number", data=None)

        response = DialplanResponseBuilder.build_transfer_response(target)

        assert response[0]["transfer"]["data"] == []

    @pytest.mark.asyncio
    async def test_get_cloud_phonic_info_with_nested_data_key(
        self, resolver, mock_maglo_client
    ):
        """Test cloud phonic info retrieval when response has nested 'data' key"""
        # Response with nested 'data' key
        mock_maglo_client.get_agent_details.return_value = {
            "data": {
                "id": 33,
                "name": "Test Agent",
                "number": "+919876543210",
                "extension": "ext123",
                "internet_calling_enable": True,
            }
        }

        (
            is_cloud,
            extension,
            agent_id,
            agent_name,
            agent_number,
        ) = await resolver._get_cloud_phonic_info(
            partner_id=12, service_board_id=70, agent_id=33
        )

        assert is_cloud is True
        assert extension == "ext123"
        assert agent_id == 33
        assert agent_name == "Test Agent"
        assert agent_number == "+919876543210"

    @pytest.mark.asyncio
    async def test_get_cloud_phonic_info_with_empty_nested_data(
        self, resolver, mock_maglo_client
    ):
        """Test cloud phonic info when nested 'data' is None or empty"""
        # Response with None nested 'data'
        mock_maglo_client.get_agent_details.return_value = {"data": None}

        (
            is_cloud,
            extension,
            agent_id,
            agent_name,
            agent_number,
        ) = await resolver._get_cloud_phonic_info(
            partner_id=12, service_board_id=70, agent_id=33
        )

        assert is_cloud is False
        assert extension is None
        assert agent_id is None
        assert agent_name is None
        assert agent_number is None

    @pytest.mark.asyncio
    async def test_get_cloud_phonic_info_with_non_dict_response(
        self, resolver, mock_maglo_client
    ):
        """Test cloud phonic info when response is not a dict"""
        # Response is not a dict (e.g., list or string)
        mock_maglo_client.get_agent_details.return_value = "Invalid response"

        (
            is_cloud,
            extension,
            agent_id,
            agent_name,
            agent_number,
        ) = await resolver._get_cloud_phonic_info(
            partner_id=12, service_board_id=70, agent_id=33
        )

        assert is_cloud is False
        assert extension is None
        assert agent_id is None
        assert agent_name is None
        assert agent_number is None

    @pytest.mark.asyncio
    async def test_get_cloud_phonic_info_404_error_different_message(
        self, resolver, mock_maglo_client, mock_logger
    ):
        """Test cloud phonic info with 404 error but different message (not service board)"""
        # ValueError with 404 but different message
        mock_maglo_client.get_agent_details.side_effect = ValueError(
            "Maglo error 404: Agent not found"
        )

        result = await resolver._get_cloud_phonic_info(
            partner_id=12, service_board_id=70, agent_id=33
        )

        assert result == (False, None, None, None, None)
        # Should call logger.error instead of logger.warning
        mock_logger.error.assert_called()
        # Verify the error message
        error_call = mock_logger.error.call_args[0][0]
        assert "Maglo API error for agent" in error_call

    @pytest.mark.asyncio
    async def test_get_cloud_phonic_info_value_error_without_404(
        self, resolver, mock_maglo_client, mock_logger
    ):
        """Test cloud phonic info with ValueError that doesn't contain '404'"""
        # ValueError without 404
        mock_maglo_client.get_agent_details.side_effect = ValueError(
            "Some other Maglo error"
        )

        result = await resolver._get_cloud_phonic_info(
            partner_id=12, service_board_id=70, agent_id=33
        )

        assert result == (False, None, None, None, None)
        # Should call logger.error
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args[0][0]
        assert "Maglo API error for agent 33" in error_call
