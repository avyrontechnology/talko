from datetime import datetime, timezone
from typing import Optional
from src.components.call_record.models import CallRecordModel
from src.components.call_record.dto import Contract
from src.components.call_record.repositories import CallRecordRepository
from src.loggers.holler_service_logger import HollerServiceLogger


class CallRecordService:

    def __init__(
        self, call_record_repo: CallRecordRepository, logger: HollerServiceLogger
    ):
        self.__call_record_repo = call_record_repo
        self.__logger = logger

    async def create_call_record(
        self, data: Contract.CreateCallRecordReq, partner_id: int, user_id: int
    ) -> Contract.CreateCallRecordResp:
        try:
            self.__logger.info("Started adding call recod: {}".format(data))
            call_record = CallRecordModel(
                caller=data.caller,
                receiver=data.receiver,
                duration=data.duration,
                timestamp=data.timestamp,
                partner_id=partner_id,
                created_by=user_id,
                created_at=datetime.now(timezone.utc),
            ).model_dump(mode="json")
            record_id = await self.__call_record_repo.add_call_record(call_record)
            self.__logger.info("Call record added by : {}".format(user_id))
            return Contract.CreateCallRecordResp(
                record_id=record_id, message="Call record created successfully"
            )
        except Exception as e:
            self.__logger.error(f"Error creating call record: {e}")
            raise e

    async def get_call_record(
        self, record_id: str, partner_id: int
    ) -> Optional[CallRecordModel]:
        try:
            self.__logger.info(
                "Fetching call record for record_id: {}".format(record_id)
            )
            data = await self.__call_record_repo.get_call_record(record_id, partner_id)
            self.__logger.info(
                "Fetched call record for record_id: {}".format(record_id)
            )
            return data
        except Exception as e:
            self.__logger.error(f"Error fetching call record: {e}")
            raise e

    async def get_all_call_records(self, partner_id: int) -> list[CallRecordModel]:
        try:
            self.__logger.info(
                "Getting all call record of partner_id: {}".format(partner_id)
            )
            records = await self.__call_record_repo.get_all_call_records(partner_id)
            self.__logger.info(
                "Fetched all call record of partner: {}".format(partner_id)
            )
            return records
        except Exception as e:
            self.__logger.error(f"Error retrieving all call records: {e}")
            raise e

    async def update_call_record(
        self, record_id: str, partner_id: int, data: Contract.UpdateCallRecordReq
    ) -> Contract.UpdateCallRecordResp:
        try:
            self.__logger.info(
                "Updatind call record of record_id: {}".format(record_id)
            )
            if not await self.__call_record_repo.is_call_record_exist(
                record_id, partner_id
            ):
                self.__logger.error(
                    "Call record does not exist with id: {}".format(record_id)
                )
                raise ValueError("Call record does not exist")
            update_data = data.model_dump(exclude_unset=True)
            await self.__call_record_repo.update_call_record(
                record_id, partner_id, update_data
            )
            self.__logger.info("Call record updated of record_id: {}".format(record_id))
            return Contract.UpdateCallRecordResp(
                record_id=record_id, message="Call record updated successfully"
            )
        except Exception as e:
            self.__logger.error(f"Error updating call record: {e}")
            raise e

    async def delete_call_record(self, record_id: str, partner_id: int):
        try:
            self.__logger.info(
                "Deleting call record of record_id: {}".format(record_id)
            )
            if not await self.__call_record_repo.is_call_record_exist(
                record_id, partner_id
            ):
                self.__logger.error(
                    "Call record does not exist with id: {}".format(record_id)
                )
                raise ValueError("Call record does not exist")
            await self.__call_record_repo.delete_call_record(record_id, partner_id)
            self.__logger.info("Call record deleted of record_id: {}".format(record_id))
        except Exception as e:
            self.__logger.error(f"Error deleting call record: {e}")
            raise e
