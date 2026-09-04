import asyncio

from celery import shared_task

from src.components.call_assets.update_recordings import RecordingsUpdateTask
from src.core.container import Container
from src.loggers.holler_celery_loggers import CeleryLogger


@shared_task(bind=True, max_retries=3, soft_time_limit=150, time_limit=180)
def check_and_save_unsaved_recordings(self):
    """
    Celery task to check and save unsaved call recordings
    Args:
    Returns:
        str: Task completion message.
    """
    logger = CeleryLogger.get_logger()
    logger.info("Starting check_and_save_unsaved_recordings")

    try:
        # Initialize container
        container = Container()
        save_and_update_unsaved_recorings_task: RecordingsUpdateTask = container.save_and_update_unsaved_recorings_task()
        result = asyncio.run(save_and_update_unsaved_recorings_task.process_reocrdings_urls())
        logger.info("Completed check_and_save_unsaved_recordings")
        return result

    except Exception as e:
        logger.error(
            "Error in check_and_save_unsaved_recordings: {}".format(str(e))
        )
        raise self.retry(countdown=600)  # Retry in 10 minutes