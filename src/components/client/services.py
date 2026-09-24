from bson import ObjectId

from src.components.client.dto import TalkoContract
from src.components.client.message import (
    CLIENT_ACTIVATED_SUCCESSFULLY,
    CLIENT_CREATED_SUCCESSFULLY,
    CLIENT_DEACTIVATED_SUCCESSFULLY,
    CLIENT_NAME_EXISTS,
    CLIENT_NOT_FOUND,
    CLIENT_UPDATED_SUCCESSFULLY,
)
from src.components.client.models import TalkoClientModel
from src.components.client.repository import TalkoClientRepository
from src.exceptions import TalkoConflictError, TalkoResourceNotFound
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.datetime_util import TalkoDateTimeUtil


class TalkoClientService:
    def __init__(
        self,
        repository: TalkoClientRepository,
        logger: TalkoServiceLogger,
        datetime_util: TalkoDateTimeUtil,
    ):
        self.__repository = repository
        self.__logger = logger
        self.__datetime_util = datetime_util

    @staticmethod
    def _to_response(doc: dict) -> TalkoContract.ClientResponse:
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return TalkoContract.ClientResponse(**doc)

    async def create_client(self, payload: TalkoContract.ClientCreate) -> TalkoContract.ClientCreateResponse:
        name = payload.name.strip()
        if not name:
            from src.exceptions import TalkoBadRequestError

            raise TalkoBadRequestError("Client name must not be empty")
        existing = await self.__repository.find_by_name(payload.partner_id, name)
        if existing:
            raise TalkoConflictError(CLIENT_NAME_EXISTS.format(name, payload.partner_id))
        record = TalkoClientModel(
            partner_id=payload.partner_id,
            name=name,
            workspace_ids=payload.workspace_ids or [],
            is_active=True,
        ).model_dump()
        client_id = await self.__repository.insert_client(record)
        self.__logger.info(f"Client created id={client_id} partner={payload.partner_id}")
        return TalkoContract.ClientCreateResponse(id=client_id, message=CLIENT_CREATED_SUCCESSFULLY)

    async def list_clients(self, partner_id: int, active_only: bool = False) -> list[TalkoContract.ClientResponse]:
        docs = await self.__repository.find_by_partner(partner_id, active_only)
        return [self._to_response(d) for d in docs]

    async def list_all_clients(self, active_only: bool = False) -> list[TalkoContract.ClientResponse]:
        docs = await self.__repository.find_all(active_only)
        return [self._to_response(d) for d in docs]

    async def get_client(self, client_id: str) -> TalkoContract.ClientResponse:
        doc = await self.__repository.find_by_id(ObjectId(client_id))
        if not doc:
            raise TalkoResourceNotFound(CLIENT_NOT_FOUND.format(client_id))
        return self._to_response(doc)

    async def update_client(
        self, client_id: str, payload: TalkoContract.ClientUpdate
    ) -> TalkoContract.ClientCreateResponse:
        update = {k: v for k, v in payload.model_dump().items() if v is not None}
        if "name" in update:
            update["name"] = update["name"].strip()
            if not update["name"]:
                from src.exceptions import TalkoBadRequestError

                raise TalkoBadRequestError("Client name must not be empty")
        update["updated_at"] = self.__datetime_util.get_current_time()
        doc = await self.__repository.update_client(ObjectId(client_id), update)
        if not doc:
            raise TalkoResourceNotFound(CLIENT_NOT_FOUND.format(client_id))
        return TalkoContract.ClientCreateResponse(id=client_id, message=CLIENT_UPDATED_SUCCESSFULLY)

    async def set_active(self, client_id: str, is_active: bool) -> TalkoContract.ClientCreateResponse:
        doc = await self.__repository.update_client(
            ObjectId(client_id),
            {
                "is_active": is_active,
                "updated_at": self.__datetime_util.get_current_time(),
            },
        )
        if not doc:
            raise TalkoResourceNotFound(CLIENT_NOT_FOUND.format(client_id))
        return TalkoContract.ClientCreateResponse(
            id=client_id,
            message=CLIENT_ACTIVATED_SUCCESSFULLY if is_active else CLIENT_DEACTIVATED_SUCCESSFULLY,
        )
