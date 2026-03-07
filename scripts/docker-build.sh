#!/bin/bash
# Build script for Docker containers that copies local dependencies first

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "📦 Preparing Docker build context..."

# Copy comic-search-lib if it exists in the parent directory
if [ -d "/mnt/extra/josh/code/comic-search-lib" ]; then
    echo "📋 Copying comic-search-lib into build context..."
    rm -rf "$PROJECT_ROOT/comic-search-lib"
    # Use rsync to exclude .venv and other build artifacts
    rsync -av --exclude='.venv' --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
        /mnt/extra/josh/code/comic-search-lib/ "$PROJECT_ROOT/comic-search-lib/"
    # Double-check and remove any .venv that slipped through
    rm -rf "$PROJECT_ROOT/comic-search-lib/.venv"
    echo "✅ comic-search-lib copied (excluding virtual environments)"
else
    echo "⚠️  Warning: comic-search-lib not found at /mnt/extra/josh/code/comic-search-lib"
    echo "   Build may fail if this dependency is required"
fi

echo "🐳 Building Docker image..."
docker compose build "$@"

echo "🧹 Cleaning up build artifacts..."
rm -rf "$PROJECT_ROOT/comic-search-lib"

echo "✅ Build complete!"
