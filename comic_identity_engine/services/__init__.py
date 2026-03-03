"""Services for Comic Identity Engine.

This package contains business logic services for:
- URL parsing from comic platforms
- Cross-platform identity resolution
- URL building for all platforms
- Operations management (AIP-151)
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

__all__ = [
    "parse_url",
    "ParsedUrl",
    "IdentityResolver",
    "ResolutionResult",
    "MatchCandidate",
    "build_urls",
    "OperationsManager",
]
