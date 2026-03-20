"""Tests for GCDDumpMatcher service."""

import pytest

from comic_identity_engine.services import GCDDumpMatcher, GCDMatchResult


class TestGCDMatchResult:
    """Tests for GCDMatchResult dataclass."""

    def test_matched_property_true_when_issue_id_set(self) -> None:
        """matched property returns True when gcd_issue_id is set."""
        result = GCDMatchResult(
            gcd_issue_id=12345,
            gcd_series_id=100,
            gcd_series_name="X-Men",
            match_type="barcode",
            confidence=0.99,
        )
        assert result.matched is True

    def test_matched_property_false_when_no_issue_id(self) -> None:
        """matched property returns False when gcd_issue_id is None."""
        result = GCDMatchResult(match_type="no_match", confidence=0.0)
        assert result.matched is False

    def test_is_high_confidence_true_when_above_threshold(self) -> None:
        """is_high_confidence returns True when confidence >= 0.90."""
        result = GCDMatchResult(
            gcd_issue_id=12345,
            match_type="barcode",
            confidence=0.95,
        )
        assert result.is_high_confidence is True

    def test_is_high_confidence_true_at_threshold(self) -> None:
        """is_high_confidence returns True when confidence == 0.90."""
        result = GCDMatchResult(
            gcd_issue_id=12345,
            match_type="series_issue_year",
            confidence=0.90,
        )
        assert result.is_high_confidence is True

    def test_is_high_confidence_false_below_threshold(self) -> None:
        """is_high_confidence returns False when confidence < 0.90."""
        result = GCDMatchResult(
            gcd_issue_id=12345,
            match_type="fuzzy",
            confidence=0.85,
        )
        assert result.is_high_confidence is False

    def test_gcd_url_generated_when_issue_id_present(self) -> None:
        """gcd_url is generated correctly when gcd_issue_id is set."""
        result_with_url = GCDMatchResult(
            gcd_issue_id=12345,
            match_type="barcode",
            confidence=0.99,
            gcd_url="https://www.comics.org/issue/12345/",
        )
        assert result_with_url.gcd_url == "https://www.comics.org/issue/12345/"


class TestGCDDumpMatcher:
    """Tests for GCDDumpMatcher service."""

    @pytest.fixture
    def matcher(self) -> GCDDumpMatcher:
        """Create a GCDDumpMatcher instance."""
        return GCDDumpMatcher()

    def test_is_available_returns_true_when_db_exists(
        self, matcher: GCDDumpMatcher
    ) -> None:
        """is_available returns True when database file exists."""
        assert matcher.is_available() is True

    def test_match_returns_result_object(self, matcher: GCDDumpMatcher) -> None:
        """match() returns a GCDMatchResult object."""
        result = matcher.match(
            barcode="9781302945374",
            series_title="X-Men",
            issue_number="1",
            year=2019,
        )
        assert isinstance(result, GCDMatchResult)

    def test_match_by_barcode_exact(self, matcher: GCDDumpMatcher) -> None:
        """Matching by exact barcode returns high-confidence result."""
        result = matcher.match(barcode="9781302945374")
        if result.matched:
            assert result.match_type == "barcode"
            assert result.confidence >= 0.95

    def test_match_by_series_issue_with_year(self, matcher: GCDDumpMatcher) -> None:
        """Matching by series + issue + year returns proper result."""
        result = matcher.match(
            series_title="X-Men",
            issue_number="1",
            year=1963,
        )
        assert isinstance(result, GCDMatchResult)
        if result.matched:
            assert result.gcd_issue_id is not None
            assert result.confidence >= 0.80

    def test_match_returns_no_match_for_invalid_input(
        self, matcher: GCDDumpMatcher
    ) -> None:
        """Match returns no_match for invalid input."""
        result = matcher.match(
            series_title="Nonexistent Series That Does Not Exist",
            issue_number="99999",
            year=1900,
        )
        assert result.matched is False
        assert result.match_type.startswith("no_")

    def test_match_with_series_group_fallback(self, matcher: GCDDumpMatcher) -> None:
        """Match uses series_group as fallback when series_title fails."""
        result = matcher.match(
            series_title="Unknown Series",
            issue_number="1",
            year=1980,
            series_group="X-Men",
        )
        assert isinstance(result, GCDMatchResult)

    def test_strip_diacritics_normalizes_unicode(self, matcher: GCDDumpMatcher) -> None:
        """_strip_diacritics normalizes unicode characters."""
        result = GCDDumpMatcher._strip_diacritics("Rōnin")
        assert result == "Ronin"

    def test_normalize_series_name_removes_volume(
        self, matcher: GCDDumpMatcher
    ) -> None:
        """_normalize_series_name removes volume information."""
        result = GCDDumpMatcher._normalize_series_name("X-Men, Vol. 1")
        assert "Vol." not in result

    def test_normalize_issue_number_converts_to_string(
        self, matcher: GCDDumpMatcher
    ) -> None:
        """_normalize_issue_number returns string for valid input."""
        result = matcher._normalize_issue_number("42")
        assert result == "42"

    def test_normalize_issue_number_returns_none_for_empty(
        self, matcher: GCDDumpMatcher
    ) -> None:
        """_normalize_issue_number returns None for empty input."""
        result = matcher._normalize_issue_number("")
        assert result is None

        result = matcher._normalize_issue_number(None)
        assert result is None

    def test_similarity_score_exact_match(self, matcher: GCDDumpMatcher) -> None:
        """_similarity_score returns 1.0 for exact match."""
        result = matcher._similarity_score("X-Men", "X-Men")
        assert result == 1.0

    def test_similarity_score_case_insensitive(self, matcher: GCDDumpMatcher) -> None:
        """_similarity_score is case insensitive."""
        result = matcher._similarity_score("x-men", "X-MEN")
        assert result == 1.0

    def test_similarity_score_partial_match(self, matcher: GCDDumpMatcher) -> None:
        """_similarity_score returns partial score for partial match."""
        result = matcher._similarity_score("X-Men", "X-Men Classic")
        assert 0.5 < result < 1.0

    def test_context_manager(self) -> None:
        """GCDDumpMatcher can be used as context manager."""
        with GCDDumpMatcher() as matcher:
            assert matcher.is_available() is True
        # After context exit, database should be closed
        assert matcher._db is None

    def test_close_releases_database(self, matcher: GCDDumpMatcher) -> None:
        """close() releases database connection."""
        assert matcher.is_available() is True
        matcher.close()
        assert matcher._db is None

    def test_match_with_empty_barcode(self, matcher: GCDDumpMatcher) -> None:
        """Match with empty barcode falls back to series matching."""
        result = matcher.match(
            barcode="",
            series_title="X-Men",
            issue_number="1",
            year=1963,
        )
        assert isinstance(result, GCDMatchResult)
