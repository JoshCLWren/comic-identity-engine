"""Tests for GCDMatchingService strategy selection."""

from __future__ import annotations

from unittest.mock import MagicMock

from comic_identity_engine.matching.service import GCDMatchingService
from comic_identity_engine.matching.types import (
    CLZInput,
    MatchConfidence,
    StrategyResult,
)


def make_clz(
    series_name: str = "Amazing Spider-Man",
    series_group: str = "",
    issue_nr: str = "1",
    year: int | None = 1990,
    barcode: str = "",
    publisher: str = "marvel",
) -> CLZInput:
    """Build a CLZInput with sensible defaults for testing."""
    from comic_identity_engine.matching.normalizers import (
        normalize_publisher,
        normalize_series_name,
        normalize_series_name_strict,
    )

    series_group = series_group or series_name
    return CLZInput(
        comic_id="test-1",
        series_name=series_name,
        series_name_normalized=normalize_series_name(series_name),
        series_name_strict=normalize_series_name_strict(series_name),
        series_group=series_group,
        series_group_normalized=normalize_series_name(series_group),
        series_group_strict=normalize_series_name_strict(series_group),
        issue_nr=issue_nr,
        issue_full=issue_nr,
        year=year,
        barcode=barcode,
        cover_year=year,
        publisher=publisher,
        publisher_normalized=normalize_publisher(publisher),
    )


def make_adapter(
    series_exact: dict[str, list[dict]] | None = None,
    issues: dict[tuple[int, str], tuple[int, str]] | None = None,
    cover_years: dict[tuple[int, str], int] | None = None,
    barcode_ids: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mock GCDLocalAdapter."""
    adapter = MagicMock()
    adapter.iter_series_groups.return_value = []
    adapter.get_series_info.return_value = {}

    series_exact = series_exact or {}
    issues = issues or {}
    cover_years = cover_years or {}
    barcode_ids = barcode_ids or {}

    def find_series_exact(
        name_lower: str, _publisher_normalized: str = ""
    ) -> list[dict]:
        return series_exact.get(name_lower, [])

    def find_issue(series_id: int, issue_nr: str) -> tuple[int, str] | None:
        return issues.get((series_id, issue_nr))

    def get_issue_cover_year(series_id: int, issue_nr: str) -> int | None:
        return cover_years.get((series_id, issue_nr))

    def find_issue_by_barcode(barcode: str) -> int | None:
        return barcode_ids.get(barcode)

    def find_issue_by_barcode_prefix(barcode: str) -> tuple[int, str] | None:
        for bc, bid in barcode_ids.items():
            if bc.startswith(barcode) or barcode.startswith(bc[:13]):
                return (bid, bc)
        return None

    def find_issues_by_number_and_year(
        _issue_nr: str, _year: int
    ) -> list[tuple[int, int]]:
        return []

    adapter.find_series_exact.side_effect = find_series_exact
    adapter.find_issue.side_effect = find_issue
    adapter.get_issue_cover_year.side_effect = get_issue_cover_year
    adapter.find_issue_by_barcode.side_effect = find_issue_by_barcode
    adapter.find_issue_by_barcode_prefix.side_effect = find_issue_by_barcode_prefix
    adapter.find_issues_by_number_and_year.side_effect = find_issues_by_number_and_year
    adapter.find_series_strict.return_value = []

    return adapter


class TestBarcode:
    def test_exact_barcode_wins(self) -> None:
        adapter = make_adapter(barcode_ids={"0123456789012": 42})
        svc = GCDMatchingService(adapter)
        clz = make_clz(barcode="0123456789012")
        result = svc.match(clz)
        assert result.confidence == MatchConfidence.BARCODE
        assert result.gcd_issue_id == 42

    def test_zero_barcode_skipped(self) -> None:
        adapter = make_adapter()
        svc = GCDMatchingService(adapter)
        clz = make_clz(barcode="00000000000000")
        result = svc.match(clz)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestExactOneIssue:
    def test_single_series_single_issue_match(self) -> None:
        series = {
            "id": 10,
            "year_began": 1990,
            "year_ended": 1998,
            "publisher_normalized": "marvel",
        }
        adapter = make_adapter(
            series_exact={"amazing spider-man": [series]},
            issues={(10, "1"): (99, "canonical")},
            cover_years={(10, "1"): 1990},
        )
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Amazing Spider-Man", issue_nr="1", year=1990)
        result = svc.match(clz)
        assert result.confidence == MatchConfidence.EXACT_ONE_ISSUE
        assert result.gcd_issue_id == 99
        assert result.strategy_name == "exact_one_issue"

    def test_vol_suffix_stripped_for_lookup(self) -> None:
        """CLZ 'Amazing Spider-Man, Vol. 1' should match GCD 'amazing spider-man'."""
        series = {
            "id": 10,
            "year_began": 1990,
            "year_ended": 1998,
            "publisher_normalized": "marvel",
        }
        adapter = make_adapter(
            series_exact={"amazing spider-man": [series]},
            issues={(10, "1"): (99, "canonical")},
            cover_years={(10, "1"): 1990},
        )
        svc = GCDMatchingService(adapter)
        clz = make_clz(
            series_name="Amazing Spider-Man, Vol. 1", issue_nr="1", year=1990
        )
        result = svc.match(clz)
        assert result.confidence == MatchConfidence.EXACT_ONE_ISSUE
        assert result.gcd_issue_id == 99

    def test_no_match_when_multiple_series(self) -> None:
        s1 = {
            "id": 10,
            "year_began": 1963,
            "year_ended": 1996,
            "publisher_normalized": "marvel",
        }
        s2 = {
            "id": 11,
            "year_began": 1999,
            "year_ended": 2012,
            "publisher_normalized": "marvel",
        }
        adapter = make_adapter(
            series_exact={"amazing spider-man": [s1, s2]},
            issues={(10, "1"): (99, "canonical"), (11, "1"): (100, "canonical")},
        )
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Amazing Spider-Man", issue_nr="1", year=None)
        result = svc.match(clz)
        # Two matching series without a year → can't resolve to EXACT_ONE_ISSUE
        assert result.confidence != MatchConfidence.EXACT_ONE_ISSUE


class TestExactClosestYear:
    def test_picks_closest_year_from_multiple_series(self) -> None:
        s1 = {
            "id": 10,
            "year_began": 1963,
            "year_ended": 1996,
            "publisher_normalized": "marvel",
        }
        s2 = {
            "id": 11,
            "year_began": 1999,
            "year_ended": 2012,
            "publisher_normalized": "marvel",
        }
        adapter = make_adapter(
            series_exact={"amazing spider-man": [s1, s2]},
            issues={(10, "1"): (99, "canonical"), (11, "1"): (100, "canonical")},
            cover_years={(10, "1"): 1966, (11, "1"): 2001},
        )
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Amazing Spider-Man", issue_nr="1", year=2000)
        result = svc.match(clz)
        assert result.confidence == MatchConfidence.EXACT_CLOSEST_YEAR
        assert result.gcd_issue_id == 100  # 2001 is closer to 2000 than 1966


class TestGroupNameStrategy:
    def test_group_name_used_when_differs(self) -> None:
        """Series Group 'X-Men' should match GCD when Series is 'Uncanny X-Men'."""
        series = {
            "id": 20,
            "year_began": 1963,
            "year_ended": None,
            "publisher_normalized": "marvel",
        }
        adapter = make_adapter(
            series_exact={"x-men": [series]},
            issues={(20, "5"): (200, "canonical")},
            cover_years={(20, "5"): 1992},
        )
        svc = GCDMatchingService(adapter)
        clz = make_clz(
            series_name="Uncanny X-Men",
            series_group="X-Men",
            issue_nr="5",
            year=1992,
        )
        result = svc.match(clz)
        assert result.confidence == MatchConfidence.EXACT_ONE_ISSUE
        assert result.gcd_issue_id == 200
        assert "group" in result.strategy_name

    def test_group_not_used_when_same_as_series(self) -> None:
        series = {
            "id": 20,
            "year_began": 1963,
            "year_ended": None,
            "publisher_normalized": "marvel",
        }
        adapter = make_adapter(
            series_exact={"x-men": [series]},
            issues={(20, "5"): (200, "canonical")},
            cover_years={(20, "5"): 1992},
        )
        svc = GCDMatchingService(adapter)
        # Series == Group, so group strategy should not add "group" to strategy name
        clz = make_clz(
            series_name="X-Men", series_group="X-Men", issue_nr="5", year=1992
        )
        result = svc.match(clz)
        assert result.confidence == MatchConfidence.EXACT_ONE_ISSUE
        assert "group" not in result.strategy_name


class TestYearGapRetry:
    def test_prefers_series_name_when_closer_year(self) -> None:
        """If group match has large year gap but series_name has closer year, use series_name."""
        group_series = {
            "id": 10,
            "year_began": 1963,
            "year_ended": 1996,
            "publisher_normalized": "marvel",
        }
        name_series = {
            "id": 11,
            "year_began": 1991,
            "year_ended": 2001,
            "publisher_normalized": "marvel",
        }

        def find_series_exact(name_lower: str, _pub: str = "") -> list[dict]:
            if name_lower == "x-men":
                return [group_series]
            if name_lower == "uncanny x-men":
                return [name_series]
            return []

        adapter = MagicMock()
        adapter._series_map = {}
        adapter._series_id_to_info = {}

        def find_issue_for_group(
            series_id: int, issue_nr: str
        ) -> tuple[int, str] | None:
            return (100 + series_id, "canonical") if issue_nr == "5" else None

        def get_cover_year_for_group(series_id: int, _issue_nr: str) -> int | None:
            return 1970 if series_id == 10 else 1992

        adapter.find_series_exact.side_effect = find_series_exact
        adapter.find_issue.side_effect = find_issue_for_group
        adapter.get_issue_cover_year.side_effect = get_cover_year_for_group
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_issues_by_number_and_year.return_value = []
        adapter.find_series_strict.return_value = []

        svc = GCDMatchingService(adapter)
        clz = make_clz(
            series_name="Uncanny X-Men",
            series_group="X-Men",
            issue_nr="5",
            year=1992,
        )
        result = svc.match(clz)
        # Group result year=1970, gap=22. Series_name result year=1992, gap=0. Should prefer series_name.
        assert result.gcd_series_id == 11
        assert "group" not in result.strategy_name


class TestGroupYearGapRejection:
    def test_group_match_rejected_when_large_year_gap(self) -> None:
        """Group 'Justice League' matches GCD omnibus (cover_year=2014), CLZ year=1989.
        Gap=25 > GROUP_YEAR_GAP_MAX=15. Series name finds no match. Result: NO_MATCH.
        """
        group_series = {
            "id": 50,
            "year_began": 1987,
            "year_ended": None,
            "publisher_normalized": "dc",
        }

        def find_series_exact(name_lower: str, _pub: str = "") -> list[dict]:
            if name_lower == "justice league":
                return [group_series]
            if name_lower == "justice league international":
                return []
            return []

        adapter = MagicMock()
        adapter._series_map = {}
        adapter._series_id_to_info = {}

        def find_issue(series_id: int, issue_nr: str) -> tuple[int, str] | None:
            if series_id == 50 and issue_nr == "32":
                return (500, "canonical")
            return None

        def get_issue_cover_year(series_id: int, _issue_nr: str) -> int | None:
            if series_id == 50:
                return 2014
            return None

        adapter.find_series_exact.side_effect = find_series_exact
        adapter.find_issue.side_effect = find_issue
        adapter.get_issue_cover_year.side_effect = get_issue_cover_year
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_issues_by_number_and_year.return_value = []
        adapter.find_series_strict.return_value = []

        svc = GCDMatchingService(adapter)
        clz = make_clz(
            series_name="Justice League International",
            series_group="Justice League",
            issue_nr="32",
            year=1989,
            publisher="dc",
        )
        result = svc.match(clz)
        assert result.confidence == MatchConfidence.NO_MATCH
        assert not result.is_match()

    def test_group_match_kept_when_small_year_gap(self) -> None:
        """Group 'Justice League' matches GCD series with cover_year=1990, CLZ year=1989.
        Gap=1 <= GROUP_YEAR_GAP_MAX=15. Should return EXACT_ONE_ISSUE with the group result.
        """
        group_series = {
            "id": 50,
            "year_began": 1987,
            "year_ended": None,
            "publisher_normalized": "dc",
        }

        def find_series_exact(name_lower: str, _pub: str = "") -> list[dict]:
            if name_lower == "justice league":
                return [group_series]
            if name_lower == "justice league international":
                return []
            return []

        adapter = MagicMock()
        adapter._series_map = {}
        adapter._series_id_to_info = {}

        def find_issue(series_id: int, issue_nr: str) -> tuple[int, str] | None:
            if series_id == 50 and issue_nr == "32":
                return (500, "canonical")
            return None

        def get_issue_cover_year(series_id: int, _issue_nr: str) -> int | None:
            if series_id == 50:
                return 1990
            return None

        adapter.find_series_exact.side_effect = find_series_exact
        adapter.find_issue.side_effect = find_issue
        adapter.get_issue_cover_year.side_effect = get_issue_cover_year
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_issues_by_number_and_year.return_value = []
        adapter.find_series_strict.return_value = []

        svc = GCDMatchingService(adapter)
        clz = make_clz(
            series_name="Justice League International",
            series_group="Justice League",
            issue_nr="32",
            year=1989,
            publisher="dc",
        )
        result = svc.match(clz)
        assert result.confidence == MatchConfidence.EXACT_ONE_ISSUE
        assert result.gcd_issue_id == 500
        assert "group" in (result.strategy_name or "")

    def test_group_match_replaced_by_series_name_when_gap_under_threshold(self) -> None:
        """Group match has year gap=10 (under GROUP_YEAR_GAP_MAX=15, not rejected by new guard).
        Series_name match has gap=1. Existing year-gap retry (threshold=4) should prefer series_name.
        """
        group_series = {
            "id": 60,
            "year_began": 1987,
            "year_ended": None,
            "publisher_normalized": "dc",
        }
        name_series = {
            "id": 61,
            "year_began": 1988,
            "year_ended": 2004,
            "publisher_normalized": "dc",
        }

        def find_series_exact(name_lower: str, _pub: str = "") -> list[dict]:
            if name_lower == "justice league":
                return [group_series]
            if name_lower == "justice league international":
                return [name_series]
            return []

        adapter = MagicMock()
        adapter._series_map = {}
        adapter._series_id_to_info = {}

        def find_issue(series_id: int, issue_nr: str) -> tuple[int, str] | None:
            if issue_nr == "32":
                if series_id == 60:
                    return (600, "canonical")
                if series_id == 61:
                    return (610, "canonical")
            return None

        def get_issue_cover_year(series_id: int, _issue_nr: str) -> int | None:
            if series_id == 60:
                return 1999  # gap=10 from CLZ year=1989
            if series_id == 61:
                return 1990  # gap=1 from CLZ year=1989
            return None

        adapter.find_series_exact.side_effect = find_series_exact
        adapter.find_issue.side_effect = find_issue
        adapter.get_issue_cover_year.side_effect = get_issue_cover_year
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_issues_by_number_and_year.return_value = []
        adapter.find_series_strict.return_value = []

        svc = GCDMatchingService(adapter)
        clz = make_clz(
            series_name="Justice League International",
            series_group="Justice League",
            issue_nr="32",
            year=1989,
            publisher="dc",
        )
        result = svc.match(clz)
        # Series_name result (gap=1) should win over group result (gap=10)
        assert result.gcd_series_id == 61
        assert "group" not in (result.strategy_name or "")


class TestNoMatch:
    def test_no_match_returns_no_match_confidence(self) -> None:
        adapter = make_adapter()
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Totally Unknown Series")
        result = svc.match(clz)
        assert result.confidence == MatchConfidence.NO_MATCH
        assert not result.is_match()


class TestTryNormalizedSeries:
    def test_normalized_series_match(self) -> None:
        adapter = make_adapter()
        adapter.find_series_strict.return_value = [
            {"id": 42, "name": "X-Men", "publisher_normalized": "marvel"}
        ]
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="X-Men")
        result = svc._try_normalized_series(clz)
        assert result.confidence == MatchConfidence.NORMALIZED_SERIES
        assert result.gcd_series_id == 42
        assert result.strategy_name == "normalized_series"

    def test_normalized_series_no_match(self) -> None:
        adapter = make_adapter()
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Unknown Series XYZ")
        result = svc._try_normalized_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH

    def test_normalized_series_multiple_returns_no_match(self) -> None:
        adapter = make_adapter()
        adapter.find_series_strict.return_value = [
            {"id": 1, "name": "X-Men", "publisher_normalized": "marvel"},
            {"id": 2, "name": "X-Men", "publisher_normalized": "marvel"},
        ]
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="X-Men")
        result = svc._try_normalized_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestTryWordOrderSeries:
    def test_word_order_series_match(self) -> None:
        adapter = make_adapter()
        adapter.iter_series_groups.return_value = [
            [{"id": 55, "name": "X-Men Classic", "publisher_normalized": "marvel"}]
        ]
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Classic X-Men")
        result = svc._try_word_order_series(clz)
        assert result.confidence == MatchConfidence.WORD_ORDER_SERIES
        assert result.gcd_series_id == 55

    def test_word_order_series_no_match(self) -> None:
        adapter = make_adapter()
        adapter.iter_series_groups.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Classic X-Men")
        result = svc._try_word_order_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH

    def test_word_order_series_single_word_returns_no_match(self) -> None:
        adapter = make_adapter()
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="XMen")
        result = svc._try_word_order_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestTryColonCommaSeries:
    def test_colon_comma_series_match(self) -> None:
        adapter = MagicMock()
        adapter.find_series_exact.side_effect = lambda n, p=0: (
            [{"id": 77, "name": "Batman, Year One", "publisher_normalized": "dc"}]
            if n == "batman, year one"
            else []
        )
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_issues_by_number_and_year.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Batman: Year One", publisher="dc")
        result = svc._try_colon_comma_series(clz)
        assert result.confidence == MatchConfidence.COLON_COMMA_SERIES
        assert result.gcd_series_id == 77
        assert "colon_comma" in result.strategy_name

    def test_colon_comma_series_no_match(self) -> None:
        adapter = make_adapter()
        adapter.find_series_exact.side_effect = lambda n, p=0: [] if ":" in n else []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="X-Men: Volume 1")
        result = svc._try_colon_comma_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH

    def test_colon_comma_series_no_colon_returns_no_match(self) -> None:
        adapter = make_adapter()
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="X-Men")
        result = svc._try_colon_comma_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestTryArticleSeries:
    def test_article_series_match_with_issue(self) -> None:
        adapter = MagicMock()
        adapter.find_series_exact.side_effect = lambda n, p=0: (
            [{"id": 88, "name": "Amazing Spider-Man", "publisher_normalized": "marvel"}]
            if n == "amazing spider-man"
            else []
        )
        adapter.find_issue.return_value = (880, "canonical")
        adapter.get_issue_cover_year.return_value = 1990
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_issues_by_number_and_year.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="The Amazing Spider-Man", issue_nr="1", year=1990)
        result = svc._try_article_series(clz)
        assert result.confidence == MatchConfidence.EXACT_ONE_ISSUE
        assert result.gcd_issue_id == 880

    def test_article_series_match_without_issue(self) -> None:
        adapter = MagicMock()
        adapter.find_series_exact.side_effect = lambda n, p=0: (
            [{"id": 88, "name": "Amazing Spider-Man", "publisher_normalized": "marvel"}]
            if n == "amazing spider-man"
            else []
        )
        adapter.find_issue.return_value = None
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_issues_by_number_and_year.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="The Amazing Spider-Man", issue_nr="999", year=1990)
        result = svc._try_article_series(clz)
        assert result.confidence == MatchConfidence.ARTICLE_SERIES
        assert result.gcd_series_id == 88

    def test_article_series_no_match(self) -> None:
        adapter = MagicMock()
        adapter.find_series_exact.side_effect = lambda n, p=0: []
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_issues_by_number_and_year.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="The Amazing Spider-Man")
        result = svc._try_article_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestTrySubstringSeries:
    def test_substring_series_match(self) -> None:
        adapter = make_adapter()
        adapter.iter_series_groups.return_value = [
            [{"id": 99, "name": "Amazing Spider-Man", "publisher_normalized": "marvel"}]
        ]
        adapter.get_issue_cover_year.return_value = 1990
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Amazing Spider-Man", issue_nr="1", year=1990)
        result = svc._try_substring_series(clz)
        assert result.confidence == MatchConfidence.SUBSTRING_SERIES
        assert result.gcd_series_id == 99

    def test_substring_series_no_match(self) -> None:
        adapter = make_adapter()
        adapter.iter_series_groups.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Amazing Spider-Man")
        result = svc._try_substring_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH

    def test_substring_series_short_name_returns_no_match(self) -> None:
        adapter = make_adapter()
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="X")
        result = svc._try_substring_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestTryReverseLookup:
    def test_reverse_lookup_unique_series(self) -> None:
        adapter = MagicMock()
        adapter.find_issues_by_number_and_year.side_effect = lambda n, y: [(42, 420)]
        adapter.get_series_info.return_value = {"name": "X-Men"}
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Amazing Spider-Man", issue_nr="1", year=1990)
        result = svc._try_reverse_lookup(clz)
        assert result.confidence == MatchConfidence.REVERSE_LOOKUP_ONE
        assert result.gcd_issue_id == 420
        assert result.gcd_series_id == 42

    def test_reverse_lookup_publisher_filter(self) -> None:
        adapter = MagicMock()
        adapter.find_issues_by_number_and_year.side_effect = lambda n, y: [
            (1, 100),
            (2, 200),
        ]
        adapter.get_series_info.side_effect = lambda sid: {
            1: {"publisher_normalized": "marvel", "name": "X-Men"},
            2: {"publisher_normalized": "dc", "name": "Batman"},
        }.get(sid, {})
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(
            series_name="Unknown", issue_nr="1", year=1990, publisher="marvel"
        )
        result = svc._try_reverse_lookup(clz)
        assert result.confidence == MatchConfidence.REVERSE_LOOKUP_ONE
        assert result.gcd_series_id == 1

    def test_reverse_lookup_similarity(self) -> None:
        adapter = MagicMock()
        adapter.find_issues_by_number_and_year.side_effect = lambda n, y: [
            (1, 100),
            (2, 200),
        ]
        adapter.get_series_info.side_effect = lambda sid: {
            1: {"name": "Amazing Spider-Man"},
            2: {"name": "Superman"},
        }.get(sid, {})
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Spider-Man", issue_nr="1", year=1990)
        result = svc._try_reverse_lookup(clz)
        assert result.confidence == MatchConfidence.REVERSE_LOOKUP_SIMILARITY
        assert result.gcd_series_id == 1

    def test_reverse_lookup_no_match_no_year(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Unknown", issue_nr="1", year=None)
        result = svc._try_reverse_lookup(clz)
        assert result.confidence == MatchConfidence.NO_MATCH

    def test_reverse_lookup_no_match_no_issues(self) -> None:
        adapter = MagicMock()
        adapter.find_issues_by_number_and_year.side_effect = lambda n, y: []
        adapter.get_series_info.return_value = {}
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Unknown", issue_nr="1", year=1990)
        result = svc._try_reverse_lookup(clz)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestTryVariantFallback:
    def test_variant_fallback_match(self) -> None:
        adapter = MagicMock()
        adapter.find_issue.side_effect = lambda s, n: (555, "canonical")
        adapter.get_issue_cover_year.side_effect = lambda s, n: 1990
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        prior = StrategyResult(
            confidence=MatchConfidence.EXACT_SERIES,
            gcd_series_id=42,
            strategy_name="exact_series",
        )
        clz = make_clz(series_name="X-Men", issue_nr="1", year=1990)
        clz.issue_full = "1AU"
        result = svc._try_variant_fallback(clz, prior)
        assert result.confidence == MatchConfidence.EXACT_ONE_ISSUE
        assert result.gcd_issue_id == 555

    def test_variant_fallback_no_match_digit_only(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        prior = StrategyResult(
            confidence=MatchConfidence.EXACT_SERIES,
            gcd_series_id=42,
            strategy_name="exact_series",
        )
        clz = make_clz(series_name="X-Men", issue_nr="1", year=1990)
        clz.issue_full = "1"
        result = svc._try_variant_fallback(clz, prior)
        assert result.confidence == MatchConfidence.NO_MATCH

    def test_variant_fallback_no_match_letter_only(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        prior = StrategyResult(
            confidence=MatchConfidence.EXACT_SERIES,
            gcd_series_id=42,
            strategy_name="exact_series",
        )
        clz = make_clz(series_name="X-Men", issue_nr="A", year=1990)
        clz.issue_full = "A"
        result = svc._try_variant_fallback(clz, prior)
        assert result.confidence == MatchConfidence.NO_MATCH

    def test_variant_fallback_no_series_id(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        prior = StrategyResult(
            confidence=MatchConfidence.NO_MATCH,
            gcd_series_id=None,
            strategy_name="none",
        )
        clz = make_clz(series_name="X-Men", issue_nr="1", year=1990)
        clz.issue_full = "1AU"
        result = svc._try_variant_fallback(clz, prior)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestSimilarity:
    def test_similarity_exact_match(self) -> None:
        adapter = make_adapter()
        svc = GCDMatchingService(adapter)
        score = svc._similarity("x-men", "x-men")
        assert score == 1.0

    def test_similarity_substring(self) -> None:
        adapter = make_adapter()
        svc = GCDMatchingService(adapter)
        score = svc._similarity("x-men", "x-men classic")
        assert 0.0 < score < 1.0

    def test_similarity_word_overlap(self) -> None:
        adapter = make_adapter()
        svc = GCDMatchingService(adapter)
        score = svc._similarity("amazing spider-man", "spectacular spider-man")
        assert 0.0 < score < 1.0

    def test_similarity_no_overlap(self) -> None:
        adapter = make_adapter()
        svc = GCDMatchingService(adapter)
        score = svc._similarity("x-men", "batman")
        assert score == 0.0


class TestTryBarcodePrefix:
    def test_barcode_prefix_match(self) -> None:
        adapter = MagicMock()
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = (42, "978130294537454499")
        adapter.iter_series_groups.return_value = []
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        result = svc._try_barcode("9781302945374")
        assert result.confidence == MatchConfidence.BARCODE
        assert result.strategy_name == "barcode_prefix"
        assert result.gcd_issue_id == 42

    def test_barcode_no_match(self) -> None:
        adapter = MagicMock()
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.iter_series_groups.return_value = []
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        result = svc._try_barcode("00000000000000")
        assert result.confidence == MatchConfidence.NO_MATCH


class TestMatchVariantFallback:
    def test_match_calls_variant_fallback_when_series_matches_but_no_issue(
        self,
    ) -> None:
        adapter = MagicMock()

        def find_series_exact(name_lower: str, _pub: str = "") -> list[dict]:
            if name_lower == "x-men":
                return [
                    {"id": 10, "year_began": 1991, "publisher_normalized": "marvel"}
                ]
            return []

        def find_issue(series_id: int, issue_nr: str) -> tuple[int, str] | None:
            if series_id == 10 and issue_nr == "999AU":
                return (101, "canonical")
            return None

        adapter.find_series_exact.side_effect = find_series_exact
        adapter.find_issue.side_effect = find_issue
        adapter.get_issue_cover_year.return_value = 1991
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_strict.return_value = []
        adapter.iter_series_groups.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []

        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="X-Men", issue_nr="999", year=1991)
        clz.issue_full = "999AU"
        result = svc.match(clz)
        assert result.gcd_series_id == 10
        assert result.gcd_issue_id == 101
        assert "variant" in (result.strategy_name or "")


class TestMatchYearGapRetryReplaces:
    def test_year_gap_retry_replaces_when_series_name_closer(self) -> None:
        group_series = {
            "id": 10,
            "year_began": 1963,
            "year_ended": 1996,
            "publisher_normalized": "marvel",
        }
        name_series = {
            "id": 11,
            "year_began": 1991,
            "year_ended": 2001,
            "publisher_normalized": "marvel",
        }

        def find_series_exact(name_lower: str, _pub: str = "") -> list[dict]:
            if name_lower == "x-men":
                return [group_series]
            if name_lower == "uncanny x-men":
                return [name_series]
            return []

        adapter = MagicMock()
        adapter._series_map = {}
        adapter._series_id_to_info = {}

        def find_issue(series_id: int, issue_nr: str) -> tuple[int, str] | None:
            return (100 + series_id, "canonical") if issue_nr == "1" else None

        def get_cover_year(series_id: int, _issue_nr: str) -> int | None:
            if series_id == 10:
                return 1966
            if series_id == 11:
                return 1991
            return None

        adapter.find_series_exact.side_effect = find_series_exact
        adapter.find_issue.side_effect = find_issue
        adapter.get_issue_cover_year.side_effect = get_cover_year
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_issues_by_number_and_year.return_value = []
        adapter.find_series_strict.return_value = []

        svc = GCDMatchingService(adapter)
        clz = make_clz(
            series_name="Uncanny X-Men",
            series_group="X-Men",
            issue_nr="1",
            year=1991,
        )
        result = svc.match(clz)
        assert result.gcd_series_id == 11
        assert "group" not in (result.strategy_name or "")


class TestTryWordOrderPublisherFilter:
    def test_word_order_skips_wrong_publisher(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = [
            [{"id": 55, "name": "X-Men Classic", "publisher_normalized": "dc"}]
        ]
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Classic X-Men", publisher="marvel")
        result = svc._try_word_order_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestTrySubstringSeriesPaths:
    def test_substring_strips_the_prefix(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = [
            [{"id": 99, "name": "Amazing Spider-Man", "publisher_normalized": "marvel"}]
        ]
        adapter.get_issue_cover_year.return_value = 1990
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="The Amazing Spider-Man", issue_nr="1", year=1990)
        result = svc._try_substring_series(clz)
        assert result.confidence == MatchConfidence.SUBSTRING_SERIES

    def test_substring_skips_wrong_publisher(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = [
            [{"id": 99, "name": "Amazing Spider-Man", "publisher_normalized": "dc"}]
        ]
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Amazing Spider-Man", publisher="marvel")
        result = svc._try_substring_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH

    def test_substring_filters_by_year(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = [
            [
                {
                    "id": 99,
                    "name": "Amazing Spider-Man",
                    "publisher_normalized": "marvel",
                }
            ],
            [
                {
                    "id": 100,
                    "name": "Amazing Spider-Man Vol. 2",
                    "publisher_normalized": "marvel",
                }
            ],
        ]

        def get_cover_year(sid: int, _inr: str) -> int | None:
            if sid == 99:
                return 1984
            if sid == 100:
                return 1990
            return None

        adapter.get_issue_cover_year.side_effect = get_cover_year
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Amazing Spider-Man", issue_nr="1", year=1990)
        result = svc._try_substring_series(clz)
        assert result.gcd_series_id == 100

    def test_substring_uses_filtered_when_available(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = [
            [{"id": 99, "name": "Amazing Spider-Man", "publisher_normalized": "marvel"}]
        ]

        def get_cover_year(sid: int, _inr: str) -> int | None:
            if sid == 99:
                return 1990
            return None

        adapter.get_issue_cover_year.side_effect = get_cover_year
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Amazing Spider-Man", issue_nr="1", year=1990)
        result = svc._try_substring_series(clz)
        assert result.confidence == MatchConfidence.SUBSTRING_SERIES
        assert result.gcd_series_id == 99


class TestTryColonCommaSeriesMultiple:
    def test_colon_comma_multiple_returns_no_match(self) -> None:
        adapter = MagicMock()
        adapter.find_series_exact.side_effect = lambda n, p=0: (
            [{"id": 1, "name": "Batman, Year One", "publisher_normalized": "dc"}] * 2
        )
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Batman: Year One", publisher="dc")
        result = svc._try_colon_comma_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestTryArticleSeriesMultiple:
    def test_article_multiple_returns_no_match(self) -> None:
        adapter = MagicMock()
        adapter.find_series_exact.side_effect = lambda n, p=0: (
            [{"id": 88, "name": "Amazing Spider-Man", "publisher_normalized": "marvel"}]
            * 2
        )
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="The Amazing Spider-Man")
        result = svc._try_article_series(clz)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestTryReverseLookupMultipleSeriesNoMatch:
    def test_reverse_multiple_no_similarity_match(self) -> None:
        adapter = MagicMock()
        adapter.find_issues_by_number_and_year.side_effect = lambda n, y: [
            (1, 100),
            (2, 200),
        ]
        adapter.get_series_info.side_effect = lambda sid: {
            1: {"name": "Batman"},
            2: {"name": "Superman"},
        }.get(sid, {})
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        svc = GCDMatchingService(adapter)
        clz = make_clz(series_name="Spider-Man", issue_nr="1", year=1990)
        result = svc._try_reverse_lookup(clz)
        assert result.confidence == MatchConfidence.NO_MATCH


class TestTryVariantFallbackNoMatch:
    def test_variant_empty_issue_full(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        prior = StrategyResult(
            confidence=MatchConfidence.EXACT_SERIES,
            gcd_series_id=42,
            strategy_name="exact_series",
        )
        clz = make_clz(series_name="X-Men", issue_nr="1", year=1990)
        clz.issue_full = ""
        result = svc._try_variant_fallback(clz, prior)
        assert result.confidence == MatchConfidence.NO_MATCH

    def test_variant_letter_only(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        prior = StrategyResult(
            confidence=MatchConfidence.EXACT_SERIES,
            gcd_series_id=42,
            strategy_name="exact_series",
        )
        clz = make_clz(series_name="X-Men", issue_nr="A", year=1990)
        clz.issue_full = "A"
        result = svc._try_variant_fallback(clz, prior)
        assert result.confidence == MatchConfidence.NO_MATCH

    def test_variant_no_series_id(self) -> None:
        adapter = MagicMock()
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        prior = StrategyResult(
            confidence=MatchConfidence.NO_MATCH,
            gcd_series_id=None,
            strategy_name="none",
        )
        clz = make_clz(series_name="X-Men", issue_nr="1", year=1990)
        clz.issue_full = "1AU"
        result = svc._try_variant_fallback(clz, prior)
        assert result.confidence == MatchConfidence.NO_MATCH

    def test_variant_issue_not_found(self) -> None:
        adapter = MagicMock()
        adapter.find_issue.return_value = None
        adapter.iter_series_groups.return_value = []
        adapter.find_issue_by_barcode.return_value = None
        adapter.find_issue_by_barcode_prefix.return_value = None
        adapter.find_series_exact.return_value = []
        adapter.find_series_strict.return_value = []
        adapter.find_issues_by_number_and_year.return_value = []
        svc = GCDMatchingService(adapter)
        prior = StrategyResult(
            confidence=MatchConfidence.EXACT_SERIES,
            gcd_series_id=42,
            strategy_name="exact_series",
        )
        clz = make_clz(series_name="X-Men", issue_nr="1", year=1990)
        clz.issue_full = "1AU"
        result = svc._try_variant_fallback(clz, prior)
        assert result.confidence == MatchConfidence.NO_MATCH
