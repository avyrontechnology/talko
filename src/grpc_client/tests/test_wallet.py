"""Wallet client tests: talko -> fake console-core wallet (in-process)."""

import grpc
import pytest
import pytest_asyncio

from src.grpc_client.client_services.wallet_service_client import (
    TalkoWalletServiceClient,
)
from src.pub import partner_wallet_pb2
from src.pub.partner_wallet_pb2_grpc import (
    WalletRPCServiceServicer,
    add_WalletRPCServiceServicer_to_server,
)


class FakeWallet(WalletRPCServiceServicer):
    async def WalletDebit(self, request, context):
        if request.partner_id == "missing":
            await context.abort(grpc.StatusCode.NOT_FOUND, "no wallet")
        if request.amount > 1000:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "insufficient")
        return partner_wallet_pb2.WalletDebitResponse(
            message="Success",
            transaction_id="tx-1",
            amount=request.amount,
            remaining_balance=100.0 - request.amount,
            already_charged=False,
        )


@pytest_asyncio.fixture
async def wallet_client():
    server = grpc.aio.server()
    add_WalletRPCServiceServicer_to_server(FakeWallet(), server)
    port = server.add_insecure_port("localhost:0")
    await server.start()
    client = TalkoWalletServiceClient(server_address=f"localhost:{port}")
    yield client
    await client.close_channel()
    await server.stop(None)


@pytest.mark.asyncio
async def test_wallet_debit_success(wallet_client):
    res = await wallet_client.wallet_debit(
        partner_id=101, amount=5.0, currency="INR", call_id="C1", billed_minutes=2.0
    )
    assert res["transaction_id"] == "tx-1"
    assert res["remaining_balance"] == 95.0
    assert res["already_charged"] is False


@pytest.mark.asyncio
async def test_wallet_debit_not_found_returns_none(wallet_client):
    assert (
        await wallet_client.wallet_debit(
            partner_id="missing",
            amount=5.0,
            currency="INR",
            call_id="C2",
            billed_minutes=1.0,
        )
        is None
    )


@pytest.mark.asyncio
async def test_wallet_debit_insufficient_returns_none(wallet_client):
    assert (
        await wallet_client.wallet_debit(
            partner_id=101,
            amount=5000.0,
            currency="INR",
            call_id="C3",
            billed_minutes=1.0,
        )
        is None
    )
