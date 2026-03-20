"""Integration tests for CLZ import pipeline with GCD matching.

These tests verify the integration between tasks.py and the GCD matching service.
They mock GCDMatchingService to avoid database dependencies.

Covered scenarios:
- High-confidence match (>=90) → returns GCD result for downstream processing
- Low-confidence match (<90) → falls back to IdentityResolver
- GCDMatchingService raises exception → falls back gracefully, logs warning
- Adapter unavailable (db not found) → singleton is None, fallback is silent
- CLZInput construction from CSV row data
- Confidence threshold boundary behavior
"""

from unittest.mock import MagicMock, patch

import pytest

from comic_identity_engine.jobs.tasks import (
    _get_gcd_matching_service,
    _try_gcd_match,
)
from comic_identity_engine.matching.types import MatchConfidence, StrategyResult


SAMPLE_CSV_ROW = {
    "Core ComicID": "clz-12345",
    "Series": "Justice League: Another Nail",
    "Series Group": "Justice League",
    "Issue": "2",
    "Issue Nr": "2",
    "Cover Year": "2004",
    "Barcode": "76194123774900211",
    "Publisher": "DC Comics",
}


@pytest.fixture
def sample_csv_row():
    """Sample CLZ CSV row for testing."""
    return SAMPLE_CSV_ROW.copy()


@pytest.fixture
def mock_issue_candidate():
    """Mock CLZ issue candidate."""
    candidate = MagicMock()
    candidate.series_title = "Justice League: Another Nail"
    candidate.issue_number = "2"
    candidate.series_start_year = 2004
    candidate.publisher = "DC Comics"
    candidate.source_issue_id = "clz-12345"
    candidate.source_series_id = None
    candidate.upc = "76194123774900211"
    candidate.cover_date = "Aug 2004"
    candidate.variant_suffix = None
    candidate.variant_name = None
    return candidate


class TestGCDMatchingServiceSingleton:
    """Tests for GCD matching service singleton behavior."""

    def setup_method(self):
        """Reset singleton before each test."""
        import comic_identity_engine.jobs.tasks as tasks_module

        tasks_module._GCD_MATCHING_SERVICE = None

    def test_singleton_reuse_across_multiple_calls(self):
        """Singleton is reused across multiple _get_gcd_matching_service calls."""
        with patch("comic_identity_engine.jobs.tasks._GCD_MATCHING_SERVICE", None):
            with patch(
                "comic_identity_engine.matching.adapter.GCDLocalAdapter"
            ) as mock_adapter_class:
                with patch(
                    "comic_identity_engine.matching.service.GCDMatchingService"
                ) as mock_service_class:
                    mock_adapter = MagicMock()
                    mock_adapter._loaded = True
                    mock_adapter.series_count = 100000
                    mock_adapter.issue_count = 2000000
                    mock_adapter_class.return_value = mock_adapter

                    mock_service = MagicMock()
                    mock_service_class.return_value = mock_service

                    first = _get_gcd_matching_service()
                    second = _get_gcd_matching_service()
                    third = _get_gcd_matching_service()

                    assert first is second is third
                    mock_adapter_class.assert_called_once()
                    mock_service_class.assert_called_once()

    def test_adapter_unavailable_returns_none(self):
        """When adapter fails to load, singleton is None."""
        with patch("comic_identity_engine.jobs.tasks._GCD_MATCHING_SERVICE", None):
            with patch(
                "comic_identity_engine.matching.adapter.GCDLocalAdapter"
            ) as mock_adapter_class:
                mock_adapter = MagicMock()
                mock_adapter._loaded = False
                mock_adapter_class.return_value = mock_adapter

                result = _get_gcd_matching_service()

                assert result is None
                mock_adapter.load.assert_called_once()
                mock_adapter.close.assert_called_once()


class TestTryGCDMatchIntegration:
    """Integration tests for _try_gcd_match function with various scenarios."""

    def setup_method(self):
        """Reset singleton before each test."""
        import comic_identity_engine.jobs.tasks as tasks_module

        tasks_module._GCD_MATCHING_SERVICE = None

    def test_barcode_match_confidence_100_returns_result(self):
        """Barcode match (confidence=100) returns match dictionary."""
        mock_service = MagicMock()
        mock_result = StrategyResult(
            confidence=MatchConfidence.BARCODE,
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
            mock_service.match.assert_called_once()

    def test_high_confidence_exact_match_returns_result(self):
        """High-confidence EXACT_ONE_ISSUE match (confidence=90) returns match dictionary."""
        mock_service = MagicMock()
        mock_result = StrategyResult(
            confidence=MatchConfidence.EXACT_ONE_ISSUE,
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

    def test_low_confidence_closest_year_returns_none(self):
        """Low-confidence EXACT_CLOSEST_YEAR match (confidence=85) returns None."""
        mock_service = MagicMock()
        mock_result = StrategyResult(
            confidence=MatchConfidence.EXACT_CLOSEST_YEAR,
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

    def test_no_match_returns_none(self):
        """No match (confidence=0) returns None for fallback to resolver."""
        mock_service = MagicMock()
        mock_result = StrategyResult(
            confidence=MatchConfidence.NO_MATCH,
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
            mock_service.match.assert_called_once()

    def test_service_unavailable_returns_none(self):
        """When GCD service is unavailable, returns None for silent fallback."""
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

    def test_exception_returns_none_with_warning_logged(self):
        """Exception in GCD service is caught, logged, returns None."""
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

            with patch("comic_identity_engine.jobs.tasks.logger") as mock_logger:
                result = _try_gcd_match(row, issue_candidate)

            assert result is None
            mock_service.match.assert_called_once()
            mock_logger.warning.assert_called()
            warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
            assert any("GCD matching failed" in c for c in warning_calls)

    def test_clz_input_built_correctly_from_csv_row(self):
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
            mock_service.match.assert_called_once()
            call_args = mock_service.match.call_args
            clz_input = call_args[0][0]
            assert clz_input.series_name == "The Amazing Spider-Man"
            assert clz_input.issue_nr == "1"


class TestGCDMatchConfidenceThresholds:
    """Tests for confidence threshold behavior (>=90 uses GCD, <90 falls back)."""

    def setup_method(self):
        """Reset singleton before each test."""
        import comic_identity_engine.jobs.tasks as tasks_module

        tasks_module._GCD_MATCHING_SERVICE = None

    @pytest.mark.parametrize(
        "confidence_level,expected_result",
        [
            (MatchConfidence.BARCODE, True),  # 100 - uses GCD
            (MatchConfidence.EXACT_ONE_ISSUE, True),  # 90 - uses GCD
            (MatchConfidence.EXACT_CLOSEST_YEAR, False),  # 85 - fallback
            (MatchConfidence.EXACT_SERIES, False),  # 80 - fallback
            (MatchConfidence.NORMALIZED_SERIES, False),  # 75 - fallback
            (MatchConfidence.NO_MATCH, False),  # 0 - fallback
        ],
    )
    def test_confidence_threshold_boundary(self, confidence_level, expected_result):
        """Confidence >= 90 returns GCD result, < 90 returns None."""
        mock_service = MagicMock()
        mock_result = StrategyResult(
            confidence=confidence_level,
            gcd_issue_id=12345 if confidence_level.value > 0 else None,
            strategy_name="test_strategy",
        )
        mock_service.match.return_value = mock_result

        with patch(
            "comic_identity_engine.jobs.tasks._get_gcd_matching_service",
            return_value=mock_service,
        ):
            row = {
                "Core ComicID": "clz-test",
                "Series": "Test Series",
                "Issue": "1",
                "Cover Year": "2020",
            }
            issue_candidate = MagicMock(
                series_title="Test Series",
                issue_number="1",
            )

            result = _try_gcd_match(row, issue_candidate)

            if expected_result:
                assert result is not None
                assert result["gcd_issue_id"] == 12345
            else:
                assert result is None


class TestFullPipelineGCDIntegration:
    """Tests for full pipeline integration scenarios with GCD matching."""

    def setup_method(self):
        """Reset singleton before each test."""
        import comic_identity_engine.jobs.tasks as tasks_module

        tasks_module._GCD_MATCHING_SERVICE = None

    def test_pipeline_with_real_clz_csv_row_format(self):
        """Test GCD matching with actual CLZ CSV row format."""
        csv_row = {
            "Core ComicID": "60070",
            "Series": "Justice League: Another Nail",
            "Series Group": "Justice League",
            "Issue": "2",
            "Issue Nr": "2",
            "Cover Year": "2004",
            "Barcode": "76194123774900211",
            "Publisher": "DC Comics",
        }

        mock_service = MagicMock()
        mock_result = StrategyResult(
            confidence=MatchConfidence.EXACT_ONE_ISSUE,
            gcd_issue_id=12345,
            strategy_name="exact_one_issue",
        )
        mock_service.match.return_value = mock_result

        with patch(
            "comic_identity_engine.jobs.tasks._get_gcd_matching_service",
            return_value=mock_service,
        ):
            issue_candidate = MagicMock(
                series_title="Justice League: Another Nail",
                issue_number="2",
            )

            result = _try_gcd_match(csv_row, issue_candidate)

            assert result is not None
            assert result["gcd_issue_id"] == 12345
            assert result["confidence"] == 90

            call_args = mock_service.match.call_args
            clz_input = call_args[0][0]
            assert clz_input.series_name == "Justice League: Another Nail"
            assert clz_input.issue_nr == "2"
            assert clz_input.comic_id == "60070"
            assert clz_input.barcode == "76194123774900211"
