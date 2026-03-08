"""
Error classes for comic search library.

Simplified error hierarchy extracted from comic-web-scrapers.
"""


class SearchError(Exception):
    """Base class for all search-related errors."""

    def __init__(self, message, source=None, original_error=None):
        """
        Initialize a search error.

        Args:
            message: Error message
            source: Source of the error (e.g., 'atomic_avenue', 'hip')
            original_error: Original exception that caused this error
        """
        self.source = source
        self.original_error = original_error
        super().__init__(message)

    def __str__(self):
        """Return a string representation of the error."""
        source_str = f" [{self.source}]" if self.source else ""
        return f"{self.__class__.__name__}{source_str}: {super().__str__()}"


class NetworkError(SearchError):
    """Error for network-related issues (connection, timeout, etc.)."""

    def __init__(self, message, source=None, original_error=None, status_code=None):
        """
        Initialize a network error.

        Args:
            message: Error message
            source: Source of the error (e.g., 'atomic_avenue', 'hip')
            original_error: Original exception that caused this error
            status_code: HTTP status code if applicable
        """
        self.status_code = status_code
        super().__init__(message, source, original_error)

    def __str__(self):
        """Return a string representation of the error."""
        status_str = f" (HTTP {self.status_code})" if self.status_code else ""
        return f"{super().__str__()}{status_str}"


class AuthenticationError(SearchError):
    """Error for authentication-related issues (invalid credentials, tokens, etc.)."""

    pass


class ParseError(SearchError):
    """Error for parsing-related issues (invalid HTML, unexpected format, etc.)."""

    pass


class RateLimitError(NetworkError):
    """Error for rate limit-related issues."""

    def __init__(self, message, source=None, original_error=None, retry_after=None):
        """
        Initialize a rate limit error.

        Args:
            message: Error message
            source: Source of the error (e.g., 'atomic_avenue', 'hip')
            original_error: Original exception that caused this error
            retry_after: Suggested retry after seconds if available
        """
        self.retry_after = retry_after
        super().__init__(message, source, original_error, status_code=429)


class ResourceExhaustedError(SearchError):
    """Error for resource exhaustion issues (too many redirects, etc.)."""

    pass


class ValidationError(SearchError):
    """Error for validation-related issues (invalid input, etc.)."""

    pass
