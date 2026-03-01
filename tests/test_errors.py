"""Tests for error classes."""

import pytest

from comic_identity_engine.errors import (
    AdapterError,
    AuthenticationError,
    ConfigurationError,
    NetworkError,
    ParseError,
    RateLimitError,
    ResourceExhaustedError,
    ResolutionError,
    ValidationError,
)


class TestAdapterError:
    """Tests for AdapterError base class."""

    def test_basic_error_message(self):
        """Test basic error message."""
        error = AdapterError("Test error message")
        assert str(error) == "AdapterError: Test error message"
        assert error.source is None
        assert error.original_error is None

    def test_error_with_source(self):
        """Test error with source."""
        error = AdapterError("Test error", source="gcd")
        assert str(error) == "AdapterError [gcd]: Test error"
        assert error.source == "gcd"

    def test_error_with_original_error(self):
        """Test error with original error."""
        original = ValueError("Original error")
        error = AdapterError("Wrapper error", original_error=original)
        assert error.original_error is original

    def test_error_with_source_and_original(self):
        """Test error with both source and original error."""
        original = ConnectionError("Connection failed")
        error = AdapterError("Network error", source="hip", original_error=original)
        assert str(error) == "AdapterError [hip]: Network error"
        assert error.source == "hip"
        assert error.original_error is original


class TestNetworkError:
    """Tests for NetworkError class."""

    def test_basic_network_error(self):
        """Test basic network error."""
        error = NetworkError("Connection timeout")
        assert str(error) == "NetworkError: Connection timeout"
        assert error.status_code is None

    def test_network_error_with_status_code(self):
        """Test network error with HTTP status code."""
        error = NetworkError("HTTP error", status_code=404)
        assert str(error) == "NetworkError: HTTP error (HTTP 404)"
        assert error.status_code == 404

    def test_network_error_with_source(self):
        """Test network error with source."""
        error = NetworkError("API error", source="cpg", status_code=500)
        assert str(error) == "NetworkError [cpg]: API error (HTTP 500)"

    def test_network_error_with_original_error(self):
        """Test network error with original error."""
        original = TimeoutError("Request timeout")
        error = NetworkError("Timeout error", original_error=original, status_code=408)
        assert error.original_error is original


class TestAuthenticationError:
    """Tests for AuthenticationError class."""

    def test_basic_authentication_error(self):
        """Test basic authentication error."""
        error = AuthenticationError("Invalid API key")
        assert str(error) == "AuthenticationError: Invalid API key"

    def test_authentication_error_with_source(self):
        """Test authentication error with source."""
        error = AuthenticationError("Token expired", source="gcd")
        assert str(error) == "AuthenticationError [gcd]: Token expired"


class TestParseError:
    """Tests for ParseError class."""

    def test_basic_parse_error(self):
        """Test basic parse error."""
        error = ParseError("Invalid JSON structure")
        assert str(error) == "ParseError: Invalid JSON structure"

    def test_parse_error_with_source(self):
        """Test parse error with source."""
        error = ParseError("HTML parsing failed", source="hip")
        assert str(error) == "ParseError [hip]: HTML parsing failed"


class TestRateLimitError:
    """Tests for RateLimitError class."""

    def test_basic_rate_limit_error(self):
        """Test basic rate limit error."""
        error = RateLimitError("Rate limit exceeded")
        assert str(error) == "RateLimitError: Rate limit exceeded (HTTP 429)"
        assert error.status_code == 429
        assert error.retry_after is None

    def test_rate_limit_error_with_retry_after(self):
        """Test rate limit error with retry_after."""
        error = RateLimitError("Too many requests", retry_after=60)
        assert (
            str(error)
            == "RateLimitError: Too many requests (HTTP 429), retry after 60s"
        )
        assert error.retry_after == 60

    def test_rate_limit_error_with_all_fields(self):
        """Test rate limit error with all fields."""
        error = RateLimitError("API rate limit", source="gcd", retry_after=120)
        assert (
            str(error)
            == "RateLimitError [gcd]: API rate limit (HTTP 429), retry after 120s"
        )
        assert error.source == "gcd"
        assert error.retry_after == 120


class TestConfigurationError:
    """Tests for ConfigurationError class."""

    def test_basic_configuration_error(self):
        """Test basic configuration error."""
        error = ConfigurationError("Missing environment variable")
        assert str(error) == "ConfigurationError: Missing environment variable"


class TestResourceExhaustedError:
    """Tests for ResourceExhaustedError class."""

    def test_basic_resource_exhausted_error(self):
        """Test basic resource exhausted error."""
        error = ResourceExhaustedError("Connection pool exhausted")
        assert str(error) == "ResourceExhaustedError: Connection pool exhausted"


class TestValidationError:
    """Tests for ValidationError class."""

    def test_basic_validation_error(self):
        """Test basic validation error."""
        error = ValidationError("Invalid issue number format")
        assert str(error) == "ValidationError: Invalid issue number format"

    def test_validation_error_with_source(self):
        """Test validation error with source."""
        error = ValidationError("Missing required field", source="gcd")
        assert str(error) == "ValidationError [gcd]: Missing required field"


class TestResolutionError:
    """Tests for ResolutionError class."""

    def test_basic_resolution_error(self):
        """Test basic resolution error."""
        error = ResolutionError("No match found")
        assert str(error) == "ResolutionError [resolver]: No match found"
        assert error.confidence is None
        assert error.candidates == []

    def test_resolution_error_with_confidence(self):
        """Test resolution error with confidence score."""
        error = ResolutionError("Low confidence match", confidence=0.45)
        assert (
            str(error)
            == "ResolutionError [resolver]: Low confidence match (best confidence: 0.45)"
        )
        assert error.confidence == 0.45

    def test_resolution_error_with_candidates(self):
        """Test resolution error with candidates."""
        candidates = [{"id": 1, "title": "X-Men #1"}, {"id": 2, "title": "X-Men #2"}]
        error = ResolutionError("Multiple candidates found", candidates=candidates)
        assert (
            str(error)
            == "ResolutionError [resolver]: Multiple candidates found (2 candidates)"
        )
        assert error.candidates == candidates

    def test_resolution_error_with_confidence_and_candidates(self):
        """Test resolution error with both confidence and candidates."""
        candidates = [{"id": 1, "confidence": 0.7}]
        error = ResolutionError(
            "Ambiguous match", confidence=0.7, candidates=candidates
        )
        assert (
            str(error)
            == "ResolutionError [resolver]: Ambiguous match (best confidence: 0.7) (1 candidates)"
        )
        assert error.confidence == 0.7
        assert len(error.candidates) == 1

    def test_resolution_error_with_original_error(self):
        """Test resolution error with original error."""
        original = ValueError("Calculation failed")
        error = ResolutionError("Resolution failed", original_error=original)
        assert error.original_error is original

    def test_resolution_error_empty_candidates_list(self):
        """Test resolution error with empty candidates list."""
        error = ResolutionError("No candidates", candidates=[])
        assert str(error) == "ResolutionError [resolver]: No candidates"

    def test_resolution_error_zero_confidence(self):
        """Test resolution error with zero confidence."""
        error = ResolutionError("No match", confidence=0.0)
        assert (
            str(error) == "ResolutionError [resolver]: No match (best confidence: 0.0)"
        )

    def test_resolution_error_high_confidence(self):
        """Test resolution error with high confidence."""
        error = ResolutionError("Good match but below threshold", confidence=0.85)
        assert (
            str(error)
            == "ResolutionError [resolver]: Good match but below threshold (best confidence: 0.85)"
        )


class TestErrorInheritance:
    """Tests for error class inheritance."""

    def test_adapter_error_is_exception(self):
        """Test AdapterError inherits from Exception."""
        assert issubclass(AdapterError, Exception)

    def test_network_error_inherits_adapter_error(self):
        """Test NetworkError inherits from AdapterError."""
        error = NetworkError("Test")
        assert isinstance(error, AdapterError)
        assert isinstance(error, Exception)

    def test_authentication_error_inherits_adapter_error(self):
        """Test AuthenticationError inherits from AdapterError."""
        error = AuthenticationError("Test")
        assert isinstance(error, AdapterError)

    def test_parse_error_inherits_adapter_error(self):
        """Test ParseError inherits from AdapterError."""
        error = ParseError("Test")
        assert isinstance(error, AdapterError)

    def test_rate_limit_error_inherits_network_error(self):
        """Test RateLimitError inherits from NetworkError."""
        error = RateLimitError("Test")
        assert isinstance(error, NetworkError)
        assert isinstance(error, AdapterError)

    def test_validation_error_inherits_adapter_error(self):
        """Test ValidationError inherits from AdapterError."""
        error = ValidationError("Test")
        assert isinstance(error, AdapterError)

    def test_resolution_error_inherits_adapter_error(self):
        """Test ResolutionError inherits from AdapterError."""
        error = ResolutionError("Test")
        assert isinstance(error, AdapterError)


class TestErrorAttributes:
    """Tests for error attribute access."""

    def test_adapter_error_attributes(self):
        """Test AdapterError has correct attributes."""
        error = AdapterError("Test", source="test", original_error=ValueError("orig"))
        assert hasattr(error, "source")
        assert hasattr(error, "original_error")
        assert error.source == "test"
        assert isinstance(error.original_error, ValueError)

    def test_network_error_additional_attributes(self):
        """Test NetworkError has additional attributes."""
        error = NetworkError("Test", status_code=404)
        assert hasattr(error, "status_code")
        assert error.status_code == 404

    def test_rate_limit_error_additional_attributes(self):
        """Test RateLimitError has additional attributes."""
        error = RateLimitError("Test", retry_after=60)
        assert hasattr(error, "retry_after")
        assert error.retry_after == 60

    def test_resolution_error_additional_attributes(self):
        """Test ResolutionError has additional attributes."""
        candidates = [{"id": 1}]
        error = ResolutionError("Test", confidence=0.5, candidates=candidates)
        assert hasattr(error, "confidence")
        assert hasattr(error, "candidates")
        assert error.confidence == 0.5
        assert error.candidates == candidates


class TestErrorCatching:
    """Tests for catching and raising errors."""

    def test_catch_adapter_error_base(self):
        """Test catching errors as AdapterError."""
        with pytest.raises(AdapterError) as exc_info:
            raise NetworkError("Network failed")
        assert isinstance(exc_info.value, NetworkError)

    def test_catch_network_error_specifically(self):
        """Test catching NetworkError specifically."""
        with pytest.raises(NetworkError):
            raise RateLimitError("Rate limited")

    def test_catch_resolution_error(self):
        """Test catching ResolutionError."""
        with pytest.raises(ResolutionError) as exc_info:
            raise ResolutionError("No match", confidence=0.1)
        assert exc_info.value.confidence == 0.1
