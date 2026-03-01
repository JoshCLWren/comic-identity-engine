# Comic Identity Engine CI/Dev Image
# Single Dockerfile that works for both local development and CI

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.6.3 /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files and project files (needed for package build)
COPY pyproject.toml uv.lock README.md ./
COPY comic_identity_engine/ ./comic_identity_engine/

# Install dependencies using uv (including dev dependencies)
RUN uv sync --dev

# Copy application files
COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY examples/ ./examples/

# Set PATH to use uv-installed binaries
ENV PATH="/app/.venv/bin:$PATH"

# Default command runs the CI script
CMD ["bash", "scripts/ci.sh"]
