from celery import Celery
from celery.schedules import crontab

from src.loggers.talko_celery_loggers import TalkoCeleryLogger

celery_logger = TalkoCeleryLogger.get_logger()


def create_celery(
    app_name: str,
    broker_url: str,
    backend_url: str = None,
    task_modules: list = None,
    config_module: str = None,
) -> Celery:
    try:
        celery_logger.info(
            "Creating Celery app '{}' with broker='{}' and backend='{}'".format(
                app_name, broker_url, backend_url
            )
        )

        celery = Celery(app_name, broker=broker_url, backend=backend_url)
        celery.conf.update(
            task_track_started=True,
            worker_concurrency=10,
            task_always_eager=False,
            task_time_limit=1200,  # 20 minutes
        )

        celery.conf.beat_schedule = {
            "check_incomplete_cdrs_every_5_minutes": {
                "task": "src.components.call_operation.tasks.check_incomplete_cdrs",
                "schedule": crontab(minute="*/5"),  # runs every 5 minutes
                "args": ["tata_tele"],
            },
            "check_and_save_unsaved_recordings_every_3_minutes": {
                "task": "src.components.call_assets.tasks.check_and_save_unsaved_recordings",
                "schedule": crontab(minute="*/3"),  # runs every 3 minutes
                "args":[],
            },
            "did_cooldown_expiry_daily": {
                "task": "src.components.did_management.tasks.process_expired_did_cooldowns",
                "schedule": crontab(hour=3, minute=0),  # every day at 03:00
                "args": [],  # no arguments needed
            },
            "missed_callback_sweeper_every_minute": {
                "task": "src.components.call_management.tasks.missed_callback_sweeper_task",
                "schedule": crontab(minute="*"),
                "args": [],
            },
        }

        if config_module:
            celery.config_from_object(config_module)
            celery_logger.info(f"Loaded Celery config from module: {config_module}")

        if task_modules:
            celery.autodiscover_tasks(task_modules)
            celery_logger.info(f"Autodiscovered tasks from modules: {task_modules}")

        celery_logger.info(f"Celery app '{app_name}' created successfully")
        return celery

    except Exception as e:
        celery_logger.exception(f"Failed to create Celery app '{app_name}': {e}")
        raise
