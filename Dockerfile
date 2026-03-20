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
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files and project files (needed for package build)
COPY pyproject.toml uv.lock README.md ./
COPY comic_identity_engine/ ./comic_identity_engine/

# Accept build arg for private repo access
ARG DEPLOY_TOKEN

# Configure git for private repos (if token provided) and install dependencies
# These are combined in one RUN to ensure git config is available for uv sync
RUN if [ -n "$DEPLOY_TOKEN" ]; then \
        echo "Configuring git with deploy token..." && \
        git config --global url."https://${DEPLOY_TOKEN}@github.com/".insteadOf "https://github.com/"; \
    else \
        echo "No DEPLOY_TOKEN provided, skipping git config"; \
    fi && \
    git config --list && \
    uv sync --dev

# Install Playwright browsers and required system packages for browser-backed scrapers.
RUN uv run playwright install --with-deps chromium

# Copy application files
COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY examples/ ./examples/

# Set PATH to use uv-installed binaries
ENV PATH="/app/.venv/bin:$PATH"

# Default command runs the CI script
CMD ["bash", "scripts/ci.sh"]
