"""Error classes for Comic Identity Engine.

SOURCE: Derived from comic-web-scrapers/comic_scrapers/common/errors.py
MODIFICATIONS:
- Renamed: ScraperError → AdapterError (matches our existing base.py)
- Added: ResolutionError for identity resolution failures
- Kept: All specialized error types for consistency

USAGE:
- Platform adapter error handling
- Network error handling for HTTP requests
- Parse error handling for HTML/JSON responses
- Validation errors for user input
- Rate limiting errors
- Identity resolution errors

USED BY:
- All platform adapters (adapters/*.py)
- Identity resolver service
- API error handlers
- CLI commands
"""


class AdapterError(Exception):
    """Base class for all adapter-related errors.

    This was renamed from ScraperError to match our domain model.
    All adapter-specific exceptions inherit from this class.
    """

    def __init__(self, message, source=None, original_error=None):
        """Initialize an adapter error.

        Args:
            message (str): Error message
            source (str, optional): Source of the error (e.g., 'hip', 'cpg', 'gcd')
            original_error (Exception, optional): Original exception that caused this error
        """
        self.source = source
        self.original_error = original_error
        super().__init__(message)

    def __str__(self):
        """Return a string representation of the error."""
        source_str = f" [{self.source}]" if self.source else ""
        return f"{self.__class__.__name__}{source_str}: {super().__str__()}"


class NetworkError(AdapterError):
    """Error for network-related issues (connection, timeout, etc.)."""

    def __init__(self, message, source=None, original_error=None, status_code=None):
        """Initialize a network error.

        Args:
            message (str): Error message
            source (str, optional): Source of the error (e.g., 'hip', 'cpg')
            original_error (Exception, optional): Original exception that caused this error
            status_code (int, optional): HTTP status code if applicable
        """
        self.status_code = status_code
        super().__init__(message, source, original_error)

    def __str__(self):
        """Return a string representation of the error."""
        status_str = f" (HTTP {self.status_code})" if self.status_code else ""
        return f"{super().__str__()}{status_str}"


class AuthenticationError(AdapterError):
    """Error for authentication-related issues (invalid credentials, tokens, etc.)."""

    pass


class ParseError(AdapterError):
    """Error for parsing-related issues (invalid HTML, unexpected format, etc.)."""

    pass


class RateLimitError(NetworkError):
    """Error for rate limit-related issues."""

    def __init__(self, message, source=None, original_error=None, retry_after=None):
        """Initialize a rate limit error.

        Args:
            message (str): Error message
            source (str, optional): Source of the error (e.g., 'hip', 'cpg')
            original_error (Exception, optional): Original exception that caused this error
            retry_after (int, optional): Suggested retry after seconds if available
        """
        self.retry_after = retry_after
        super().__init__(message, source, original_error, status_code=429)

    def __str__(self):
        """Return a string representation of the error."""
        retry_str = f", retry after {self.retry_after}s" if self.retry_after else ""
        return f"{super().__str__()}{retry_str}"


class ConfigurationError(AdapterError):
    """Error for configuration-related issues."""

    pass


class ResourceExhaustedError(AdapterError):
    """Error for resource exhaustion (too many connections, memory, etc.)."""

    pass


class ValidationError(AdapterError):
    """Error for data validation issues."""

    pass


class ResolutionError(AdapterError):
    """Error for identity resolution failures.

    This error is raised when cross-platform identity resolution fails
    or cannot achieve sufficient confidence.
    """

    def __init__(self, message, confidence=None, candidates=None, original_error=None):
        """Initialize a resolution error.

        Args:
            message (str): Error message
            confidence (float, optional): Best confidence score achieved
            candidates (list, optional): List of candidate matches that were considered
            original_error (Exception, optional): Original exception that caused this error
        """
        self.confidence = confidence
        self.candidates = candidates or []
        super().__init__(message, source="resolver", original_error=original_error)

    def __str__(self):
        """Return a string representation of the error."""
        confidence_str = (
            f" (best confidence: {self.confidence})"
            if self.confidence is not None
            else ""
        )
        candidates_str = (
            f" ({len(self.candidates)} candidates)" if self.candidates else ""
        )
        return f"{super().__str__()}{confidence_str}{candidates_str}"


class RepositoryError(AdapterError):
    """Error for repository-related issues.

    This error is raised when database operations fail at the repository layer.
    """

    pass


class DuplicateEntityError(RepositoryError):
    """Error for duplicate entity creation attempts.

    This error is raised when attempting to create an entity that violates
    a unique constraint (e.g., duplicate external mapping, duplicate variant).
    """

    def __init__(
        self, message, entity_type=None, existing_id=None, original_error=None
    ):
        """Initialize a duplicate entity error.

        Args:
            message (str): Error message
            entity_type (str, optional): Type of entity (e.g., 'ExternalMapping', 'Variant')
            existing_id (str, optional): ID of the existing entity
            original_error (Exception, optional): Original exception that caused this error
        """
        self.entity_type = entity_type
        self.existing_id = existing_id
        super().__init__(message, source="repository", original_error=original_error)

    def __str__(self):
        """Return a string representation of the error."""
        type_str = f" [{self.entity_type}]" if self.entity_type else ""
        id_str = f" (existing: {self.existing_id})" if self.existing_id else ""
        return f"{super().__str__()}{type_str}{id_str}"


class EntityNotFoundError(RepositoryError):
    """Error for entity not found.

    This error is raised when attempting to update or delete an entity
    that does not exist in the database.
    """

    def __init__(self, message, entity_type=None, entity_id=None, original_error=None):
        """Initialize an entity not found error.

        Args:
            message (str): Error message
            entity_type (str, optional): Type of entity (e.g., 'Issue', 'SeriesRun')
            entity_id (str, optional): ID of the entity that was not found
            original_error (Exception, optional): Original exception that caused this error
        """
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(message, source="repository", original_error=original_error)

    def __str__(self):
        """Return a string representation of the error."""
        type_str = f" [{self.entity_type}]" if self.entity_type else ""
        id_str = f" (id: {self.entity_id})" if self.entity_id else ""
        return f"{super().__str__()}{type_str}{id_str}"
