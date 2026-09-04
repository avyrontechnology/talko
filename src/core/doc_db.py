import contextlib
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.client_session import ClientSession
from typing import Any, AsyncIterator
from src.loggers.holler_service_logger import HollerServiceLogger
from src.core.environment import ENV


class DocDatabaseSessionManager:
    def __init__(
        self, logger: HollerServiceLogger, engine_kwargs: dict[str, Any] = None
    ):
        if engine_kwargs is None:
            engine_kwargs = {}
        self.__logger: HollerServiceLogger = logger
        self._engine_kwargs = engine_kwargs
        self._db_name = ENV.MONGO_DB
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None

    def _get_connection_string(self):
        if ENV.ENVIRONMENT != "LOCAL":
            self._host = "mongodb+srv://{user}:{password}@{db_host}/admin{tls}&{auth_source}".format(
                user=ENV.MONGO_USER,
                password=ENV.MONGO_PASSWORD,
                db_host=ENV.MONGO_HOST,
                tls="?tls=true",
                auth_source="authSource=admin",
            )
        else:
            self._host = "mongodb://{user}:{password}@{db_host}:{port}".format(
                user=ENV.MONGO_USER,
                password=ENV.MONGO_PASSWORD,
                db_host=ENV.MONGO_HOST,
                port=ENV.MONGO_PORT,
            )

    def _initialize_client(self):
        """Ensures MongoDB client is initialized."""
        if self._client is None:
            self._get_connection_string()
            self.__logger.info("MongoDB database: {}".format(self._db_name))
            self.__logger.info("MongoDB host: {}".format(self._host))
            self._client = AsyncIOMotorClient(self._host, **self._engine_kwargs)
            self._db = self._client[self._db_name]

    async def close(self):
        """Closing MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncIOMotorDatabase]:
        """Creates a MongoDB session with transaction support."""
        self._initialize_client()
        session: ClientSession = await self._client.start_session()

        try:
            async with session.start_transaction():
                yield self._db
        finally:
            await session.end_session()

    @contextlib.asynccontextmanager
    async def collection(self, collection_name: str) -> AsyncIterator:
        """
        Provides a MongoDB collection for a single operation.

        No session/transaction here on purpose — nearly every call site does
        exactly one operation, for which a transaction adds no atomicity
        benefit (single MongoDB writes are already atomic) but does add
        snapshot-isolation risk: a document committed moments earlier by a
        different session isn't guaranteed visible inside a fresh
        transaction's snapshot. That caused real read-your-recent-write
        failures (e.g. a Celery task reading a CDR a webhook had just
        written). Call sites that genuinely need multi-operation atomicity
        (a read-check followed by a conditional write) should use connect()
        directly instead, not this.
        """
        self._initialize_client()
        yield self._db[collection_name]
