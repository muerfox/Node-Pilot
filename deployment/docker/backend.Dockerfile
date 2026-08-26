# NodePilot Controller image. Used for local development via
# docker-compose; production deployments are documented in
# docs/installation.md and do not require Docker (the agent in
# particular must run directly on the hypervisor host).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/requirements/ requirements/
RUN pip install -r requirements/development.txt

COPY backend/ .

EXPOSE 8000

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
