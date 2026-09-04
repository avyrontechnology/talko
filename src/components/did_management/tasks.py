import asyncio
from typing import Any, Dict

from celery import shared_task
from pymongo.operations import UpdateOne

from src.components.did_management.constants import TalkoDIDStatus
from src.components.did_management.models import TalkoPhoneNumberManagement
from src.core.container import TalkoContainer
from src.loggers.talko_celery_loggers import TalkoCeleryLogger
from src.utils.datetime_util import TalkoDateTimeUtil


@shared_task(bind=True, max_retries=3, soft_time_limit=300, time_limit=360)
def process_expired_did_cooldowns(self) -> str:
    """
    Celery task to transition expired Cooling Period DIDs to Cooldown Completed.

    Runs daily (scheduled via beat_schedule).

    Returns:
        str: Completion message with count of updated DIDs
    """
    logger = TalkoCeleryLogger.get_logger()
    logger.info("Starting DID cooldown expiry task")

    try:
        container = TalkoContainer()
        db = container.db()

        now: int = TalkoDateTimeUtil.get_current_time()
        updated_count: int = 0

        logger.info(
            "Checking for DIDs in Cooling Period that expired before {}".format(now)
        )

        async def run_expiry() -> str:
            nonlocal updated_count

            # Read-then-bulk-write: uses connect()'s transaction, not the
            # plain collection() helper, so the expired-DID selection and
            # the batch status transition stay consistent with each other.
            async with db.connect() as mongo_db:
                collection = mongo_db[
                    TalkoPhoneNumberManagement.CollectionName.PHONE_NUMBER_MANAGEMENT
                ]

                query: Dict[str, Any] = {
                    "status": TalkoDIDStatus.COOLING_PERIOD.value,
                    "cooldown_until": {"$lte": now},
                }

                logger.info("Executing query in cooldowns: {}".format(query))

                cursor = collection.find(query)
                expired_docs = [doc async for doc in cursor]

                logger.info(
                    "Query executed, found {} expired DIDs".format(len(expired_docs))
                )
                logger.debug("Expired DIDs: {}".format(expired_docs))

                if not expired_docs:
                    return "No expired Cooling Period DIDs found"

                logger.info(
                    "Found {} expired Cooling Period DIDs".format(len(expired_docs))
                )

                bulk_ops: list = []
                for doc in expired_docs:
                    bulk_ops.append(
                        UpdateOne(
                            {"_id": doc["_id"]},
                            {
                                "$set": {
                                    "status": TalkoDIDStatus.COOLDOWN_COMPLETED.value,
                                    "cooldown_until": None,
                                    "status_changed_at": now,
                                }
                            },
                            upsert=False,
                        )
                    )

                if bulk_ops:
                    result = await collection.bulk_write(bulk_ops)
                    updated_count = result.modified_count
                    logger.info(
                        "Transitioned {} DIDs to Cooldown Completed".format(
                            updated_count
                        )
                    )

                return "Processed {} DIDs, updated {}".format(
                    len(expired_docs), updated_count
                )

        # Run the async logic
        result_message: str = asyncio.run(run_expiry())

        logger.info("DID cooldown expiry task completed: {}".format(result_message))
        return result_message

    except Exception as exc:
        logger.error("Error in DID cooldown expiry task: {}".format(str(exc)))
        raise self.retry(exc=exc, countdown=300)  # retry after 5 minutes
