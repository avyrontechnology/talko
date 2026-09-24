FROM python:3.11.8-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/talko-service \
    PORT=8003 \
    POETRY_VERSION=1.8.3

EXPOSE 8003
WORKDIR /talko-service

# curl is needed for the container HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy Poetry configuration first for better layer caching.
COPY poetry.lock pyproject.toml ./

# Install Poetry and project dependencies (main only, no dev packages).
RUN pip3 install --no-cache-dir poetry==${POETRY_VERSION} \
    && pip3 install --no-cache-dir packaging==24.1 \
    && poetry config virtualenvs.create false \
    && poetry install --no-root --only main \
    && rm -rf /root/.cache

# Copy rest of the source code.
COPY . ./

# Run as non-root for production.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /talko-service
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8003}/talko-service/v1/health || exit 1

# PORT env lets hosts dictate the port (ECS, Render, DigitalOcean App
# Platform injects $PORT=8080, HF Spaces uses 7860). Defaults to 8003 locally.
# Production server: no --reload, 2 workers.
CMD ["sh", "-c", "poetry run uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8003} --workers 2"]
