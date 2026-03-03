"""Platform adapters for comic data sources.

This package contains adapters for various comic platforms:
- base: Abstract base classes and exceptions
- gcd: Grand Comics Database adapter
- locg: League of Comic Geeks adapter
- ccl: Comic Collector Live adapter
- aa: Atomic Avenue adapter
- cpg: Comics Price Guide adapter
- hip: HIP Comic adapter
- clz: CLZ CSV import adapter
"""

from comic_identity_engine.adapters.base import (
    AdapterError,
    NotFoundError,
    SourceAdapter,
    SourceError,
    ValidationError,
)
from comic_identity_engine.adapters.aa import AAAdapter
from comic_identity_engine.adapters.gcd import GCDAdapter
from comic_identity_engine.adapters.cpg import CPGAdapter
from comic_identity_engine.adapters.locg import LoCGAdapter
from comic_identity_engine.adapters.hip import HIPAdapter
from comic_identity_engine.adapters.ccl import CCLAdapter
from comic_identity_engine.adapters.clz import CLZAdapter

__all__ = [
    "SourceAdapter",
    "AdapterError",
    "NotFoundError",
    "ValidationError",
    "SourceError",
    "AAAdapter",
    "GCDAdapter",
    "CPGAdapter",
    "LoCGAdapter",
    "HIPAdapter",
    "CCLAdapter",
    "CLZAdapter",
]
