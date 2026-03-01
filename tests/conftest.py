"""Pytest configuration for Comic Identity Engine tests."""

import os

# Set default DATABASE_URL before any imports
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/test_db")
