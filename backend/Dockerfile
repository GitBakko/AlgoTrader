# syntax=docker/dockerfile:1

# ===== Base Stage =====
FROM python:3.12-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.0 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Set working directory
WORKDIR /app

# ===== Development Stage =====
FROM base as development

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies (including dev dependencies)
RUN poetry install --no-root --with dev

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Command will be overridden by docker-compose
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ===== Production Stage =====
FROM base as production

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install only production dependencies
RUN poetry install --no-root --only main

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 algotrader && \
    chown -R algotrader:algotrader /app
USER algotrader

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
