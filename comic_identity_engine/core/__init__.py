"""Core infrastructure for Comic Identity Engine.

This module contains shared infrastructure components used across
the application, including caching, HTTP clients, and interfaces.
"""

from comic_identity_engine.core.interfaces import CacheProvider, SessionManager

__all__ = [
    "CacheProvider",
    "SessionManager",
]
