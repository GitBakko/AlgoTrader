# syntax=docker/dockerfile:1

# Dependencies are installed with pip from requirements.txt — the single
# source of truth pinned from the working venv (pyproject.toml is tool
# config only; the old poetry dependency set is abandoned). Mirrors the
# CI install chain (.github/workflows/ci.yml): torch first from the CPU
# wheel index so the requirements pass doesn't pull the multi-GB CUDA
# wheel from PyPI.

# ===== Builder =====
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

# ===== Development Stage =====
FROM python:3.12-slim AS development

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt

# Code is bind-mounted by docker-compose in dev; this COPY is the fallback
COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ===== Production Stage =====
FROM python:3.12-slim AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY . .

RUN useradd -m -u 1000 algotrader && \
    chown -R algotrader:algotrader /app
USER algotrader

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# workers MUST stay 1: the app holds singleton in-process state (paper
# trading loop, dedicated reconciler task, APScheduler P&L snapshotter,
# broker session with 10-min token, WS quote cache). Multiple workers
# would run multiple trading loops against one broker account.
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
