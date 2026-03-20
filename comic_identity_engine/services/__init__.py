"""Services for Comic Identity Engine.

This package contains business logic services for:
- URL parsing from comic platforms
- Cross-platform identity resolution
- URL building for all platforms
- Operations management (AIP-151)
- Catalog browsing for deterministic comic lookup
"""

from comic_identity_engine.services.url_parser import (
    parse_url,
    ParsedUrl,
)
from comic_identity_engine.services.identity_resolver import (
    IdentityResolver,
    ResolutionResult,
    MatchCandidate,
)
from comic_identity_engine.services.url_builder import (
    build_urls,
)
from comic_identity_engine.services.operations import (
    OperationsManager,
)
from comic_identity_engine.services.canonical_repair import (
    CanonicalRepairService,
)
from comic_identity_engine.services.series_page_extractor import (
    SeriesPageExtractor,
    SeriesExtractionResult,
)
from comic_identity_engine.services.catalog_browser import (
    CatalogBrowser,
    CatalogMatchResult,
)
from comic_identity_engine.services.gcd_dump_matcher import (
    GCDDumpMatcher,
    GCDMatchResult,
)

__all__ = [
    "parse_url",
    "ParsedUrl",
    "IdentityResolver",
    "ResolutionResult",
    "MatchCandidate",
    "build_urls",
    "OperationsManager",
    "CanonicalRepairService",
    "SeriesPageExtractor",
    "SeriesExtractionResult",
    "CatalogBrowser",
    "CatalogMatchResult",
    "GCDDumpMatcher",
    "GCDMatchResult",
]
