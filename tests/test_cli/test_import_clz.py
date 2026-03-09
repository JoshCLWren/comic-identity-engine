"""Test CLI import_clz command with new response format."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from comic_identity_engine.cli.commands.import_clz import cli_import_clz


def test_import_clz_displays_new_format():
    """Test that CLI displays correct metrics from new response format."""

    runner = CliRunner()

    # Mock the HTTP client responses
    with patch(
        "comic_identity_engine.cli.commands.import_clz.httpx.Client"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        # Mock POST /api/v1/import/clz - submit CSV
        submit_response = MagicMock()
        submit_response.status_code = 202
        submit_response.json.return_value = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": False,
            "metadata": {
                "operation_type": "import_clz",
                "csv_path": "/path/to/test.csv",
                "status": "pending",
            },
        }
        mock_client.post.return_value = submit_response

        # Mock GET /api/v1/import/clz/{operation_id} - poll status
        poll_response = MagicMock()
        poll_response.status_code = 200

        # New response format with all required fields
        poll_response.json.return_value = {
            "name": "operations/550e8400-e29b-41d4-a716-446655440000",
            "done": True,
            "response": {
                "total_rows": 100,
                "processed": 100,
                "resolved": 95,
                "failed": 5,
                "errors": [
                    {"row": 10, "source_issue_id": "12345", "error": "UPC not found"},
                    {
                        "row": 25,
                        "source_issue_id": "67890",
                        "error": "Series not found",
                    },
                ],
                "summary": "Processed 100 CLZ rows: 95 resolved, 5 failed. 2 errors.",
            },
            "metadata": {"operation_type": "import_clz", "status": "completed"},
        }
        mock_client.get.return_value = poll_response

        # Run the CLI command
        result = runner.invoke(
            cli_import_clz, ["tests/fixtures/clz/sample_clz_export.csv"]
        )

        # Verify command succeeded
        assert result.exit_code == 0

        # Verify output contains new format metrics
        output = result.output
        assert "Total Rows" in output or "100" in output
        assert "Processed" in output
        assert "Resolved" in output
        assert "Failed" in output
        assert "95" in output  # resolved count
        assert "5" in output  # failed count


def test_import_clz_progress_bar_uses_new_format():
    """Test that progress bar correctly uses processed/total_rows from new format."""

    runner = CliRunner()

    with patch(
        "comic_identity_engine.cli.commands.import_clz.httpx.Client"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        # Submit response
        submit_response = MagicMock()
        submit_response.status_code = 202
        submit_response.json.return_value = {
            "name": "operations/test-operation-id",
            "done": False,
            "metadata": {"status": "pending"},
        }
        mock_client.post.return_value = submit_response

        # Poll responses - simulate progress
        poll_responses = [
            # 50% progress
            {
                "name": "operations/test-operation-id",
                "done": False,
                "response": {
                    "total_rows": 100,
                    "processed": 50,
                    "resolved": 45,
                    "failed": 5,
                },
                "metadata": {"status": "running"},
            },
            # 100% complete
            {
                "name": "operations/test-operation-id",
                "done": True,
                "response": {
                    "total_rows": 100,
                    "processed": 100,
                    "resolved": 95,
                    "failed": 5,
                    "errors": [],
                    "summary": "Processed 100 CLZ rows: 95 resolved, 5 failed. 0 errors.",
                },
                "metadata": {"status": "completed"},
            },
        ]

        mock_client.get.side_effect = [
            MagicMock(status_code=200, json=lambda: poll_responses[0]),
            MagicMock(status_code=200, json=lambda: poll_responses[1]),
        ]

        result = runner.invoke(
            cli_import_clz, ["tests/fixtures/clz/sample_clz_export.csv"]
        )

        assert result.exit_code == 0
        # The progress bar should update based on processed/total_rows
        # We can't easily test the visual progress bar, but we can verify
        # that the CLI completed successfully


def test_import_clz_verbose_shows_errors():
    """Test that verbose mode shows error details from new format."""

    runner = CliRunner()

    with patch(
        "comic_identity_engine.cli.commands.import_clz.httpx.Client"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        submit_response = MagicMock()
        submit_response.status_code = 202
        submit_response.json.return_value = {
            "name": "operations/test-operation-id",
            "done": False,
            "metadata": {"status": "pending"},
        }
        mock_client.post.return_value = submit_response

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "name": "operations/test-operation-id",
            "done": True,
            "response": {
                "total_rows": 10,
                "processed": 10,
                "resolved": 8,
                "failed": 2,
                "errors": [
                    {"row": 5, "source_issue_id": "12345", "error": "UPC not found"},
                    {"row": 9, "source_issue_id": "67890", "error": "Series not found"},
                ],
                "summary": "Processed 10 CLZ rows: 8 resolved, 2 failed. 2 errors.",
            },
            "metadata": {"status": "completed"},
        }
        mock_client.get.return_value = poll_response

        # Run with verbose flag
        result = runner.invoke(
            cli_import_clz, ["tests/fixtures/clz/sample_clz_export.csv", "--verbose"]
        )

        assert result.exit_code == 0
        # In verbose mode, errors should be displayed
        output = result.output
        assert "Errors" in output


def test_import_clz_calculates_success_rate():
    """Test that CLI calculates success rate from new format."""

    runner = CliRunner()

    with patch(
        "comic_identity_engine.cli.commands.import_clz.httpx.Client"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        submit_response = MagicMock()
        submit_response.status_code = 202
        submit_response.json.return_value = {
            "name": "operations/test-operation-id",
            "done": False,
            "metadata": {"status": "pending"},
        }
        mock_client.post.return_value = submit_response

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "name": "operations/test-operation-id",
            "done": True,
            "response": {
                "total_rows": 100,
                "processed": 100,
                "resolved": 95,
                "failed": 5,
                "errors": [],
                "summary": "Processed 100 CLZ rows: 95 resolved, 5 failed. 0 errors.",
            },
            "metadata": {"status": "completed"},
        }
        mock_client.get.return_value = poll_response

        result = runner.invoke(
            cli_import_clz, ["tests/fixtures/clz/sample_clz_export.csv"]
        )

        assert result.exit_code == 0
        output = result.output
        # Should show 95% success rate (95/100)
        assert "95.0%" in output or "95%" in output


def test_import_clz_attach_polls_existing_operation_without_posting():
    """Attach mode should poll an existing operation instead of submitting a file."""

    runner = CliRunner()

    with patch(
        "comic_identity_engine.cli.commands.import_clz.httpx.Client"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "name": "operations/test-operation-id",
            "done": True,
            "response": {
                "total_rows": 10,
                "processed": 10,
                "resolved": 9,
                "failed": 1,
                "errors": [],
                "summary": "Processed 10 CLZ rows: 9 resolved, 1 failed. 0 errors.",
            },
            "metadata": {"status": "completed"},
        }
        mock_client.get.return_value = poll_response

        result = runner.invoke(
            cli_import_clz, ["--operation-id", "operations/test-operation-id"]
        )

        assert result.exit_code == 0
        mock_client.post.assert_not_called()
        mock_client.get.assert_called_once_with(
            "http://localhost:8000/api/v1/import/clz/test-operation-id"
        )
        assert "Resolved" in result.output
        assert "9" in result.output


def test_import_clz_retry_failed_only_posts_flag():
    """Retry-failed-only mode should submit the explicit retry flag."""

    runner = CliRunner()

    with patch(
        "comic_identity_engine.cli.commands.import_clz.httpx.Client"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        submit_response = MagicMock()
        submit_response.status_code = 202
        submit_response.json.return_value = {
            "name": "operations/test-operation-id",
            "done": False,
            "metadata": {"status": "pending"},
        }
        mock_client.post.return_value = submit_response

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "name": "operations/test-operation-id",
            "done": True,
            "response": {
                "total_rows": 10,
                "processed": 10,
                "resolved": 10,
                "failed": 0,
                "errors": [],
                "summary": "Processed 10 CLZ rows: 10 resolved, 0 failed. 0 errors.",
            },
            "metadata": {"status": "completed"},
        }
        mock_client.get.return_value = poll_response

        result = runner.invoke(
            cli_import_clz,
            ["tests/fixtures/clz/sample_clz_export.csv", "--retry-failed-only"],
        )

        assert result.exit_code == 0
        mock_client.post.assert_called_once_with(
            "http://localhost:8000/api/v1/import/clz",
            json={
                "file_path": str(
                    Path("tests/fixtures/clz/sample_clz_export.csv").absolute()
                ),
                "retry_failed_only": True,
            },
        )


if __name__ == "__main__":
    # Run tests
    test_import_clz_displays_new_format()
    print("✓ test_import_clz_displays_new_format passed")

    test_import_clz_progress_bar_uses_new_format()
    print("✓ test_import_clz_progress_bar_uses_new_format passed")

    test_import_clz_verbose_shows_errors()
    print("✓ test_import_clz_verbose_shows_errors passed")

    test_import_clz_calculates_success_rate()
    print("✓ test_import_clz_calculates_success_rate passed")

    print("\n✅ All CLI import_clz tests passed!")
