from celery import shared_task
from celery.schedules import crontab

from .celery_app import celery


# A simple task
@celery.task
def add_numbers(x: int, y: int) -> int:
    result = x + y
    return result


# poetry add redbeat
# A periodic task

# @shared_task
# def my_periodic_task():
#     print("Periodic Task Executed")

# celery.conf.beat_schedule = {
#     "run_periodic_task_example": {
#         "task": "src.maglo_celery.tasks.my_periodic_task",
#         "schedule": crontab(minute="*/1"),  # Every 1 minute
#     },
# }
