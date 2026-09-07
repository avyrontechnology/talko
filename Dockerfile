FROM python:3.11.8-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/talko-service

EXPOSE 8003
WORKDIR /talko-service

# Copy Poetry configuration files
COPY poetry.lock pyproject.toml ./

# Install Poetry and dependencies
RUN pip3 install poetry==1.8.3
# Explicitly install packaging to avoid FileNotFoundError
RUN pip3 install packaging==24.1
RUN poetry config virtualenvs.create false
# Install dependencies without the root project to avoid potential issues
RUN poetry install --no-root

# Copy rest of the source code
COPY . ./

# CMD poetry run alembic upgrade head && \
# CMD poetry run uvicorn --host=0.0.0.0 --port=8003 src.main:app --reload &\
#     poetry run celery -A src.maglo_celery.celery_app.celery worker --loglevel=info --concurrency=4
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
# PORT env lets hosts like Hugging Face Spaces (7860) dictate the port.
CMD ["sh", "-c", "poetry run uvicorn --host=0.0.0.0 --port=${PORT:-8003} src.main:app"]

