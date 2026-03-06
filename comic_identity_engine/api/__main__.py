#!/usr/bin/env python
"""Entry point for cie-api command."""

import sys
from uvicorn import main

if __name__ == "__main__":
    sys.argv = [
        "uvicorn",
        "comic_identity_engine.api.main:create_app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        *sys.argv[1:],
    ]
    main()
