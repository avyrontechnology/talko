"""Partner client tests: talko -> fake console-core AuthService (in-process).

Fake servicer implements the 3 partner reads with console-core field
numbers; client parses them. Repo convention: @pytest.mark.asyncio.
"""

import grpc
import pytest
import pytest_asyncio

from src.grpc_client.client_services.partner_service_client import (
    TalkoPartnerServiceClient,
)
from src.pub import auth_pb2
from src.pub.auth_pb2_grpc import (
    AuthServiceServicer,
    add_AuthServiceServicer_to_server,
)


class FakePartnerAuth(AuthServiceServicer):
    async def GetPartnerDetails(self, request, context):
        if request.partner_id == "missing":
            await context.abort(grpc.StatusCode.NOT_FOUND, "no such partner")
        return auth_pb2.GetPartnerDetailsResponse(
            message="Success",
            partner_detail=auth_pb2.PartnerDetail(
                partner_id=request.partner_id,
                name="Acme",
                is_active=True,
                partner_status="ACTIVE",
                active_license=10,
            ),
        )

    async def GetPartnerMetaDataDetails(self, request, context):
        return auth_pb2.GetPartnerMetaDataDetailsResponse(
            is_talko_enabled=True,
            type_of_business="SMB",
            subscription_mode="self_served",
        )

    async def GetPartnerServicesDetails(self, request, context):
        return auth_pb2.GetPartnerServiceDetailsResponse(
            is_talko_service_enabled=True,
            is_gsm_calling_enabled=False,
            is_meeting_log_enabled=True,
            enable_dialer=True,
        )


@pytest_asyncio.fixture
async def partner_client():
    server = grpc.aio.server()
    add_AuthServiceServicer_to_server(FakePartnerAuth(), server)
    port = server.add_insecure_port("localhost:0")
    await server.start()
    client = TalkoPartnerServiceClient(server_address=f"localhost:{port}")
    yield client
    await client.close_channel()
    await server.stop(None)


@pytest.mark.asyncio
async def test_get_partner_details(partner_client):
    res = await partner_client.get_partner_details(101)
    assert res["partner_id"] == "101"
    assert res["is_active"] is True
    assert res["partner_status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_get_partner_details_missing_returns_none(partner_client):
    assert await partner_client.get_partner_details("missing") is None


@pytest.mark.asyncio
async def test_get_partner_meta_data(partner_client):
    res = await partner_client.get_partner_meta_data(101)
    assert res["is_talko_enabled"] is True
    assert res["subscription_mode"] == "self_served"


@pytest.mark.asyncio
async def test_get_partner_services(partner_client):
    res = await partner_client.get_partner_services(101)
    assert res["enable_dialer"] is True
    assert res["is_gsm_calling_enabled"] is False


@pytest.mark.asyncio
async def test_is_partner_live_true(partner_client):
    assert await partner_client.is_partner_live(101) is True


@pytest.mark.asyncio
async def test_is_partner_live_missing_false(partner_client):
    assert await partner_client.is_partner_live("missing") is False
