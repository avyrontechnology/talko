from src.config import settings
from src.core.container import Container
from src.holler_celery.celery_config import APP_NAME, REDIS_URL, TASK_MODULES
from src.holler_celery.celery_utils import create_celery

celery = create_celery(
    app_name=APP_NAME,
    broker_url=REDIS_URL,
    backend_url=REDIS_URL,
    task_modules=TASK_MODULES,
    config_module="src.holler_celery.celery_config",
)

celery.container = Container()

# To Run Celery Worker
# celery -A holler.celery_app.celery worker --loglevel=info -Q holler_queue
