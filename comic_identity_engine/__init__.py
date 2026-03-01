"""Comic Identity Engine - Domain-specific entity resolution for comic books."""

from comic_identity_engine.parsing import ParseResult, parse_issue_candidate
from comic_identity_engine.models import IssueCandidate, SeriesCandidate
from comic_identity_engine.adapters import (
    AdapterError,
    NotFoundError,
    SourceAdapter,
    SourceError,
    ValidationError,
)
from comic_identity_engine.gcd_adapter import GCDAdapter

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
