"""Tests for GCDMatchingService strategy selection."""

from __future__ import annotations

from unittest.mock import MagicMock

from comic_identity_engine.matching.service import GCDMatchingService
from comic_identity_engine.matching.types import CLZInput, MatchConfidence


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
