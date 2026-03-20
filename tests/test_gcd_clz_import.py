"""Tests for GCD matching integration in CLZ import pipeline.

These tests verify the integration between tasks.py and the GCD matching service,
specifically the _get_gcd_matching_service() and _try_gcd_match() functions.

The tests mock GCDMatchingService to avoid database dependencies.
"""

from unittest.mock import MagicMock, patch


from comic_identity_engine.jobs.tasks import _get_gcd_matching_service, _try_gcd_match
from comic_identity_engine.matching.types import MatchConfidence, StrategyResult


class TestGetGCDMatchingService:
    """Tests for _get_gcd_matching_service() singleton."""

    @patch("comic_identity_engine.jobs.tasks._GCD_MATCHING_SERVICE", None)
    @patch("comic_identity_engine.matching.adapter.GCDLocalAdapter")
    @patch("comic_identity_engine.matching.service.GCDMatchingService")
    def test_successful_initialization(
        self, mock_service_class, mock_adapter_class
    ) -> None:
        """Singleton is initialized successfully when database is available."""
        mock_adapter = MagicMock()
        mock_adapter._loaded = True
        mock_adapter.series_count = 100000
        mock_adapter.issue_count = 2000000
        mock_adapter_class.return_value = mock_adapter

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        result = _get_gcd_matching_service()

        assert result is not None
        assert result == mock_service
        mock_adapter.load.assert_called_once()
        mock_service_class.assert_called_once_with(adapter=mock_adapter)

    @patch("comic_identity_engine.jobs.tasks._GCD_MATCHING_SERVICE", None)
    @patch("comic_identity_engine.matching.adapter.GCDLocalAdapter")
    def test_adapter_unavailable_closes_connection(self, mock_adapter_class) -> None:
        """When adapter fails to load, connection is closed and singleton is None."""
        mock_adapter = MagicMock()
        mock_adapter._loaded = False
        mock_adapter_class.return_value = mock_adapter

        result = _get_gcd_matching_service()

        assert result is None
        mock_adapter.load.assert_called_once()
        mock_adapter.close.assert_called_once()

    @patch("comic_identity_engine.jobs.tasks._GCD_MATCHING_SERVICE", None)
    @patch("comic_identity_engine.matching.adapter.GCDLocalAdapter")
    @patch("comic_identity_engine.matching.service.GCDMatchingService")
    def test_singleton_reuse(self, mock_service_class, mock_adapter_class) -> None:
        """Subsequent calls return the same singleton instance."""
        mock_adapter = MagicMock()
        mock_adapter._loaded = True
        mock_adapter_class.return_value = mock_adapter

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        first = _get_gcd_matching_service()
        second = _get_gcd_matching_service()

        assert first is second
        mock_adapter_class.assert_called_once()


class TestTryGCDMatch:
    """Tests for _try_gcd_match() integration function."""

    def setup_method(self):
        """Reset singleton before each test."""
        import comic_identity_engine.jobs.tasks as tasks_module

        tasks_module._GCD_MATCHING_SERVICE = None

    def test_high_confidence_match_returns_result(self) -> None:
        """High-confidence match (>=90) returns match dictionary."""
        mock_service = MagicMock()
        mock_result = StrategyResult(
            confidence=MatchConfidence.EXACT_ONE_ISSUE,  # value = 90
            gcd_issue_id=12345,
            strategy_name="exact_one_issue",
        )
        mock_service.match.return_value = mock_result

        with patch(
            "comic_identity_engine.jobs.tasks._get_gcd_matching_service",
            return_value=mock_service,
        ):
            row = {
                "Core ComicID": "clz-123",
                "Series": "X-Men",
                "Issue": "1",
                "Cover Year": "1963",
                "Barcode": "",
            }
            issue_candidate = MagicMock(
                series_title="X-Men",
                issue_number="1",
            )

            result = _try_gcd_match(row, issue_candidate)

            assert result is not None
            assert result["gcd_issue_id"] == 12345
            assert result["strategy_name"] == "exact_one_issue"
            assert result["confidence"] == 90
            mock_service.match.assert_called_once()

    def test_barcode_match_returns_result(self) -> None:
        """Barcode match (confidence=100) returns match dictionary."""
        mock_service = MagicMock()
        mock_result = StrategyResult(
            confidence=MatchConfidence.BARCODE,  # value = 100
            gcd_issue_id=54321,
            strategy_name="barcode",
        )
        mock_service.match.return_value = mock_result

        with patch(
            "comic_identity_engine.jobs.tasks._get_gcd_matching_service",
            return_value=mock_service,
        ):
            row = {
                "Core ComicID": "clz-456",
                "Series": "X-Men",
                "Issue": "1",
                "Barcode": "9781302945374",
            }
            issue_candidate = MagicMock(
                series_title="X-Men",
                issue_number="1",
            )

            result = _try_gcd_match(row, issue_candidate)

            assert result is not None
            assert result["gcd_issue_id"] == 54321
            assert result["confidence"] == 100

    def test_low_confidence_match_returns_none(self) -> None:
        """Low-confidence match (<90) returns None (fallback to resolver)."""
        mock_service = MagicMock()
        mock_result = StrategyResult(
            confidence=MatchConfidence.EXACT_CLOSEST_YEAR,  # value = 85
            gcd_issue_id=67890,
            strategy_name="exact_closest_year",
        )
        mock_service.match.return_value = mock_result

        with patch(
            "comic_identity_engine.jobs.tasks._get_gcd_matching_service",
            return_value=mock_service,
        ):
            row = {
                "Core ComicID": "clz-789",
                "Series": "X-Men",
                "Issue": "1",
                "Cover Year": "1963",
            }
            issue_candidate = MagicMock(
                series_title="X-Men",
                issue_number="1",
            )

            result = _try_gcd_match(row, issue_candidate)

            assert result is None
            mock_service.match.assert_called_once()

    def test_no_match_returns_none(self) -> None:
        """No match (confidence=0) returns None (fallback to resolver)."""
        mock_service = MagicMock()
        mock_result = StrategyResult(
            confidence=MatchConfidence.NO_MATCH,  # value = 0
            gcd_issue_id=None,
            strategy_name="",
        )
        mock_service.match.return_value = mock_result

        with patch(
            "comic_identity_engine.jobs.tasks._get_gcd_matching_service",
            return_value=mock_service,
        ):
            row = {
                "Core ComicID": "clz-999",
                "Series": "Unknown Series",
                "Issue": "999",
            }
            issue_candidate = MagicMock(
                series_title="Unknown Series",
                issue_number="999",
            )

            result = _try_gcd_match(row, issue_candidate)

            assert result is None

    def test_service_unavailable_returns_none(self) -> None:
        """When GCD service is unavailable, returns None (fallback to resolver)."""
        with patch(
            "comic_identity_engine.jobs.tasks._get_gcd_matching_service",
            return_value=None,
        ):
            row = {
                "Core ComicID": "clz-000",
                "Series": "X-Men",
                "Issue": "1",
            }
            issue_candidate = MagicMock()

            result = _try_gcd_match(row, issue_candidate)

            assert result is None

    def test_exception_in_service_returns_none(self) -> None:
        """Exception in GCD service is caught, logged, and returns None."""
        mock_service = MagicMock()
        mock_service.match.side_effect = Exception("Database error")

        with patch(
            "comic_identity_engine.jobs.tasks._get_gcd_matching_service",
            return_value=mock_service,
        ):
            row = {
                "Core ComicID": "clz-err",
                "Series": "X-Men",
                "Issue": "1",
            }
            issue_candidate = MagicMock(
                series_title="X-Men",
                issue_number="1",
            )

            result = _try_gcd_match(row, issue_candidate)

            assert result is None
            mock_service.match.assert_called_once()

    def test_clz_input_built_from_csv_row(self) -> None:
        """CLZInput is built correctly from CSV row data."""
        mock_service = MagicMock()
        mock_result = StrategyResult(
            confidence=MatchConfidence.EXACT_ONE_ISSUE,
            gcd_issue_id=11111,
            strategy_name="exact_one_issue",
        )
        mock_service.match.return_value = mock_result

        with patch(
            "comic_identity_engine.jobs.tasks._get_gcd_matching_service",
            return_value=mock_service,
        ):
            row = {
                "Core ComicID": "clz-111",
                "Series": "The Amazing Spider-Man",
                "Series Group": "",
                "Issue": "1",
                "Issue Nr": "1",
                "Cover Year": "1963",
                "Barcode": "",
                "Publisher": "Marvel",
            }
            issue_candidate = MagicMock(
                series_title="The Amazing Spider-Man",
                issue_number="1",
            )

            result = _try_gcd_match(row, issue_candidate)

            assert result is not None
            # Verify CLZInput was built by checking match was called
            mock_service.match.assert_called_once()
            call_args = mock_service.match.call_args
            clz_input = call_args[0][0]
            assert clz_input.series_name == "The Amazing Spider-Man"
            assert clz_input.issue_nr == "1"
