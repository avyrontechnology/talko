import asyncio
import os
import base64
from functools import wraps

import grpc

from src.loggers.holler_rpc_logger import HollerRPCLogger
from dotenv import load_dotenv
from .constants import ENV
from src.core.environment import ENV as environment
from src.grpc_interceptor.auth_interceptor import ApiKeyClientInterceptor

logger = HollerRPCLogger.get_logger()

load_dotenv()


class GRPCClient:

    MAX_RETRIES = 3
    RETRY_DELAY = 2

    HOST = environment.CONSOLE_GRPC_HOST
    PORT = environment.CONSOLE_GRPC_PORT

    def __init__(self):
        logger.info("Initializing GRPCClient")
        self.server_address = f"{GRPCClient.HOST}:{GRPCClient.PORT}"
        logger.debug(f"Resolved server address: {self.server_address}")
        self.channel = self.create_channel(self.server_address)

    def create_channel(self, server_address):
        logger.info("Creating gRPC channel to: {}: CA env: {}".format(server_address, environment.CA))
        if environment.CA != "None":
            logger.info(f"Creating a secure gRPC channel to: {server_address}")
            return self._create_secure_channel(server_address)

        logger.info(f"Creating an insecure gRPC channel to: {server_address}")
        return self._create_insecure_channel(server_address)

    def _create_secure_channel(self, server_address):
        logger.debug("Loading CA certificate for secure channel setup")
        ca_cert = environment.CA
        ca_cert = base64.b64decode(ca_cert)
        logger.info("Creating gRPC secure channel to: {}: CA env: {}".format(server_address, ca_cert))
        logger.info("Loading certificates....")

        credentials = grpc.ssl_channel_credentials(root_certificates=ca_cert)
        logger.debug("SSL credentials created successfully")

        auth_interceptor = ApiKeyClientInterceptor(api_key="maglo-key")
        options = (("grpc.ssl_target_name_override", "console-service.makunaiglobal.ai"),)

        logger.info(f"Creating secure gRPC channel with interceptors to {server_address}")
        return grpc.aio.secure_channel(
            server_address,
            credentials,
            interceptors=[auth_interceptor],
            options=options
        )

    def _create_insecure_channel(self, server_address):
        logger.info(f"Creating an insecure gRPC channel to: {server_address}")
        auth_interceptor = ApiKeyClientInterceptor(api_key="maglo-key")
        logger.debug(f"Auth interceptor instantiated: {auth_interceptor}")
        return grpc.aio.insecure_channel(server_address, interceptors=[auth_interceptor])

    async def close_channel(self):
        if self.channel:
            logger.info(f"Closing the gRPC channel: {self.channel}")
            await self.channel.close()
            logger.debug("gRPC channel closed successfully")

    @staticmethod
    def call_with_retry(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(GRPCClient.MAX_RETRIES):
                try:
                    logger.debug(f"Calling {func.__name__} (attempt {attempt + 1})")
                    return await func(*args, **kwargs)
                except grpc.aio.AioRpcError as exc:
                    logger.error(f"gRPC error in {func.__name__}: {exc}")
                    if attempt < GRPCClient.MAX_RETRIES - 1:
                        logger.info(
                            f"Retrying {func.__name__} (attempt {attempt + 2}/{GRPCClient.MAX_RETRIES})"
                        )
                        await asyncio.sleep(GRPCClient.RETRY_DELAY)
                    else:
                        logger.error(
                            f"Failed to execute {func.__name__} after {GRPCClient.MAX_RETRIES} attempts"
                        )
                        return None

        return wrapper
