"""Comic Identity Engine - Domain-specific entity resolution for comic books."""

from comic_identity_engine.parsing import ParseResult, parse_issue_candidate
from comic_identity_engine.models import IssueCandidate, SeriesCandidate
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
    # Adapter base
    "SourceAdapter",
    "AdapterError",
    "NotFoundError",
    "ValidationError",
    "SourceError",
    # Concrete adapters
    "GCDAdapter",
]
