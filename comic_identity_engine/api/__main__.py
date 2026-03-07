#!/usr/bin/env python
"""Entry point for the local API server."""

from __future__ import annotations

import sys

from uvicorn import main


def run() -> None:
    """Run the API using the project environment's installed uvicorn."""
    sys.argv = [
        "uvicorn",
        "comic_identity_engine.api.main:create_app",
        "--factory",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        *sys.argv[1:],
    ]
    main()


if __name__ == "__main__":
    run()
