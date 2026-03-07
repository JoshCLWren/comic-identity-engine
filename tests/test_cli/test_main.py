"""Comprehensive tests for the Comic Identity Engine CLI main module.

This module tests all CLI functionality including:
- Operation ID extraction
- Operation polling
- Output formatting (JSON, table, URLs)
- Main command execution
- Error handling
"""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner
from rich.console import Console

from comic_identity_engine.cli.main import (
    _build_status_message,
    _build_platform_timeline,
    _display_json,
    _display_table,
    _display_platform_timeline,
    _display_urls,
    _extract_operation_id,
    _format_failure_message,
    _poll_operation,
    cli_find,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def runner():
    """Provide a Click test runner."""
    return CliRunner()


@pytest.fixture
def console():
    """Provide a Rich console for testing."""
    return Console(file=StringIO(), force_terminal=True)


@pytest.fixture
def mock_client():
    """Provide a mock httpx Client."""
    client = MagicMock(spec=httpx.Client)
    return client


@pytest.fixture
def sample_operation_data():
    """Provide sample operation data for testing."""
    return {
        "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        "done": True,
        "response": {
            "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
            "confidence": 0.95,
            "explanation": "Exact match found",
            "platform_urls": {
                "gcd": "https://www.comics.org/issue/12345/",
                "locg": "https://leagueofcomicgeeks.com/comic/12345678/x-men-1",
            },
        },
    }


@pytest.fixture
def sample_incomplete_operation():
    """Provide sample incomplete operation data."""
    return {
        "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        "done": False,
        "metadata": {"status": "processing"},
    }


@pytest.fixture
def sample_failed_operation():
    """Provide sample failed operation data."""
    return {
        "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        "done": True,
        "error": {"message": "Operation failed: Invalid URL format"},
    }


# =============================================================================
# _extract_operation_id Tests
# =============================================================================


class TestExtractOperationId:
    """Test the _extract_operation_id function."""

    def test_extract_operation_id_valid(self):
        """Test extracting UUID from valid operation name."""
        result = _extract_operation_id(
            "operations/550e8400-e29b-41d4-a716-446655440000"
        )
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_extract_operation_id_with_special_chars(self):
        """Test extracting UUID with special characters."""
        result = _extract_operation_id("operations/abc_123-DEF.789+xyz==")
        assert result == "abc_123-DEF.789+xyz=="

    def test_extract_operation_id_no_prefix_raises(self):
        """Test that missing 'operations/' prefix raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            _extract_operation_id("550e8400-e29b-41d4-a716-446655440000")
        assert "Invalid operation name format" in str(exc_info.value)

    def test_extract_operation_id_empty_string_raises(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            _extract_operation_id("")
        assert "Invalid operation name format" in str(exc_info.value)

    def test_extract_operation_id_wrong_prefix_raises(self):
        """Test that wrong prefix raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            _extract_operation_id("operation/550e8400-e29b-41d4-a716-446655440000")
        assert "Invalid operation name format" in str(exc_info.value)

    def test_extract_operation_id_only_prefix_returns_empty(self):
        """Test that only prefix without UUID returns empty string."""
        result = _extract_operation_id("operations/")
        assert result == ""


# =============================================================================
# _poll_operation Tests
# =============================================================================


class TestPollOperation:
    """Test the _poll_operation function."""

    def test_poll_operation_success(self, mock_client, console):
        """Test successful polling until operation completes."""
        completed_data = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {"result": "success"},
        }

        mock_response = MagicMock()
        mock_response.json.return_value = completed_data
        mock_client.get.return_value = mock_response

        result = _poll_operation(
            client=mock_client,
            api_url="http://localhost:8000",
            operation_id="550e8400-e29b-41d4-a716-446655440000",
            timeout=10,
            verbose=False,
            console=console,
        )

        assert result == completed_data
        mock_client.get.assert_called_once_with(
            "http://localhost:8000/api/v1/identity/resolve/550e8400-e29b-41d4-a716-446655440000"
        )

    def test_poll_operation_multiple_polls(self, mock_client, console):
        """Test polling multiple times before completion."""
        incomplete_data = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": False,
            "metadata": {"status": "processing"},
        }
        completed_data = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {"result": "success"},
        }

        mock_client.get.side_effect = [
            MagicMock(json=lambda: incomplete_data),
            MagicMock(json=lambda: incomplete_data),
            MagicMock(json=lambda: completed_data),
        ]

        with patch("time.sleep"):
            result = _poll_operation(
                client=mock_client,
                api_url="http://localhost:8000",
                operation_id="550e8400-e29b-41d4-a716-446655440000",
                timeout=10,
                verbose=False,
                console=console,
            )

        assert result == completed_data
        assert mock_client.get.call_count == 3

    def test_poll_operation_timeout(self, mock_client, console):
        """Test that timeout raises TimeoutError."""
        incomplete_data = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": False,
            "metadata": {"status": "running"},
            "response": {
                "platform_status": {
                    "gcd": "found",
                    "locg": {"status": "searching", "strategy": "fuzzy_title"},
                }
            },
        }

        mock_client.get.return_value = MagicMock(json=lambda: incomplete_data)

        with patch("time.sleep"), patch("time.time") as mock_time:
            mock_time.side_effect = [0, 1, 2, 3, 4, 5]  # Exceeds timeout of 3

            with pytest.raises(TimeoutError) as exc_info:
                _poll_operation(
                    client=mock_client,
                    api_url="http://localhost:8000",
                    operation_id="550e8400-e29b-41d4-a716-446655440000",
                    timeout=3,
                    verbose=False,
                    console=console,
                )

        message = str(exc_info.value)
        assert "did not complete within 3 seconds" in message
        assert "last_status=running" in message
        assert "gcd=found" in message

    def test_poll_operation_error(self, mock_client, console):
        """Test that operation error raises RuntimeError."""
        error_data = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "error": {"message": "Operation failed: Invalid input"},
        }

        mock_response = MagicMock()
        mock_response.json.return_value = error_data
        mock_client.get.return_value = mock_response

        with pytest.raises(RuntimeError) as exc_info:
            _poll_operation(
                client=mock_client,
                api_url="http://localhost:8000",
                operation_id="550e8400-e29b-41d4-a716-446655440000",
                timeout=10,
                verbose=False,
                console=console,
            )

        assert "Operation failed: Invalid input" in str(exc_info.value)

    def test_poll_operation_duplicate_mapping_error_includes_hint(
        self, mock_client, console
    ):
        """Test duplicate mapping failures include a concrete remediation hint."""
        error_data = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "error": {
                "message": (
                    "Unexpected error during resolution: DuplicateEntityError : "
                    "External mapping with source=gcd and source_issue_id=12345 already exists"
                )
            },
            "response": {
                "error_type": "unexpected_error",
                "exception_type": "DuplicateEntityError",
                "source": "gcd",
                "source_issue_id": "12345",
            },
        }

        mock_response = MagicMock()
        mock_response.json.return_value = error_data
        mock_client.get.return_value = mock_response

        with pytest.raises(RuntimeError) as exc_info:
            _poll_operation(
                client=mock_client,
                api_url="http://localhost:8000",
                operation_id="550e8400-e29b-41d4-a716-446655440000",
                timeout=10,
                verbose=False,
                console=console,
                request_url="https://www.comics.org/issue/12345/",
            )

        message = str(exc_info.value)
        assert "--clear-mappings 12345" in message
        assert "restart the API and worker" in message

    def test_format_failure_message_summarizes_platforms(self):
        """Test failure formatter renders platform status compactly."""
        message = _format_failure_message(
            error={"message": "Operation failed"},
            response_context={
                "error_type": "validation_error",
                "platform_status": {
                    "gcd": "found",
                    "locg": {
                        "status": "searching",
                        "strategy": "fuzzy_title",
                        "reason": "retrying",
                        "detail": "waiting for next attempt",
                    },
                },
            },
            request_url="https://www.comics.org/issue/12345/",
        )

        assert "type=validation_error" in message
        assert "gcd=found" in message
        assert "locg=searching (fuzzy_title, reason=retrying, waiting for next attempt)" in message

    def test_poll_operation_verbose_output(self, mock_client, console):
        """Test verbose output during polling."""
        completed_data = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {"result": "success"},
        }

        mock_response = MagicMock()
        mock_response.json.return_value = completed_data
        mock_client.get.return_value = mock_response

        result = _poll_operation(
            client=mock_client,
            api_url="http://localhost:8000",
            operation_id="550e8400-e29b-41d4-a716-446655440000",
            timeout=10,
            verbose=True,
            console=console,
        )

        assert result == completed_data
        output = console.file.getvalue()
        assert "Polling operation" in output
        assert "Cross-platform fan-out" in output
        assert "550e8400-e29b-41d4-a716-446655440000" in output

    def test_poll_operation_verbose_with_status(self, mock_client, console):
        """Test verbose polling leaves the last live status visible."""
        incomplete_data = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": False,
            "metadata": {"status": "processing"},
        }
        completed_data = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {"result": "success"},
        }

        mock_client.get.side_effect = [
            MagicMock(json=lambda: incomplete_data),
            MagicMock(json=lambda: completed_data),
        ]

        with patch("time.sleep"):
            _poll_operation(
                client=mock_client,
                api_url="http://localhost:8000",
                operation_id="550e8400-e29b-41d4-a716-446655440000",
                timeout=10,
                verbose=True,
                console=console,
            )

        output = console.file.getvalue()
        assert "Polling operation" in output
        assert "Status: completed" in output

    def test_poll_operation_http_error(self, mock_client, console):
        """Test handling of HTTP errors during polling."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        mock_client.get.return_value = mock_response

        with pytest.raises(httpx.HTTPStatusError):
            _poll_operation(
                client=mock_client,
                api_url="http://localhost:8000",
                operation_id="550e8400-e29b-41d4-a716-446655440000",
                timeout=10,
                verbose=False,
                console=console,
            )

    def test_poll_operation_error_without_message(self, mock_client, console):
        """Test error handling when error has no message field."""
        error_data = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "error": {"code": 500},  # Non-empty dict but no message field
        }

        mock_response = MagicMock()
        mock_response.json.return_value = error_data
        mock_client.get.return_value = mock_response

        with pytest.raises(RuntimeError) as exc_info:
            _poll_operation(
                client=mock_client,
                api_url="http://localhost:8000",
                operation_id="550e8400-e29b-41d4-a716-446655440000",
                timeout=10,
                verbose=False,
                console=console,
            )

        assert "Unknown error" in str(exc_info.value)


# =============================================================================
# _display_json Tests
# =============================================================================


class TestDisplayJson:
    """Test the _display_json function."""

    def test_display_json_basic(self, capsys):
        """Test basic JSON output."""
        data = {"key": "value", "number": 42}
        _display_json(data)

        captured = capsys.readouterr()
        assert json.loads(captured.out) == data

    def test_display_json_nested(self, capsys):
        """Test nested JSON output."""
        data = {
            "outer": {
                "inner": [1, 2, 3],
                "nested": {"deep": "value"},
            }
        }
        _display_json(data)

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result == data

    def test_display_json_empty(self, capsys):
        """Test empty dict JSON output."""
        _display_json({})

        captured = capsys.readouterr()
        assert captured.out.strip() == "{}"

    def test_display_json_special_chars(self, capsys):
        """Test JSON with special characters."""
        data = {"text": 'Hello "World"', "unicode": "日本語", "newline": "line1\nline2"}
        _display_json(data)

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result == data

    def test_display_json_indentation(self, capsys):
        """Test that JSON is properly indented."""
        data = {"a": 1, "b": 2}
        _display_json(data)

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) > 2  # Should be multi-line with indentation


# =============================================================================
# _display_table Tests
# =============================================================================


class TestDisplayTable:
    """Test the _display_table function."""

    def test_display_table_basic(self, console):
        """Test basic table output."""
        data = {
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "confidence": 0.95,
                "explanation": "Exact match found",
                "platform_urls": {
                    "gcd": "https://www.comics.org/issue/12345/",
                },
                "platform_status": {
                    "gcd": "found",
                    "locg": "not_found",
                },
            }
        }

        _display_table(data, console)
        output = console.file.getvalue()

        assert "abc12345-6789-1234-5678-abcdef123456" in output
        assert "95.00%" in output or "0.95" in output
        assert "Exact match found" in output
        assert "gcd" in output
        assert "checked=2 in parallel" in output

    def test_display_table_verbose_omits_redundant_search_sections(self, console):
        """Test verbose table output leaves search timeline to the timeline renderer."""
        data = {
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "confidence": 0.95,
                "explanation": "Exact match found",
                "platform_urls": {
                    "gcd": "https://www.comics.org/issue/12345/",
                },
                "platform_status": {
                    "gcd": "found",
                    "locg": "not_found",
                },
            }
        }

        _display_table(data, console, verbose=True)
        output = console.file.getvalue()

        assert "Exact match found" in output
        assert "Cross-Platform Search" not in output
        assert "Platform Status" not in output

    def test_display_table_multiple_urls(self, console):
        """Test table with multiple platform URLs."""
        data = {
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "confidence": 0.85,
                "explanation": "High confidence match",
                "platform_urls": {
                    "gcd": "https://www.comics.org/issue/12345/",
                    "locg": "https://leagueofcomicgeeks.com/comic/12345678/",
                    "ccl": "https://www.comiccollectorlive.com/Issue/12345",
                },
            }
        }

        _display_table(data, console)
        output = console.file.getvalue()

        assert "gcd" in output
        assert "locg" in output
        assert "ccl" in output

    def test_display_table_filters_empty_urls(self, console):
        """Test table omits platforms with blank URLs."""
        data = {
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "confidence": 0.85,
                "explanation": "High confidence match",
                "platform_urls": {
                    "gcd": "https://www.comics.org/issue/12345/",
                    "locg": "",
                    "ccl": None,
                },
            }
        }

        _display_table(data, console)
        output = console.file.getvalue()

        assert "https://www.comics.org/issue/12345/" in output
        assert "locg:" not in output
        assert "ccl:" not in output

    def test_display_table_empty_result(self, console):
        """Test table with empty result."""
        data = {"response": {}}

        _display_table(data, console)
        output = console.file.getvalue()

        assert "No results found" in output

    def test_display_table_no_response(self, console):
        """Test table with no response key."""
        data = {}

        _display_table(data, console)
        output = console.file.getvalue()

        assert "No results found" in output

    def test_display_table_no_platform_urls(self, console):
        """Test table without platform URLs."""
        data = {
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "confidence": 0.75,
                "explanation": "Medium confidence",
            }
        }

        _display_table(data, console)
        output = console.file.getvalue()

        assert "abc12345-6789-1234-5678-abcdef123456" in output

    def test_display_table_missing_fields(self, console):
        """Test table with missing optional fields."""
        data = {"response": {}}

        _display_table(data, console)
        output = console.file.getvalue()

        assert "N/A" in output or "No results found" in output

    def test_display_table_zero_confidence(self, console):
        """Test table with zero confidence."""
        data = {
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "confidence": 0.0,
                "explanation": "No match",
            }
        }

        _display_table(data, console)
        output = console.file.getvalue()

        assert "0.00%" in output or "0.0%" in output


# =============================================================================
# _display_urls Tests
# =============================================================================


class TestDisplayUrls:
    """Test the _display_urls function."""

    def test_display_urls_basic(self, capsys):
        """Test basic URL output."""
        data = {
            "response": {
                "platform_urls": {
                    "gcd": "https://www.comics.org/issue/12345/",
                    "locg": "https://leagueofcomicgeeks.com/comic/12345678/",
                }
            }
        }

        _display_urls(data)
        captured = capsys.readouterr()

        lines = captured.out.strip().split("\n")
        assert "https://www.comics.org/issue/12345/" in lines
        assert "https://leagueofcomicgeeks.com/comic/12345678/" in lines

    def test_display_urls_single(self, capsys):
        """Test single URL output."""
        data = {
            "response": {
                "platform_urls": {
                    "gcd": "https://www.comics.org/issue/12345/",
                }
            }
        }

        _display_urls(data)
        captured = capsys.readouterr()

        assert captured.out.strip() == "https://www.comics.org/issue/12345/"

    def test_display_urls_empty(self, capsys):
        """Test empty URLs output."""
        data = {"response": {"platform_urls": {}}}

        _display_urls(data)
        captured = capsys.readouterr()

        assert captured.out.strip() == ""

    def test_display_urls_filters_empty_values(self, capsys):
        """Test URL output skips blank platform URL values."""
        data = {
            "response": {
                "platform_urls": {
                    "gcd": "https://www.comics.org/issue/12345/",
                    "locg": "",
                    "ccl": None,
                }
            }
        }

        _display_urls(data)
        captured = capsys.readouterr()

        assert captured.out.strip() == "https://www.comics.org/issue/12345/"


class TestDisplayPlatformTimeline:
    """Test persisted platform event timeline output."""

    def test_build_platform_timeline_merges_events_into_platform_rows(self):
        """Test verbose timeline summarizes each platform once."""
        data = {
            "response": {
                "platform_urls": {
                    "aa": "https://atomicavenue.com/item/1",
                },
                "platform_status": {
                    "gcd": "found",
                    "locg": "not_found",
                    "aa": "found",
                    "ccl": "not_found",
                    "cpg": "not_found",
                    "hip": "not_found",
                },
                "platform_events": [
                    {"platform": "gcd", "status": "found", "timestamp": 100.0, "reason": "source_mapping"},
                    {"platform": "locg", "status": "searching", "timestamp": 100.0},
                    {"platform": "aa", "status": "searching", "timestamp": 100.0},
                    {"platform": "aa", "status": "found", "timestamp": 101.2, "reason": "match_found"},
                    {"platform": "locg", "status": "not_found", "timestamp": 103.4, "reason": "timeout", "detail": "hit 12.0s platform timeout"},
                ]
            }
        }

        timeline = _build_platform_timeline(data)

        aa = next(entry for entry in timeline if entry["platform"] == "aa")
        locg = next(entry for entry in timeline if entry["platform"] == "locg")

        assert aa["status"] == "found"
        assert aa["started_at"] == "+0.0s"
        assert aa["finished_at"] == "+1.2s"
        assert aa["duration"] == "1.2s"
        assert aa["url"] == "https://atomicavenue.com/item/1"
        assert aa["details"] == "match found"
        assert locg["status"] == "not_found"
        assert locg["finished_at"] == "+3.4s"
        assert "platform timeout" in locg["details"]

    def test_display_platform_timeline_renders_parallel_summary(self, console):
        """Test verbose timeline output is durable and easier to scan."""
        data = {
            "response": {
                "platform_urls": {
                    "aa": "https://atomicavenue.com/item/1",
                },
                "platform_status": {
                    "gcd": "found",
                    "locg": "not_found",
                    "aa": "found",
                    "ccl": "not_found",
                    "cpg": "not_found",
                    "hip": "not_found",
                },
                "platform_events": [
                    {"platform": "gcd", "status": "found", "timestamp": 100.0, "reason": "source_mapping"},
                    {"platform": "locg", "status": "searching", "timestamp": 100.0},
                    {"platform": "aa", "status": "searching", "timestamp": 100.0},
                    {"platform": "aa", "status": "found", "timestamp": 101.2, "reason": "match_found"},
                    {"platform": "locg", "status": "not_found", "timestamp": 103.4, "reason": "timeout", "detail": "hit 12.0s platform timeout"},
                ]
            }
        }

        _display_platform_timeline(data, console)
        output = console.file.getvalue()

        assert "Cross-Platform Timeline" in output
        assert "Atomic Avenue" in output
        assert "League of Comic Geeks" in output
        assert "+0.0s" in output
        assert "+1.2s" in output
        assert "not_found" in output
        assert "timeout" in output


class TestStatusMessage:
    """Test compact polling status rendering."""

    def test_build_status_message_includes_elapsed_time(self):
        """Test status message is compact and includes elapsed time."""
        message = _build_status_message("running", 12.34)

        assert "Status: running" in message
        assert "elapsed=12.3s" in message

    def test_display_urls_no_response(self, capsys):
        """Test output with no response key."""
        data = {}

        _display_urls(data)
        captured = capsys.readouterr()

        assert captured.out.strip() == ""

    def test_display_urls_no_platform_urls(self, capsys):
        """Test output with no platform_urls key."""
        data = {"response": {}}

        _display_urls(data)
        captured = capsys.readouterr()

        assert captured.out.strip() == ""


# =============================================================================
# cli_find Tests
# =============================================================================


class TestCliFind:
    """Test the main cli_find command."""

    def test_cli_find_success_table_output(self, runner):
        """Test successful command with table output (default)."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }
        complete_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "confidence": 0.95,
                "explanation": "Exact match found",
                "platform_urls": {
                    "gcd": "https://www.comics.org/issue/12345/",
                },
            },
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            mock_get_response = MagicMock()
            mock_get_response.json.return_value = complete_response
            mock_client.get.return_value = mock_get_response

            result = runner.invoke(cli_find, ["https://www.comics.org/issue/12345/"])

        assert result.exit_code == 0
        assert "abc12345-6789-1234-5678-abcdef123456" in result.output

    def test_cli_find_success_json_output(self, runner):
        """Test successful command with JSON output."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }
        complete_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "confidence": 0.95,
                "explanation": "Exact match found",
                "platform_urls": {},
            },
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            mock_get_response = MagicMock()
            mock_get_response.json.return_value = complete_response
            mock_client.get.return_value = mock_get_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/", "--output", "json"],
            )

        assert result.exit_code == 0
        output_data = json.loads(result.output)
        assert (
            output_data["response"]["canonical_uuid"]
            == "abc12345-6789-1234-5678-abcdef123456"
        )

    def test_cli_find_success_urls_output(self, runner):
        """Test successful command with URLs output."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }
        complete_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "platform_urls": {
                    "gcd": "https://www.comics.org/issue/12345/",
                    "locg": "https://leagueofcomicgeeks.com/comic/12345678/",
                },
            },
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            mock_get_response = MagicMock()
            mock_get_response.json.return_value = complete_response
            mock_client.get.return_value = mock_get_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/", "--output", "urls"],
            )

        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert "https://www.comics.org/issue/12345/" in lines
        assert "https://leagueofcomicgeeks.com/comic/12345678/" in lines

    def test_cli_find_no_wait(self, runner):
        """Test command with --no-wait flag."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/", "--no-wait"],
            )

        assert result.exit_code == 0
        assert "550e8400-e29b-41d4-a716-446655440000" in result.output
        mock_client.get.assert_not_called()

    def test_cli_find_verbose(self, runner):
        """Test command with --verbose flag."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }
        complete_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "confidence": 0.95,
                "explanation": "Exact match found",
                "platform_urls": {},
            },
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            mock_get_response = MagicMock()
            mock_get_response.json.return_value = complete_response
            mock_client.get.return_value = mock_get_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/", "--verbose"],
            )

        assert result.exit_code == 0
        assert "Resolving URL" in result.output or "API endpoint" in result.output

    def test_cli_find_custom_api_url(self, runner):
        """Test command with custom --api-url."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }
        complete_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "confidence": 0.95,
                "explanation": "Exact match found",
                "platform_urls": {},
            },
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            mock_get_response = MagicMock()
            mock_get_response.json.return_value = complete_response
            mock_client.get.return_value = mock_get_response

            result = runner.invoke(
                cli_find,
                [
                    "https://www.comics.org/issue/12345/",
                    "--api-url",
                    "http://custom-api:8080",
                ],
            )

        assert result.exit_code == 0
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "http://custom-api:8080" in call_args[0][0]

    def test_cli_find_custom_timeout(self, runner):
        """Test command with custom --timeout."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }

        with (
            patch("httpx.Client") as mock_client_class,
            patch("comic_identity_engine.cli.main._poll_operation") as mock_poll,
        ):
            mock_poll.return_value = {
                "done": True,
                "response": {
                    "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                    "platform_urls": {},
                },
            }

            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            result = runner.invoke(
                cli_find,
                [
                    "https://www.comics.org/issue/12345/",
                    "--timeout",
                    "120",
                ],
            )

        assert result.exit_code == 0
        mock_poll.assert_called_once()
        call_kwargs = mock_poll.call_args.kwargs
        assert call_kwargs["timeout"] == 120

    def test_cli_find_default_timeout_matches_long_running_search(self, runner):
        """Test command default timeout allows cross-platform searches to finish."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }

        with (
            patch("httpx.Client") as mock_client_class,
            patch("comic_identity_engine.cli.main._poll_operation") as mock_poll,
        ):
            mock_poll.return_value = {
                "done": True,
                "response": {
                    "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                    "platform_urls": {},
                },
            }

            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/"],
            )

        assert result.exit_code == 0
        mock_poll.assert_called_once()
        call_kwargs = mock_poll.call_args.kwargs
        assert call_kwargs["timeout"] == 180

    def test_cli_find_http_error(self, runner):
        """Test handling of HTTP errors."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"detail": "Not found"}
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=mock_response,
            )
            mock_client.post.return_value = mock_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/"],
            )

        assert result.exit_code == 1
        assert "API error" in result.output

    def test_cli_find_http_error_with_dict_detail(self, runner):
        """Test HTTP error with dict detail."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.json.return_value = {"detail": {"message": "Invalid URL"}}
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "400 Bad Request",
                request=MagicMock(),
                response=mock_response,
            )
            mock_client.post.return_value = mock_response

            result = runner.invoke(
                cli_find,
                ["https://invalid-url"],
            )

        assert result.exit_code == 1
        assert "Invalid URL" in result.output

    def test_cli_find_http_error_with_string_detail(self, runner):
        """Test HTTP error with string detail."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"detail": "Internal server error"}
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=mock_response,
            )
            mock_client.post.return_value = mock_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/"],
            )

        assert result.exit_code == 1
        assert "Internal server error" in result.output

    def test_cli_find_connection_error(self, runner):
        """Test handling of connection errors."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_client.post.side_effect = httpx.RequestError(
                "Connection refused",
                request=MagicMock(),
            )

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/"],
            )

        assert result.exit_code == 1
        assert "Request error" in result.output

    def test_cli_find_timeout_error(self, runner):
        """Test handling of timeout errors."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }

        with (
            patch("httpx.Client") as mock_client_class,
            patch("comic_identity_engine.cli.main._poll_operation") as mock_poll,
        ):
            mock_poll.side_effect = TimeoutError("Operation timed out")

            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/"],
            )

        assert result.exit_code == 1
        assert "Timeout" in result.output

    def test_cli_find_operation_error(self, runner):
        """Test handling of operation errors."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }

        with (
            patch("httpx.Client") as mock_client_class,
            patch("comic_identity_engine.cli.main._poll_operation") as mock_poll,
        ):
            mock_poll.side_effect = RuntimeError("Operation failed: Invalid input")

            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/"],
            )

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_cli_find_missing_operation_name(self, runner):
        """Test handling when API response lacks operation name."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = {}  # No name field
            mock_client.post.return_value = mock_post_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/"],
            )

        assert result.exit_code == 1
        assert "missing operation name" in result.output

    def test_cli_find_invalid_operation_name(self, runner):
        """Test handling when operation name has invalid format."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = {"name": "invalid-operation-name"}
            mock_client.post.return_value = mock_post_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/"],
            )

        assert result.exit_code == 1
        assert "Invalid operation name format" in result.output

    def test_cli_find_unexpected_error(self, runner):
        """Test handling of unexpected errors."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_client.post.side_effect = Exception("Unexpected error occurred")

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/"],
            )

        assert result.exit_code == 1
        assert "Unexpected error" in result.output

    def test_cli_find_json_output_stderr(self, runner):
        """Test that JSON output uses stderr for progress messages."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }
        complete_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "confidence": 0.95,
                "explanation": "Exact match found",
                "platform_urls": {},
            },
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            mock_get_response = MagicMock()
            mock_get_response.json.return_value = complete_response
            mock_client.get.return_value = mock_get_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/", "--output", "json"],
            )

        assert result.exit_code == 0
        # JSON output should be valid and not include Rich formatting
        output_data = json.loads(result.output)
        assert "response" in output_data

    def test_cli_find_short_output_option(self, runner):
        """Test using short -o option for output format."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }
        complete_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "platform_urls": {},
            },
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            mock_get_response = MagicMock()
            mock_get_response.json.return_value = complete_response
            mock_client.get.return_value = mock_get_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/", "-o", "json"],
            )

        assert result.exit_code == 0
        assert (
            json.loads(result.output)["response"]["canonical_uuid"]
            == "abc12345-6789-1234-5678-abcdef123456"
        )

    def test_cli_find_short_verbose_option(self, runner):
        """Test using short -v option for verbose."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }
        complete_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "platform_urls": {},
            },
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            mock_get_response = MagicMock()
            mock_get_response.json.return_value = complete_response
            mock_client.get.return_value = mock_get_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/", "-v"],
            )

        assert result.exit_code == 0

    def test_cli_find_table_case_insensitive(self, runner):
        """Test that output format is case insensitive."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }
        complete_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {
                "canonical_uuid": "abc12345-6789-1234-5678-abcdef123456",
                "platform_urls": {},
            },
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            mock_get_response = MagicMock()
            mock_get_response.json.return_value = complete_response
            mock_client.get.return_value = mock_get_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/", "-o", "TABLE"],
            )

        assert result.exit_code == 0

    def test_cli_find_http_error_non_json_response(self, runner):
        """Test HTTP error with non-JSON response body."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.side_effect = Exception("Invalid JSON")
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=mock_response,
            )
            mock_client.post.return_value = mock_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/"],
            )

        assert result.exit_code == 1
        assert "API error: 500" in result.output

    def test_cli_find_poll_error_with_status(self, runner):
        """Test poll error showing operation error with status."""
        submit_response = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
        }

        with (
            patch("httpx.Client") as mock_client_class,
            patch("comic_identity_engine.cli.main._poll_operation") as mock_poll,
        ):
            mock_poll.side_effect = RuntimeError("Operation failed: processing error")

            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            mock_post_response = MagicMock()
            mock_post_response.json.return_value = submit_response
            mock_client.post.return_value = mock_post_response

            result = runner.invoke(
                cli_find,
                ["https://www.comics.org/issue/12345/"],
            )

        assert result.exit_code == 1
        assert "processing error" in result.output
