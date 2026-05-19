# syntax=docker/dockerfile:1.7
# Multi-stage build. Final image runs as non-root user.

FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --upgrade pip && \
    pip wheel --wheel-dir /wheels .

# ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 brainbot

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels brainbot && rm -rf /wheels

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/

RUN mkdir -p /app/secrets && chown -R brainbot:brainbot /app

USER brainbot

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "brainbot.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
