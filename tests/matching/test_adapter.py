"""Regression tests for GCDLocalAdapter._load_issues() cover year logic."""

from __future__ import annotations

import sqlite3

from comic_identity_engine.matching.adapter import GCDLocalAdapter


def make_test_db() -> sqlite3.Connection:
    """Create an in-memory SQLite DB with the schema GCDLocalAdapter expects."""
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
    return db


def make_adapter_with_db(db: sqlite3.Connection) -> GCDLocalAdapter:
    """Build a GCDLocalAdapter that uses an already-open in-memory DB."""
    adapter = GCDLocalAdapter()
    adapter._db = db
    adapter._load_publishers()
    adapter._load_series()
    adapter._load_issues()
    adapter._load_barcodes()
    adapter._loaded = True
    return adapter


class TestIssueLoadingCoverYear:
    """Tests that _load_issues() always retains the earliest cover year."""

    def test_earliest_year_wins_original_before_reprint(self) -> None:
        """Original (1984) appears before reprint (2010): cover year should be 1984."""
        db = make_test_db()
        db.execute("INSERT INTO gcd_publisher VALUES (1, 'Marvel', 0)")
        db.execute(
            "INSERT INTO gcd_series VALUES (1, 'New Mutants', 1983, 1991, 100, 1, 0, 25)"
        )
        # Original comes first in result set
        db.execute(
            "INSERT INTO gcd_issue VALUES (100, 1, '19', '1984-03', '1984', NULL, 0, NULL, NULL)"
        )
        # Reprint comes second — same series_id + number, different year
        db.execute(
            "INSERT INTO gcd_issue VALUES (200, 1, '19', '2010-05', '2010', NULL, 0, NULL, NULL)"
        )
        db.commit()

        adapter = make_adapter_with_db(db)

        assert adapter.get_issue_cover_year(1, "19") == 1984

    def test_earliest_year_wins_reprint_before_original(self) -> None:
        """Reprint (2010) appears before original (1984): cover year should still be 1984."""
        db = make_test_db()
        db.execute("INSERT INTO gcd_publisher VALUES (1, 'Marvel', 0)")
        db.execute(
            "INSERT INTO gcd_series VALUES (1, 'New Mutants', 1983, 1991, 100, 1, 0, 25)"
        )
        # Reprint comes first in result set
        db.execute(
            "INSERT INTO gcd_issue VALUES (200, 1, '19', '2010-05', '2010', NULL, 0, NULL, NULL)"
        )
        # Original comes second
        db.execute(
            "INSERT INTO gcd_issue VALUES (100, 1, '19', '1984-03', '1984', NULL, 0, NULL, NULL)"
        )
        db.commit()

        adapter = make_adapter_with_db(db)

        assert adapter.get_issue_cover_year(1, "19") == 1984

    def test_single_canonical_issue_returns_its_year(self) -> None:
        """A single canonical issue has its own year returned unchanged."""
        db = make_test_db()
        db.execute("INSERT INTO gcd_publisher VALUES (1, 'Marvel', 0)")
        db.execute(
            "INSERT INTO gcd_series VALUES (1, 'New Mutants', 1983, 1991, 100, 1, 0, 25)"
        )
        db.execute(
            "INSERT INTO gcd_issue VALUES (100, 1, '19', '1984-03', '1984', NULL, 0, NULL, NULL)"
        )
        db.commit()

        adapter = make_adapter_with_db(db)

        assert adapter.get_issue_cover_year(1, "19") == 1984

    def test_newsstand_variant_does_not_override_earlier_canonical_year(self) -> None:
        """A newsstand variant with a later year should not replace the earlier canonical year."""
        db = make_test_db()
        db.execute("INSERT INTO gcd_publisher VALUES (1, 'Marvel', 0)")
        db.execute(
            "INSERT INTO gcd_series VALUES (1, 'New Mutants', 1983, 1991, 100, 1, 0, 25)"
        )
        # Canonical original
        db.execute(
            "INSERT INTO gcd_issue VALUES (100, 1, '19', '1984-03', '1984', NULL, 0, NULL, NULL)"
        )
        # Newsstand edition with a later date (e.g. reprinted as newsstand 1985)
        db.execute(
            "INSERT INTO gcd_issue VALUES (101, 1, '19', '1985-01', '1985', NULL, 0, 'Newsstand', NULL)"
        )
        db.commit()

        adapter = make_adapter_with_db(db)

        assert adapter.get_issue_cover_year(1, "19") == 1984
