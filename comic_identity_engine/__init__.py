"""Comic Identity Engine - Domain-specific entity resolution for comic books."""

import importlib

from longbox_commons import ParseResult, parse_issue_candidate
from longbox_commons.models import (
    ComicIdentity,
    IssueCandidate,
    SeriesCandidate,
    SeriesInfo,
)
from comic_identity_engine.adapters import (
    AdapterError,
    GCDAdapter,
    NotFoundError,
    SourceAdapter,
    SourceError,
    ValidationError,
)

__all__ = [
    # Parsing
    "ParseResult",
    "parse_issue_candidate",
    # Models
    "IssueCandidate",
    "SeriesCandidate",
    "SeriesInfo",
    "ComicIdentity",
    # Adapter base
    "SourceAdapter",
    "AdapterError",
    "NotFoundError",
    "ValidationError",
    "SourceError",
    # Concrete adapters
    "GCDAdapter",
    # Configuration
    "config",
    # Database (lazy)
    "database",
    # Errors
    "errors",
    # Core interfaces
    "CacheProvider",
    "SessionManager",
    # Cache implementations
    "MemoryCache",
    "RedisSingleton",
    "TieredCache",
    "http_cached",
    "redis_cache",
]

# Import these immediately (lightweight, no external deps)
from comic_identity_engine import config, errors

# Lazy module loading infrastructure
_LAZY_MODULES = {
    "database": "comic_identity_engine.database",
}

_LAZY_IMPORTS = {
    "CacheProvider": ("comic_identity_engine.core", "CacheProvider"),
    "SessionManager": ("comic_identity_engine.core", "SessionManager"),
    "MemoryCache": ("comic_identity_engine.core.cache", "MemoryCache"),
    "RedisSingleton": ("comic_identity_engine.core.cache", "RedisSingleton"),
    "TieredCache": ("comic_identity_engine.core.cache", "TieredCache"),
    "http_cached": ("comic_identity_engine.core.cache", "http_cached"),
    "redis_cache": ("comic_identity_engine.core.cache", "redis_cache"),
}


def __getattr__(name: str):
    """Lazy import of heavy modules to avoid loading them on CLI startup."""
    # Check if it's a lazy module
    if name in _LAZY_MODULES:
        module_path = _LAZY_MODULES[name]
        module = importlib.import_module(module_path)
        return module

    # Check if it's a lazy import
    if name in _LAZY_IMPORTS:
        module_path, obj_name = _LAZY_IMPORTS[name]
        module = importlib.import_module(module_path)
        return getattr(module, obj_name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
