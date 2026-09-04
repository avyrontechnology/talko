from src.config import settings
from src.core.container import TalkoContainer
from src.talko_celery.celery_config import APP_NAME, REDIS_URL, TASK_MODULES
from src.talko_celery.celery_utils import create_celery

celery = create_celery(
    app_name=APP_NAME,
    broker_url=REDIS_URL,
    backend_url=REDIS_URL,
    task_modules=TASK_MODULES,
    config_module="src.talko_celery.celery_config",
)

celery.container = TalkoContainer()

# To Run Celery Worker
# celery -A talko.celery_app.celery worker --loglevel=info -Q talko_queue
