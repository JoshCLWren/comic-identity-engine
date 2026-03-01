"""Platform adapters for comic data sources.

This package contains adapters for various comic platforms:
- base: Abstract base classes and exceptions
- gcd: Grand Comics Database adapter
- locg: League of Comic Geeks adapter (TODO)
- ccl: Comic Collector Live adapter (TODO)
- aa: Atomic Avenue adapter (TODO)
- cpg: Comics Price Guide adapter (TODO)
- hip: HIP Comic adapter (TODO)
- clz: CLZ CSV import adapter (TODO)
"""

from comic_identity_engine.adapters.base import (
    AdapterError,
    NotFoundError,
    SourceAdapter,
    SourceError,
    ValidationError,
)

from comic_identity_engine.adapters.gcd import GCDAdapter

__all__ = [
    "SourceAdapter",
    "AdapterError",
    "NotFoundError",
    "ValidationError",
    "SourceError",
    "GCDAdapter",
]
