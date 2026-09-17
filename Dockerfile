FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/api/app ./app
COPY apps/web/public/nextphase-logo.png ./apps/web/public/nextphase-logo.png

CMD ["/bin/sh", "-c", ".venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
