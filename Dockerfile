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
COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files and project files (needed for package build)
COPY pyproject.toml uv.lock README.md ./
COPY comic_identity_engine/ ./comic_identity_engine/

# Copy comic-search-lib dependency (local package)
# Assumes comic-search-lib is copied into the build context before build
COPY comic-search-lib/ /app/comic-search-lib/

# Create symlink so pyproject.toml can find comic-search-lib at its original path
RUN mkdir -p /mnt/extra/josh/code && \
    ln -s /app/comic-search-lib /mnt/extra/josh/code/comic-search-lib

# Install dependencies using uv (including dev dependencies)
RUN uv sync --dev

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
