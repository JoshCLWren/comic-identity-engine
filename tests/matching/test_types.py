"""Tests for GCD matching types."""

from comic_identity_engine.matching.types import CLZInput


class TestCLZInputFromCsvRow:
    def test_parses_basic_row(self) -> None:
        row = {
            "Core ComicID": "123",
            "Series": "X-Men",
            "Series Group": "X-Men",
            "Issue": "1",
            "Issue Nr": "1",
            "Cover Year": "1991",
            "Barcode": "75960609663900411",
            "Publisher": "Marvel Comics",
        }
        clz = CLZInput.from_csv_row(row)
        assert clz.comic_id == "123"
        assert clz.series_name == "X-Men"
        assert clz.issue_nr == "1"
        assert clz.issue_full == "1"
        assert clz.year == 1991
        assert clz.barcode == "75960609663900411"
        assert clz.publisher == "Marvel Comics"
        assert clz.publisher_normalized == "marvel"

    def test_normalizes_series_name(self) -> None:
        row = {
            "Core ComicID": "123",
            "Series": "X-Men, Vol. 1",
            "Series Group": "X-Men",
            "Issue": "1",
            "Issue Nr": "1",
            "Cover Year": "1991",
            "Barcode": "",
            "Publisher": "Marvel Comics",
        }
        clz = CLZInput.from_csv_row(row)
        assert clz.series_name == "X-Men, Vol. 1"
        assert clz.series_name_normalized == "X-Men"

    def test_handles_empty_series_group(self) -> None:
        row = {
            "Core ComicID": "123",
            "Series": "X-Men",
            "Series Group": "",
            "Issue": "1",
            "Issue Nr": "1",
            "Cover Year": "1991",
            "Barcode": "",
            "Publisher": "Marvel Comics",
        }
        clz = CLZInput.from_csv_row(row)
        assert clz.series_group == ""
        assert clz.series_group_normalized == ""

    def test_handles_missing_fields(self) -> None:
        row = {}
        clz = CLZInput.from_csv_row(row)
        assert clz.comic_id == ""
        assert clz.series_name == ""
        assert clz.issue_nr == "1"
        assert clz.year is None

    def test_handles_out_of_range_year(self) -> None:
        row = {
            "Core ComicID": "123",
            "Series": "X-Men",
            "Series Group": "X-Men",
            "Issue": "1",
            "Issue Nr": "1",
            "Cover Year": "1800",
            "Barcode": "",
            "Publisher": "Marvel Comics",
        }
        clz = CLZInput.from_csv_row(row)
        assert clz.year is None

    def test_handles_integer_year(self) -> None:
        row = {
            "Core ComicID": "123",
            "Series": "X-Men",
            "Series Group": "X-Men",
            "Issue": "1",
            "Issue Nr": "1",
            "Cover Year": 1991,
            "Barcode": "",
            "Publisher": "Marvel Comics",
        }
        clz = CLZInput.from_csv_row(row)
        assert clz.year == 1991


class TestCLZInputParseYear:
    def test_parses_valid_year(self) -> None:
        assert CLZInput._parse_year("1991") == 1991

    def test_parses_integer_year(self) -> None:
        assert CLZInput._parse_year(1991) == 1991

    def test_returns_none_for_none(self) -> None:
        assert CLZInput._parse_year(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert CLZInput._parse_year("") is None

    def test_returns_none_for_year_too_low(self) -> None:
        assert CLZInput._parse_year("1900") is None

    def test_returns_none_for_year_too_high(self) -> None:
        assert CLZInput._parse_year("2030") is None

    def test_returns_none_for_non_numeric(self) -> None:
        assert CLZInput._parse_year("nineteen ninety-one") is None

    def test_parses_float_string(self) -> None:
        assert CLZInput._parse_year("1991.0") == 1991


class TestStrategyResult:
    def test_is_match_returns_true_for_confident_match(self) -> None:
        from comic_identity_engine.matching.types import StrategyResult, MatchConfidence

        result = StrategyResult(
            confidence=MatchConfidence.BARCODE,
            gcd_issue_id=42,
        )
        assert result.is_match() is True

    def test_is_match_returns_false_for_no_match(self) -> None:
        from comic_identity_engine.matching.types import StrategyResult, MatchConfidence

        result = StrategyResult(
            confidence=MatchConfidence.NO_MATCH,
            gcd_issue_id=None,
        )
        assert result.is_match() is False

    def test_is_match_returns_false_when_issue_id_is_none(self) -> None:
        from comic_identity_engine.matching.types import StrategyResult, MatchConfidence

        result = StrategyResult(
            confidence=MatchConfidence.EXACT_ONE_ISSUE,
            gcd_issue_id=None,
        )
        assert result.is_match() is False

    def test_is_match_returns_true_for_series_only_match(self) -> None:
        from comic_identity_engine.matching.types import StrategyResult, MatchConfidence

        result = StrategyResult(
            confidence=MatchConfidence.EXACT_SERIES,
            gcd_issue_id=None,
            gcd_series_id=42,
        )
        assert result.is_match() is False
