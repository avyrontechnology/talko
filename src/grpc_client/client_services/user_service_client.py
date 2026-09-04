from typing import Dict, List, Union

from grpc.aio import AioRpcError

from src.grpc_client.grpc_client import TalkoGRPCClient
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.pub import user_pb2, user_pb2_grpc

logger = TalkoServiceLogger.get_logger()


class TalkoUserServiceClient(TalkoGRPCClient):

    def __init__(self):
        super().__init__()
        self.stub = user_pb2_grpc.UserServiceStub(self.channel)

    @TalkoGRPCClient.call_with_retry
    async def get_users_availability_status(
        self, user_ids: Union[int, List[int]]
    ) -> Dict[int, str]:
        """Fetches current availability status for one or multiple user IDs."""
        user_ids_list = [user_ids] if isinstance(user_ids, int) else user_ids
        logger.info(
            f"Sending GetUsersAvailabilityStatus request for user_ids: {user_ids_list}"
        )

        request = user_pb2.GetUsersAvailabilityStatusRequest(user_ids=user_ids_list)

        try:
            response = await self.stub.GetUsersAvailabilityStatus(request)
            logger.info(
                f"Received availability status for user_ids: {user_ids_list}"
            )

            return {
                status.user_id: status.current_status
                for status in response.users_availability_status
            }
        except AioRpcError as exc:
            logger.error(f"Error during GetUsersAvailabilityStatus call: {exc}")
            return {}
