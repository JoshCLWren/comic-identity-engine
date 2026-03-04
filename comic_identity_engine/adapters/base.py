"""Abstract base class for source platform adapters.

Each adapter is responsible for:
1. Fetching data from its source platform (API, file, etc.)
2. Validating issue numbers using parse_issue_candidate()
3. Mapping source-specific formats to internal candidate models
4. Preserving raw payloads for audit/debug

Adapters must NOT:
- Perform reconciliation against canonical entities
- Calculate confidence scores
- Infer data not present in the source
- Modify the parsing logic
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from comic_identity_engine.models import IssueCandidate, SeriesCandidate

if TYPE_CHECKING:
    from comic_identity_engine.core.http_client import HttpClient


class SourceAdapter(ABC):
    """Abstract base class for platform-specific adapters.

    Each adapter implements fetch_series() and fetch_issue() to retrieve
    data from its source platform and return normalized candidate models.

    Attributes:
        http_client: Optional shared HTTP client for making requests.
            If not provided, adapters should create their own.
    """

    def __init__(self, http_client: HttpClient | None = None) -> None:
        """Initialize the adapter.

        Args:
            http_client: Optional shared HTTP client for making requests.
                If provided, the adapter should use this client for all
                HTTP operations. If not provided, the adapter may create
                its own client or use alternative methods.
        """
        self.http_client = http_client

    @abstractmethod
    async def fetch_series(
        self, source_series_id: str
    ) -> SeriesCandidate:  # pragma: no cover
        """Fetch series data from source platform asynchronously.

        Args:
            source_series_id: Platform-specific series identifier

        Returns:
            SeriesCandidate with validated metadata

        Raises:
            NotFoundError: Series does not exist
            ValidationError: Required fields missing or invalid
            SourceError: Platform communication error
        """
        pass

    @abstractmethod
    async def fetch_issue(
        self, source_issue_id: str
    ) -> IssueCandidate:  # pragma: no cover
        """Fetch issue data from source platform asynchronously.

        The issue_number field MUST be validated using parse_issue_candidate()
        before returning the IssueCandidate.

        Args:
            source_issue_id: Platform-specific issue identifier

        Returns:
            IssueCandidate with validated metadata

        Raises:
            NotFoundError: Issue does not exist
            ValidationError: Required fields missing or issue number invalid
            SourceError: Platform communication error
        """
        pass


class AdapterError(Exception):
    """Base class for adapter exceptions."""

    pass


class NotFoundError(AdapterError):
    """Resource not found in source platform."""

    pass


class ValidationError(AdapterError):
    """Data validation failed (missing fields, invalid format, etc.)."""

    pass


class SourceError(AdapterError):
    """Error communicating with source platform."""

    pass
