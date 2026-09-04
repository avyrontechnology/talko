import asyncio

from celery import group, shared_task

from src.components.call_operation.cdr_update import TalkoCDRUpdateTask
from src.core.container import TalkoContainer
from src.loggers.talko_celery_loggers import TalkoCeleryLogger

CHUNK_SIZE = 20  # tune based on average TalkoCDR processing time

# Slightly above process_vendor_config's hard time_limit (360s) so the lock
# always outlives a legitimate run, but still self-expires if a release is
# ever missed (e.g. a hard-killed worker) instead of wedging future runs.
PROCESS_VENDOR_CONFIG_LOCK_TTL = 400


@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=90)
def check_incomplete_cdrs_coordinator(self, vendor_type: str) -> str:
    """
    Coordinator task: fetch ALL vendor configs for the given vendor_type,
    then fan out one worker task per config.

    This task is intentionally short-lived — it only fetches configs and
    dispatches workers. It never processes CDRs directly.

    Args:
        vendor_type: Vendor identifier (e.g., 'tata_tele').

    Returns:
        str: Summary of how many worker tasks were dispatched.
    """
    logger = TalkoCeleryLogger.get_logger()
    logger.info("Coordinator starting for vendor_type: {}".format(vendor_type))

    try:
        container = TalkoContainer()
        vendor_config_repo = container.vendor_config_repo()

        # Fetch ALL configs for this vendor_type — no [0] truncation
        vendor_configs = asyncio.run(
            vendor_config_repo.get_vendor_config_by_vendor_type(vendor_type)
        )

        if not vendor_configs:
            logger.warning(
                "No vendor configs found for vendor_type: {}".format(vendor_type)
            )
            return "No vendor configs found"

        logger.info(
            "Found {} config(s) for vendor_type: {}, dispatching workers".format(
                len(vendor_configs), vendor_type
            )
        )

        # Fan out: one independent worker task per vendor_config
        task_group = group(
            process_vendor_config.s(str(config["_id"]), vendor_type)
            for config in vendor_configs
        )
        task_group.apply_async()

        return "Dispatched {} worker task(s) for vendor_type: {}".format(
            len(vendor_configs), vendor_type
        )

    except Exception as e:
        logger.error(
            "Coordinator failed for vendor_type {}: {}".format(vendor_type, str(e))
        )
        raise self.retry(countdown=300)  # Retry in 5 minutes


@shared_task(bind=True, max_retries=3, soft_time_limit=300, time_limit=360)
def process_vendor_config(self, vendor_config_id: str, vendor_type: str) -> str:
    """
    Worker task: process all incomplete CDRs for ONE vendor_config_id, in chunks.

    Scoped strictly to a single vendor_config_id so that multi-config vendors
    are handled correctly without overlap. CDRs are processed in configurable
    chunks to keep each task short-lived and prevent worker timeout crashes.

    Args:
        vendor_config_id: The specific vendor config document ID to process.
        vendor_type: Vendor identifier (e.g., 'tata_tele'), passed through
                     for handler initialization.

    Returns:
        str: Summary of how many CDRs were updated.
    """
    logger = TalkoCeleryLogger.get_logger()
    lock_key = "talko:process_vendor_config_lock:{}".format(vendor_config_id)

    # Everything below runs inside ONE asyncio.run() call. A prior version
    # made three separate asyncio.run() calls (acquire lock, do the work,
    # release lock) around a module-level cached Redis client — each call
    # spins up its own event loop, but the cached client's internal lock/
    # connections stay bound to whichever loop first touched them. The next
    # asyncio.run() (in this task, or a later task in the same long-lived
    # worker process) then hit that stale binding and crashed with
    # "Event loop is closed" / "Future attached to a different loop"
    # escaping straight into Celery's own task-invocation machinery.
    # Using the DI container's redis_pool Resource — freshly acquired and
    # torn down within this single asyncio.run() call, exactly like
    # missed_call_callback_task already does — avoids the cross-loop reuse
    # entirely instead of trying to patch around it.
    acquired = False

    async def _run() -> str:
        nonlocal acquired
        container = TalkoContainer()
        container.reset_singletons()
        await container.init_resources()
        try:
            redis = await container.redis_pool()
            acquired = bool(
                await redis.set(
                    lock_key, "1", nx=True, ex=PROCESS_VENDOR_CONFIG_LOCK_TTL
                )
            )
            if not acquired:
                logger.info(
                    "Skipping vendor_config_id {} — a previous run is still "
                    "in progress (coordinator fires more often than a run "
                    "can complete)".format(vendor_config_id)
                )
                return "Skipped: already in progress for vendor_config_id {}".format(
                    vendor_config_id
                )

            logger.info(
                "Worker starting for vendor_config_id: {}, vendor_type: {}".format(
                    vendor_config_id, vendor_type
                )
            )

            cdr_update_task: TalkoCDRUpdateTask = container.cdr_update_task()
            result = await cdr_update_task.execute_for_config(
                vendor_config_id=vendor_config_id,
                vendor_type=vendor_type,
                chunk_size=CHUNK_SIZE,
            )

            logger.info(
                "Worker completed for vendor_config_id {}: {}".format(
                    vendor_config_id, result
                )
            )
            return result
        finally:
            if acquired:
                # Best-effort: don't let a release failure mask the
                # retry/return above — the TTL is the real safety net.
                try:
                    redis = await container.redis_pool()
                    await redis.delete(lock_key)
                except Exception as release_exc:
                    logger.warning(
                        "Failed to release lock for vendor_config_id {}: {}".format(
                            vendor_config_id, release_exc
                        )
                    )
            await container.shutdown_resources()

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.error(
            "Worker failed for vendor_config_id {}: {}".format(vendor_config_id, str(e))
        )
        raise self.retry(countdown=120)  # Retry in 2 minutes


# ---------------------------------------------------------------------------
# Kept for backward compatibility — delegates to the coordinator
# ---------------------------------------------------------------------------


@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=90)
def check_incomplete_cdrs(self, vendor_type: str) -> str:
    """
    Legacy entry point. Delegates to the coordinator task.

    Kept so that any existing Celery beat schedules or callers that reference
    this task name continue to work without configuration changes.

    Args:
        vendor_type: Vendor identifier (e.g., 'tata_tele').

    Returns:
        str: Confirmation that the coordinator was dispatched.
    """
    logger = TalkoCeleryLogger.get_logger()
    logger.info(
        "check_incomplete_cdrs (legacy) delegating to coordinator for vendor_type: {}".format(
            vendor_type
        )
    )
    try:
        # Fire-and-forget: calling .get() here would block on a task's own
        # result from within another task, which Celery forbids outright
        # (risk of worker-pool deadlock) — it always raised
        # "Never call result.get() within a task!" and burned through
        # retries, endlessly re-queuing itself.
        check_incomplete_cdrs_coordinator.apply_async(args=[vendor_type])
        return "Coordinator dispatched for vendor_type: {}".format(vendor_type)
    except Exception as e:
        logger.error(
            "Legacy task failed for vendor_type {}: {}".format(vendor_type, str(e))
        )
        raise self.retry(countdown=300)
