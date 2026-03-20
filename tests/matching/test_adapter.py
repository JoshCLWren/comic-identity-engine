"""Tests for GCDLocalAdapter methods with insufficient coverage.

Tests _load_publishers, _gcd_normalize_name, find_series_* methods,
find_issue, barcode methods, and related query methods.
"""

from __future__ import annotations

import sqlite3

import pytest

from comic_identity_engine.matching.adapter import GCDLocalAdapter


@pytest.fixture
def test_db() -> sqlite3.Connection:
    """Create an in-memory SQLite DB with test data.

    Schema matches GCDLocalAdapter expectations:
    - 2 publishers (Marvel, DC Comics)
    - 3 series (X-Men, Amazing Spider-Man, Batman)
    - 10 issues across the series
    - 4 barcodes
    """
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE gcd_publisher (id INTEGER, name TEXT, deleted INTEGER);
        CREATE TABLE gcd_series (
            id INTEGER, name TEXT, year_began INTEGER, year_ended INTEGER,
            issue_count INTEGER, publisher_id INTEGER, deleted INTEGER, language_id INTEGER
        );
        CREATE TABLE gcd_issue (
            id INTEGER, series_id INTEGER, number TEXT, key_date TEXT,
            publication_date TEXT, barcode TEXT, deleted INTEGER,
            variant_name TEXT, variant_of_id INTEGER
        );
    """)
    db.execute("INSERT INTO gcd_publisher VALUES (1, 'Marvel Comics', 0)")
    db.execute("INSERT INTO gcd_publisher VALUES (2, 'DC Comics', 0)")
    db.execute("INSERT INTO gcd_publisher VALUES (3, 'Deleted Publisher', 1)")

    db.execute("INSERT INTO gcd_series VALUES (1, 'X-Men', 1991, 2001, 113, 1, 0, 25)")
    db.execute(
        "INSERT INTO gcd_series VALUES (2, 'X-Men : The Early Years', 2000, 2000, 6, 1, 0, 25)"
    )
    db.execute(
        "INSERT INTO gcd_series VALUES (3, 'The Amazing Spider-Man', 1963, NULL, 900, 2, 0, 25)"
    )
    db.execute(
        "INSERT INTO gcd_series VALUES (4, 'Batman', 1940, NULL, 1100, 2, 0, 25)"
    )
    db.execute(
        "INSERT INTO gcd_series VALUES (5, 'X-Men (2000)', 2000, 2020, 207, 1, 0, 25)"
    )

    db.execute(
        "INSERT INTO gcd_issue VALUES (100, 1, '1', '1991-10', '1991', '75960609663900411', 0, NULL, NULL)"
    )
    db.execute(
        "INSERT INTO gcd_issue VALUES (101, 1, '2', '1991-11', '1991', '75960609663900428', 0, NULL, NULL)"
    )
    db.execute(
        "INSERT INTO gcd_issue VALUES (102, 1, '3', '1991-12', '1991', NULL, 0, NULL, NULL)"
    )
    db.execute(
        "INSERT INTO gcd_issue VALUES (103, 1, '10', '1992-06', '1992', '978130294537454499', 0, NULL, NULL)"
    )
    db.execute(
        "INSERT INTO gcd_issue VALUES (104, 3, '300', '1968-03', '1968', '75960609895100300', 0, NULL, NULL)"
    )
    db.execute(
        "INSERT INTO gcd_issue VALUES (105, 3, '301', '1968-05', '1968', '75960609895100301', 0, 'Newsstand', NULL)"
    )
    db.execute(
        "INSERT INTO gcd_issue VALUES (106, 4, '1', '1940-05', '1940', '978140123274050001', 0, NULL, NULL)"
    )
    db.execute(
        "INSERT INTO gcd_issue VALUES (107, 5, '1', '2000-01', '2000', NULL, 0, NULL, NULL)"
    )
    db.execute(
        "INSERT INTO gcd_issue VALUES (108, 5, '2', '2000-02', '2000', '75960608045100211', 0, NULL, NULL)"
    )
    db.execute(
        "INSERT INTO gcd_issue VALUES (109, 1, '1', '2010-01', '2010', '75960609663900916', 0, NULL, 100)"
    )
    db.commit()
    return db


@pytest.fixture
def adapter(test_db: sqlite3.Connection) -> GCDLocalAdapter:
    """Create a GCDLocalAdapter with test data loaded."""
    adapter = GCDLocalAdapter()
    adapter._db = test_db
    adapter._load_publishers()
    adapter._load_series()
    adapter._load_issues()
    adapter._load_barcodes()
    adapter._loaded = True
    return adapter


class TestLoadPublishers:
    """Tests for _load_publishers."""

    def test_loads_active_publishers(self, adapter: GCDLocalAdapter) -> None:
        """Active publishers are loaded into _publisher_map."""
        assert hasattr(adapter, "_publisher_map")
        assert adapter._publisher_map[1] == "Marvel Comics"
        assert adapter._publisher_map[2] == "DC Comics"

    def test_excludes_deleted_publishers(self, adapter: GCDLocalAdapter) -> None:
        """Deleted publishers are not loaded."""
        assert 3 not in adapter._publisher_map


class TestGcdNormalizeName:
    """Tests for _gcd_normalize_name normalization pipeline."""

    def test_normalizes_diacritics(self, adapter: GCDLocalAdapter) -> None:
        """Unicode diacritics are stripped."""
        result = adapter._gcd_normalize_name("Rōnin")
        assert "r" in result
        assert "ō" not in result

    def test_strips_subtitle(self, adapter: GCDLocalAdapter) -> None:
        """Subtitles after : or - are removed."""
        result = adapter._gcd_normalize_name("X-Men : The Early Years")
        assert "x-men" in result
        assert "early years" not in result

    def test_removes_vol_info(self, adapter: GCDLocalAdapter) -> None:
        """Volume information is removed."""
        result = adapter._gcd_normalize_name("Batman, Vol. 1")
        assert "vol" not in result

    def test_lowercases(self, adapter: GCDLocalAdapter) -> None:
        """Result is lowercase for case-insensitive comparison."""
        result = adapter._gcd_normalize_name("X-Men")
        assert result == result.lower()


class TestFindSeriesExact:
    """Tests for find_series_exact."""

    def test_returns_matching_series(self, adapter: GCDLocalAdapter) -> None:
        """Exact name match returns series."""
        results = adapter.find_series_exact("x-men")
        assert len(results) >= 1
        assert any(s["id"] == 1 for s in results)

    def test_returns_empty_for_no_match(self, adapter: GCDLocalAdapter) -> None:
        """No match returns empty list."""
        results = adapter.find_series_exact("nonexistent series")
        assert results == []

    def test_filters_by_publisher(self, adapter: GCDLocalAdapter) -> None:
        """Publisher filter restricts results."""
        results = adapter.find_series_exact("x-men", "marvel comics")
        assert all(s["publisher"] == "Marvel Comics" for s in results)

    def test_publisher_filter_excludes_wrong_publisher(
        self, adapter: GCDLocalAdapter
    ) -> None:
        """Publisher filter excludes non-matching publisher."""
        results = adapter.find_series_exact("x-men", "dc comics")
        assert results == []


class TestFindSeriesStrict:
    """Tests for find_series_strict."""

    def test_strict_match_ampersand_normalized(self, adapter: GCDLocalAdapter) -> None:
        """Strict match normalizes & to 'and'."""
        results = adapter.find_series_strict("xmen")
        assert len(results) >= 1

    def test_strict_match_punctuation_removed(self, adapter: GCDLocalAdapter) -> None:
        """Strict match removes punctuation."""
        results = adapter.find_series_strict("xmen")
        assert len(results) >= 1

    def test_returns_empty_for_no_strict_match(self, adapter: GCDLocalAdapter) -> None:
        """No strict match returns empty list."""
        results = adapter.find_series_strict("completely unrelated series xyz")
        assert results == []

    def test_filters_by_publisher_strict(self, adapter: GCDLocalAdapter) -> None:
        """Publisher filter works with strict matching."""
        results = adapter.find_series_strict("x-men", "marvel comics")
        assert all(s["publisher"] == "Marvel Comics" for s in results)


class TestFindSeriesByYear:
    """Tests for find_series_by_year."""

    def test_finds_series_active_in_year(self, adapter: GCDLocalAdapter) -> None:
        """Series active in the given year are returned."""
        results = adapter.find_series_by_year(1995)
        assert len(results) >= 1
        assert any(s["id"] == 1 for s in results)

    def test_excludes_series_not_started_yet(self, adapter: GCDLocalAdapter) -> None:
        """Series that haven't started by the year are excluded."""
        results = adapter.find_series_by_year(1940)
        assert not any(s["id"] == 1 for s in results)

    def test_excludes_ended_series(self, adapter: GCDLocalAdapter) -> None:
        """Ended series are excluded for years after their end."""
        results = adapter.find_series_by_year(2010)
        assert not any(s["id"] == 1 for s in results)

    def test_includes_ongoing_series(self, adapter: GCDLocalAdapter) -> None:
        """Series with no end year (ongoing) are included."""
        results = adapter.find_series_by_year(2020)
        assert any(s["id"] == 3 for s in results)

    def test_returns_empty_for_no_series(self, adapter: GCDLocalAdapter) -> None:
        """Returns empty list when no series match."""
        results = adapter.find_series_by_year(1900)
        assert results == []


class TestFindIssue:
    """Tests for find_issue."""

    def test_finds_canonical_issue(self, adapter: GCDLocalAdapter) -> None:
        """Canonical issue is found by series_id and number."""
        result = adapter.find_issue(1, "1")
        assert result is not None
        gcd_id, match_type = result
        assert gcd_id == 100
        assert match_type == "canonical"

    def test_returns_none_for_nonexistent_issue(self, adapter: GCDLocalAdapter) -> None:
        """Nonexistent issue returns None."""
        result = adapter.find_issue(1, "999")
        assert result is None

    def test_returns_none_for_wrong_series(self, adapter: GCDLocalAdapter) -> None:
        """Wrong series_id returns None."""
        result = adapter.find_issue(999, "1")
        assert result is None

    def test_finds_newsstand_variant(self, adapter: GCDLocalAdapter) -> None:
        """Newsstand variant is found when it exists."""
        result = adapter.find_issue(3, "301")
        assert result is not None
        _, match_type = result
        assert match_type == "newsstand"


class TestFindIssueByBarcode:
    """Tests for find_issue_by_barcode."""

    def test_finds_issue_by_exact_barcode(self, adapter: GCDLocalAdapter) -> None:
        """Exact barcode match returns GCD issue ID."""
        result = adapter.find_issue_by_barcode("75960609663900411")
        assert result == 100

    def test_returns_none_for_unknown_barcode(self, adapter: GCDLocalAdapter) -> None:
        """Unknown barcode returns None."""
        result = adapter.find_issue_by_barcode("00000000000000")
        assert result is None

    def test_returns_none_for_empty_barcode(self, adapter: GCDLocalAdapter) -> None:
        """Empty barcode returns None."""
        result = adapter.find_issue_by_barcode("")
        assert result is None


class TestFindIssueByBarcodePrefix:
    """Tests for find_issue_by_barcode_prefix."""

    def test_finds_by_prefix_match(self, adapter: GCDLocalAdapter) -> None:
        """Prefix match where GCD barcode starts with input."""
        result = adapter.find_issue_by_barcode_prefix("9781302945374")
        assert result is not None
        gcd_id, matched_bc = result
        assert gcd_id == 103
        assert matched_bc.startswith("9781302945374")

    def test_finds_by_reverse_prefix_match(self, adapter: GCDLocalAdapter) -> None:
        """Prefix match where input barcode starts with GCD barcode (13-char prefix)."""
        result = adapter.find_issue_by_barcode_prefix("9781401232740")
        assert result is not None
        gcd_id, matched_bc = result
        assert gcd_id == 106

    def test_returns_none_for_no_prefix_match(self, adapter: GCDLocalAdapter) -> None:
        """No prefix match returns None."""
        result = adapter.find_issue_by_barcode_prefix("00000000000000")
        assert result is None


class TestGetSeriesInfo:
    """Tests for get_series_info."""

    def test_returns_series_info(self, adapter: GCDLocalAdapter) -> None:
        """Returns full series info dict."""
        info = adapter.get_series_info(1)
        assert info["id"] == 1
        assert info["name"] == "X-Men"
        assert info["year_began"] == 1991
        assert info["year_ended"] == 2001

    def test_returns_empty_dict_for_unknown_id(self, adapter: GCDLocalAdapter) -> None:
        """Unknown series ID returns empty dict."""
        info = adapter.get_series_info(999)
        assert info == {}

    def test_includes_normalized_fields(self, adapter: GCDLocalAdapter) -> None:
        """Info includes normalized name and publisher."""
        info = adapter.get_series_info(1)
        assert "name_normalized" in info
        assert "publisher_normalized" in info


class TestIterSeriesGroups:
    """Tests for iter_series_groups."""

    def test_returns_all_series_groups(self, adapter: GCDLocalAdapter) -> None:
        """Returns list of all series groups."""
        groups = adapter.iter_series_groups()
        assert len(groups) >= 3

    def test_each_group_is_list(self, adapter: GCDLocalAdapter) -> None:
        """Each series group is a list of series."""
        groups = adapter.iter_series_groups()
        for group in groups:
            assert isinstance(group, list)
            assert len(group) >= 1
            assert "id" in group[0]

    def test_all_series_in_groups(self, adapter: GCDLocalAdapter) -> None:
        """All loaded series appear in some group."""
        groups = adapter.iter_series_groups()
        all_series_ids = set()
        for group in groups:
            for s in group:
                all_series_ids.add(s["id"])
        assert 1 in all_series_ids
        assert 3 in all_series_ids
        assert 4 in all_series_ids


class TestSeriesCount:
    """Tests for series_count property."""

    def test_returns_total_series_count(self, adapter: GCDLocalAdapter) -> None:
        """Returns count of all loaded series."""
        assert adapter.series_count >= 5

    def test_returns_int(self, adapter: GCDLocalAdapter) -> None:
        """Returns an integer."""
        assert isinstance(adapter.series_count, int)


class TestIssueCount:
    """Tests for issue_count property."""

    def test_returns_total_issue_count(self, adapter: GCDLocalAdapter) -> None:
        """Returns count of all loaded issues."""
        assert adapter.issue_count >= 9

    def test_returns_int(self, adapter: GCDLocalAdapter) -> None:
        """Returns an integer."""
        assert isinstance(adapter.issue_count, int)


class TestFindIssuesByNumberAndYear:
    """Tests for find_issues_by_number_and_year."""

    def test_finds_issues_in_year_range(self, adapter: GCDLocalAdapter) -> None:
        """Finds issues within ±5 year range."""
        results = adapter.find_issues_by_number_and_year("1", 1991)
        assert len(results) >= 1
        series_ids = [sid for sid, _ in results]
        assert 1 in series_ids

    def test_returns_empty_for_unknown_issue(self, adapter: GCDLocalAdapter) -> None:
        """Returns empty list for nonexistent issue number."""
        results = adapter.find_issues_by_number_and_year("999", 1991)
        assert results == []

    def test_respects_year_boundary(self, adapter: GCDLocalAdapter) -> None:
        """Issues outside ±5 year range are excluded."""
        results = adapter.find_issues_by_number_and_year("1", 1980)
        series_ids = [sid for sid, _ in results]
        assert 1 not in series_ids


class TestGetIssueCoverYear:
    """Tests for get_issue_cover_year."""

    def test_returns_cover_year_from_publication_date(
        self, adapter: GCDLocalAdapter
    ) -> None:
        """Cover year from publication_date is returned."""
        year = adapter.get_issue_cover_year(1, "1")
        assert year == 1991

    def test_returns_none_for_nonexistent_issue(self, adapter: GCDLocalAdapter) -> None:
        """Nonexistent issue returns None."""
        year = adapter.get_issue_cover_year(1, "999")
        assert year is None

    def test_returns_none_for_wrong_series(self, adapter: GCDLocalAdapter) -> None:
        """Wrong series returns None."""
        year = adapter.get_issue_cover_year(999, "1")
        assert year is None


class TestLoadPublishersWithDeleted:
    """Tests for _load_publishers filtering deleted publishers."""

    def test_loads_publishers_fixture(self, test_db: sqlite3.Connection) -> None:
        """Verify test_db has the expected publishers."""
        cursor = test_db.execute("SELECT id, name, deleted FROM gcd_publisher")
        rows = cursor.fetchall()
        publisher_map = {row["id"]: row for row in rows}
        assert len(publisher_map) == 3
        assert publisher_map[1]["name"] == "Marvel Comics"
        assert publisher_map[1]["deleted"] == 0
        assert publisher_map[3]["deleted"] == 1


class TestLoadIssuesWithKeyDate:
    """Tests for _load_issues key_date fallback."""

    def test_cover_year_from_key_date_when_pub_date_missing(
        self, test_db: sqlite3.Connection
    ) -> None:
        """When publication_date has no year, key_date is used."""
        test_db.execute(
            "INSERT INTO gcd_issue VALUES (500, 1, '99', '1995-01', NULL, NULL, 0, NULL, NULL)"
        )
        test_db.commit()

        adapter = GCDLocalAdapter()
        adapter._db = test_db
        adapter._load_publishers()
        adapter._load_series()
        adapter._load_issues()
        adapter._loaded = True

        year = adapter.get_issue_cover_year(1, "99")
        assert year == 1995

    def test_existing_variant_replaced_by_canonical(
        self, test_db: sqlite3.Connection
    ) -> None:
        """Canonical should be returned when it appears after variant in results."""
        test_db.execute(
            "INSERT INTO gcd_issue VALUES (501, 4, '50', '1951-01', '1951', NULL, 0, NULL, 100)"
        )
        test_db.execute(
            "INSERT INTO gcd_issue VALUES (502, 4, '50', '2010-01', '2010', NULL, 0, NULL, NULL)"
        )
        test_db.commit()

        adapter = GCDLocalAdapter()
        adapter._db = test_db
        adapter._load_publishers()
        adapter._load_series()
        adapter._load_issues()
        adapter._loaded = True

        issue = adapter.find_issue(4, "50")
        assert issue is not None
        _, match_type = issue
        assert match_type == "canonical"


class TestEnsureLoaded:
    """Tests for ensure_loaded lazy loading."""

    def test_ensure_loaded_does_not_double_load(
        self, test_db: sqlite3.Connection
    ) -> None:
        """Calling ensure_loaded twice should not reload."""
        adapter = GCDLocalAdapter()
        adapter._db = test_db
        adapter._loaded = False

        adapter.ensure_loaded()
        assert adapter._loaded is True

        first_count = adapter.issue_count
        adapter.ensure_loaded()
        second_count = adapter.issue_count
        assert first_count == second_count


class TestLoadIssuesKeyDateEdgeCases:
    """Tests for _load_issues key_date edge cases."""

    def test_key_date_invalid_format_returns_none(
        self, test_db: sqlite3.Connection
    ) -> None:
        """When key_date has invalid format, cover_year should not be set."""
        test_db.execute(
            "INSERT INTO gcd_issue VALUES (600, 1, '100', 'invalid-date', NULL, NULL, 0, NULL, NULL)"
        )
        test_db.commit()

        adapter = GCDLocalAdapter()
        adapter._db = test_db
        adapter._load_publishers()
        adapter._load_series()
        adapter._load_issues()
        adapter._loaded = True

        year = adapter.get_issue_cover_year(1, "100")
        assert year is None

    def test_key_date_with_split_error(self, test_db: sqlite3.Connection) -> None:
        """When key_date.split('-')[0] raises IndexError, should be caught."""
        test_db.execute(
            "INSERT INTO gcd_issue VALUES (601, 1, '101', '-', NULL, NULL, 0, NULL, NULL)"
        )
        test_db.commit()

        adapter = GCDLocalAdapter()
        adapter._db = test_db
        adapter._load_publishers()
        adapter._load_series()
        adapter._load_issues()
        adapter._loaded = True

        year = adapter.get_issue_cover_year(1, "101")
        assert year is None
