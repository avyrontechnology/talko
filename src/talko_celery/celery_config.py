"""
task_routes: Routes tasks to specific queues based on their module names (e.g., leads_queue for lead tasks).
task_default_queue: Defines a fallback queue for tasks not matching any route.
task_acks_late: Ensures tasks are acknowledged only after successful execution, improving reliability.
worker_prefetch_multiplier: Controls how many tasks are prefetched by workers at a time (set to 1 for safer, sequential task processing).
result_expires: Specifies how long the task results will be stored in the backend before they expire.
timezone: Sets the timezone for scheduling tasks (typically UTC).
enable_utc: Ensures UTC is used for all time-related operations in Celery.
"""

from src.core.environment import TalkoENV

# Celery configuration constants
REDIS_URL = f"{TalkoENV.CACHE_PROTOCOL}://{TalkoENV.CACHE_USERNAME}:{TalkoENV.CACHE_PASSWORD}@{TalkoENV.CACHE_HOST}:{TalkoENV.CACHE_PORT}/{TalkoENV.CACHE_DB}?ssl_cert_reqs=CERT_NONE"

APP_NAME = TalkoENV.SERVICE_NAME

# Task modules for auto-discovery
TASK_MODULES = [
    "src.talko_celery.tasks",
    "src.components.call_operation.tasks",
    "src.components.call_assets.tasks",
    "src.components.did_management.tasks",
    "src.components.call_management.tasks",
    "src.components.partner_webhook.tasks",
]

task_routes = {
    # Time-sensitive missed-call callbacks get their own queue + dedicated
    # worker so 100s ETAs never queue behind minute-long bulk batches
    # (TalkoCDR reconciler, recordings). Exact names first — Celery matches
    # exact task names before globs.
    "src.components.call_management.tasks.missed_call_callback_task": {
        "queue": "missed_callback_queue"
    },
    "src.components.call_management.tasks.missed_callback_sweeper_task": {
        "queue": "missed_callback_queue"
    },
    # Example task routing
    "src.components.call_operation.*": {
        "queue": "call_operation_queue"
    },  # Dedicated queue for call operation tasks
    "src.components.partner_webhook.*": {"queue": "webhook_delivery_queue"},
    "src.talko_celery.*": {"queue": "default_queue"},
    "src.components.call_assets.*": {"queue": "call_assets_queue"},
    "src.components.did_management.*": {"queue": "did_management_queue"},
    "src.components.call_management.*": {"queue": "call_management_queue"},
}

task_default_queue = "default_queue"
task_acks_late = True
worker_prefetch_multiplier = 1
result_expires = 60 * 60 * 60
timezone = "UTC"
enable_utc = True
