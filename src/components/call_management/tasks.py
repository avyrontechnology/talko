import asyncio

from celery import shared_task

from src.core.container import Container
from src.loggers.holler_celery_loggers import CeleryLogger
from src.utils.datetime_util import DateTimeUtil

MISSED_CALLBACK_SWEEP_AGE_SECONDS = 120
# ... and this recent, so permanently un-callbackable rows (AI DID,
# disabled partner, ...) age out instead of being re-dispatched forever.
MISSED_CALLBACK_SWEEP_WINDOW_SECONDS = 2700
# Dispatch cap per sweeper run. Dispatching is cheap (one apply_async per
# candidate); worker concurrency is the real throttle, so keep this well
# above the biggest expected burst (200+ simultaneous misses) to avoid
# multi-minute dispatch stagger. Every dispatch is idempotent downstream
# (already-handled / exec-lock guards), so overshoot is harmless.
MISSED_CALLBACK_SWEEP_LIMIT = 500
# Deterministic task id per missed call — the sweeper, manual re-dispatches
# and debugging all converge on one id, so any dispatch is traceable via
# AsyncResult(task_id).status.
MISSED_CALLBACK_TASK_ID_PREFIX = "missed-cb-"


def missed_callback_task_id(call_uuid: str) -> str:
    return "{}{}".format(MISSED_CALLBACK_TASK_ID_PREFIX, call_uuid)


@shared_task(bind=True, max_retries=0, soft_time_limit=60, time_limit=90)
def missed_call_callback_task(self, call_uuid: str) -> str:
    """
    Places one outbound auto-callback for a missed inbound call. Dispatched
    (immediately, no countdown) by missed_callback_sweeper_task ~2-3 min
    after the miss — see CallService.initiate_missed_call_callback for the
    full decision chain (partner opt-in, already-connected check,
    active-agent resolution, placing the callback).
    """
    logger = CeleryLogger.get_logger()
    task_id = getattr(getattr(self, "request", None), "id", None)
    logger.info(
        "Missed-call callback task starting for call_uuid={} task_id={}".format(
            call_uuid, task_id
        )
    )

    try:

        async def _run() -> str:
            # Resolved inside the running loop (not before asyncio.run()
            # starts) — call_service's dependency chain pulls in the
            # redis_pool Resource, whose async initializer needs a running
            # event loop to await; resolving it synchronously beforehand
            # raised "There is no current event loop in thread 'MainThread'".
            #
            # init_resources() is required too — a Resource provider (like
            # redis_pool) only actually runs its async initializer once this
            # is awaited. The web app only does this once at startup (see
            # src/main.py) since its Container lives for the process
            # lifetime; a Celery task builds a fresh Container per
            # invocation, so it has to redo this every time — and tear the
            # resource down after, since nothing else will.
            #
            # Once any provider's dependency graph includes an async
            # Resource, dependency_injector puts that provider itself into
            # "async mode": call_service() no longer returns a CallService
            # synchronously, it returns an awaitable that must itself be
            # awaited to get the real object — same as redis_pool() does.
            # Calling it synchronously (call_service(), no await) silently
            # returned the bare unawaited Future instead, which is what
            # "'_asyncio.Future' object has no attribute
            # 'initiate_missed_call_callback'" actually was.
            #
            # reset_singletons() is defensive, not strictly required for
            # this bug — dependency_injector caches Singleton/Resource
            # instances at the class level, shared across every Container()
            # instantiation within one process. A Celery prefork worker
            # handles many task invocations over its lifetime, each with
            # its own asyncio.run() loop, so resetting avoids a later task
            # inheriting a Resource bound to an earlier task's now-closed
            # loop.
            container = Container()
            container.reset_singletons()
            await container.init_resources()
            try:
                call_repository = container.call_repository()
                call_redis_helper = container.call_redis_helper()
                call_service = await container.call_service()

                return await _do_callback(
                    call_repository, call_redis_helper, call_service
                )
            finally:
                await container.shutdown_resources()

        async def _do_callback(
            call_repository, call_redis_helper, call_service
        ) -> str:
            cdr = await call_repository.get_cdr_by_call_id_or_uuid(None, call_uuid)
            if not cdr:
                logger.warning(
                    "Missed-call callback: no CDR found for call_uuid={}".format(
                        call_uuid
                    )
                )
                return "cdr_not_found"

            # Re-check current state — a manual callback, or a later webhook
            # delivery, may have already resolved this since it was scheduled.
            if cdr.get("call_status") != "missed" or cdr.get("action") != "inbound":
                logger.info(
                    "Missed-call callback: call_uuid={} no longer missed/inbound "
                    "(call_status={}, action={}) — skipping".format(
                        call_uuid, cdr.get("call_status"), cdr.get("action")
                    )
                )
                return "no_longer_applicable"

            # Exactly-once guards: the ETA task, the beat sweeper, and manual
            # re-dispatches can all reach this point for the same call_uuid.
            # A finished winner leaves a callback CDR (locks expire, rows
            # don't); a concurrently-running winner holds the exec lock.
            if await call_repository.find_callback_by_parent_uuid(call_uuid):
                logger.info(
                    "Missed-call callback: call_uuid={} already has a callback "
                    "— skipping".format(call_uuid)
                )
                return "already_handled"

            if not await call_redis_helper.try_acquire_missed_callback_exec_lock(
                call_uuid
            ):
                logger.info(
                    "Missed-call callback: call_uuid={} execution already in "
                    "flight — skipping".format(call_uuid)
                )
                return "duplicate_suppressed"

            await call_service.initiate_missed_call_callback(cdr)
            return "processed"

        result = asyncio.run(_run())
        logger.info(
            "Missed-call callback task finished for call_uuid={} task_id={}: {}".format(
                call_uuid, task_id, result
            )
        )
        return result

    except Exception as e:
        logger.error(
            "Missed-call callback task failed for call_uuid={} task_id={}: {}".format(
                call_uuid, task_id, str(e)
            )
        )
        return "error"


@shared_task(bind=True, max_retries=0, soft_time_limit=120, time_limit=150)
def missed_callback_sweeper_task(self) -> str:
    """
    Normal (and only) scheduler for missed-call auto-callbacks, run by beat
    every minute.

    Replaces the old direct apply_async(countdown=100) fast path, which was
    removed because countdown tasks are held in the publishing worker's
    in-memory timer and were repeatedly lost on QA (published fine, never
    even "received" — idle worker, no restart), while immediate dispatches
    always land. This task re-derives "who still needs a callback" from
    durable Mongo state on every run, so a dropped, late, or
    deploy-interrupted run is healed by the next one instead of losing the
    callback silently.

    Double-dial is impossible by construction: dispatches reuse the
    deterministic task id and every execution hits the already-handled /
    exec-lock guards in _do_callback above, so at most one execution per
    call_uuid ever places a call.
    """
    logger = CeleryLogger.get_logger()
    logger.info("Missed-call callback sweeper starting")

    try:

        async def _run() -> str:
            container = Container()
            container.reset_singletons()
            await container.init_resources()
            try:
                call_repository = container.call_repository()
                now_ms = DateTimeUtil.get_current_time()
                candidates = (
                    await call_repository.find_missed_inbounds_needing_callback(
                        older_than_ms=now_ms
                        - MISSED_CALLBACK_SWEEP_AGE_SECONDS * 1000,
                        newer_than_ms=now_ms
                        - MISSED_CALLBACK_SWEEP_WINDOW_SECONDS * 1000,
                        limit=MISSED_CALLBACK_SWEEP_LIMIT,
                    )
                )
                redis_helper = container.call_redis_helper()
                dispatched = 0
                skipped = 0
                for candidate in candidates:
                    candidate_uuid = candidate.get("call_uuid")
                    if not candidate_uuid:
                        skipped += 1
                        continue
                    # Skip anything already healed (callback placed) or
                    # currently being handled (ETA task in flight / running).
                    if await call_repository.find_callback_by_parent_uuid(
                        candidate_uuid
                    ):
                        skipped += 1
                        continue
                    if await redis_helper.is_missed_callback_exec_locked(
                        candidate_uuid
                    ):
                        skipped += 1
                        continue
                    missed_call_callback_task.apply_async(
                        args=[candidate_uuid],
                        task_id=missed_callback_task_id(candidate_uuid),
                    )
                    logger.info(
                        "Missed-call callback sweeper re-dispatched "
                        "call_uuid={}".format(candidate_uuid)
                    )
                    dispatched += 1
                return "swept:dispatched={}:skipped={}:candidates={}".format(
                    dispatched, skipped, len(candidates)
                )
            finally:
                await container.shutdown_resources()

        result = asyncio.run(_run())
        logger.info("Missed-call callback sweeper finished: {}".format(result))
        return result

    except Exception as e:
        logger.error("Missed-call callback sweeper failed: {}".format(str(e)))
        return "error"
