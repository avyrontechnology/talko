"""Console wallet debit for unified billing.

Talko prices locally (rate cards stay here); money moves in console-core.
Idempotent on call_id — retries never double-charge.
"""
import grpc
from grpc.aio import AioRpcError

from src.grpc_client.console_ids import console_id_str
from src.grpc_client.grpc_client import TalkoGRPCClient
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.pub import partner_wallet_pb2, partner_wallet_pb2_grpc

logger = TalkoServiceLogger.get_logger()


class TalkoWalletServiceClient(TalkoGRPCClient):
    def __init__(self, server_address: str = ""):
        super().__init__(server_address=server_address)
        self.stub = partner_wallet_pb2_grpc.WalletRPCServiceStub(self.channel)

    @TalkoGRPCClient.call_with_retry
    async def wallet_debit(
        self,
        partner_id,
        amount: float,
        currency: str,
        call_id: str,
        billed_minutes: float,
        description: str = "",
    ) -> dict | None:
        """Debit via console. Returns ledger-shaped dict (talkо contract)."""
        request = partner_wallet_pb2.WalletDebitRequest(
            partner_id=console_id_str(partner_id),
            amount=float(amount),
            currency=currency or "INR",
            call_id=str(call_id),
            billed_minutes=float(billed_minutes or 0),
            description=description or "",
        )
        logger.info(
            f"Sending WalletDebit call_id={call_id} amount={amount} partner={partner_id}"
        )
        try:
            response = await self.stub.WalletDebit(request)
            logger.info(
                f"WalletDebit ok call_id={call_id} balance={response.remaining_balance}"
            )
            return {
                "transaction_id": response.transaction_id,
                "amount": response.amount,
                "remaining_balance": response.remaining_balance,
                "already_charged": response.already_charged,
            }
        except AioRpcError as exc:
            logger.error(f"Error during WalletDebit call_id={call_id}: {exc}")
            if exc.code() in (
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.FAILED_PRECONDITION,
            ):
                return None
            raise
