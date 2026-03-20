"""Local GCD adapter - reads from SQLite database for fast bulk matching."""

from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from comic_identity_engine.matching.normalizers import (
    normalize_publisher,
    normalize_series_name,
    strip_subtitle,
)

DB_PATH = os.environ.get("GCD_DB_PATH", "/mnt/bigdata/downloads/2026-03-15.db")


@dataclass
class GCDLocalAdapter:
    """Local GCD adapter using SQLite database.

    Loads all series and issues into memory for fast matching.
    Thread-safe for use in the matching service.
    """

    _db: sqlite3.Connection | None = field(default=None, repr=False)
    _series_map: dict[str, list[dict]] = field(default_factory=dict, repr=False)
    _series_id_to_info: dict[int, dict] = field(default_factory=dict, repr=False)
    _issue_map: dict[tuple[int, str], tuple[int, str]] = field(
        default_factory=dict, repr=False
    )
    _year_to_issues: dict[int, list[tuple[int, int, str]]] = field(
        default_factory=dict, repr=False
    )
    _issue_cover_year: dict[tuple[int, str], int] = field(
        default_factory=dict, repr=False
    )
    _barcode_map: dict[str, int] = field(default_factory=dict, repr=False)
    _publisher_map: dict[int, str] = field(default_factory=dict, repr=False)
    _loaded: bool = field(default=False, repr=False)

    def load(self) -> None:
        """Load all data from SQLite into memory. Call once at startup."""
        if self._db is None:
            self._db = sqlite3.connect(DB_PATH)
            self._db.row_factory = sqlite3.Row

        if not self._loaded:
            self._load_publishers()
            self._load_series()
            self._load_issues()
            self._load_barcodes()
            self._loaded = True

    def ensure_loaded(self) -> None:
        """Lazy load on first use."""
        if not self._loaded:
            self.load()

    def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            self._db.close()
            self._db = None

    def __del__(self) -> None:
        """Ensure database connection is closed on deletion."""
        self.close()

    def _strip_diacritics(self, text: str) -> str:
        """Normalize unicode diacritics so e.g. 'Rōnin' matches 'Ronin'."""
        return (
            unicodedata.normalize("NFKD", text)
            .encode("ascii", "ignore")
            .decode("ascii")
        )

    def _normalize_series_name_strict(self, name: str) -> str:
        """Strip all punctuation and normalize &/and for deep matching."""
        if not name:
            return ""
        name = normalize_series_name(name)
        name = name.lower()
        name = re.sub(r"&", "and", name)
        name = re.sub(r"[^\w\s]", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def _gcd_normalize_name(self, name: str) -> str:
        """Normalize GCD series name for matching against CLZ.

        Pipeline:
        1. strip_diacritics - handles unicode variants
        2. strip_subtitle - removes " : Subtitle" or " - Subtitle"
        3. normalize_series_name - removes Vol. X, publisher parens, II/III, Annual, (YYYY)
        4. lower case
        """
        name = self._strip_diacritics(name)
        name = strip_subtitle(name)
        name = normalize_series_name(name)
        return name.lower()

    def _load_publishers(self) -> None:
        """Load publishers from gcd_publisher table."""
        assert self._db is not None
        rows = self._db.execute(
            "SELECT id, name FROM gcd_publisher WHERE deleted = 0"
        ).fetchall()
        self._publisher_map = {row["id"]: row["name"] for row in rows}

    def _load_series(self) -> None:
        """Load series mappings with normalized names."""
        assert self._db is not None
        from datetime import datetime

        current_year = datetime.now().year
        rows = self._db.execute(
            f"""
            SELECT s.name, s.id, s.year_began, s.year_ended, s.issue_count, s.publisher_id
            FROM gcd_series s
            WHERE s.deleted = 0
              AND s.language_id = 25
              AND s.year_began <= {current_year}
              AND (s.year_ended IS NULL OR s.year_ended >= 1950)
            """
        ).fetchall()

        for row in rows:
            name = self._strip_diacritics(row["name"]).lower()
            name_strict = self._normalize_series_name_strict(name)
            name_normalized = normalize_series_name(name)
            publisher_normalized = ""
            publisher_id = row["publisher_id"]
            if publisher_id and publisher_id in self._publisher_map:
                pub_name = self._publisher_map[publisher_id]
                publisher_normalized = normalize_publisher(pub_name)
            series_info = {
                "id": row["id"],
                "name": row["name"],
                "name_normalized": name_normalized,
                "name_strict": name_strict,
                "publisher_normalized": publisher_normalized,
                "year_began": row["year_began"],
                "year_ended": row["year_ended"],
                "issue_count": row["issue_count"],
            }
            self._series_id_to_info[row["id"]] = series_info
            if name not in self._series_map:
                self._series_map[name] = []
            self._series_map[name].append(series_info)

    def _load_issues(self) -> None:
        """Load issue mappings with cover year extraction."""
        assert self._db is not None
        from datetime import datetime

        current_year = datetime.now().year
        rows = self._db.execute(
            """
            SELECT series_id, number, id, key_date, publication_date,
                   CASE WHEN variant_name = 'Newsstand' THEN 'newsstand'
                        WHEN variant_of_id IS NULL THEN 'canonical'
                        ELSE 'variant' END as match_type
            FROM gcd_issue
            WHERE deleted = 0
            """
        ).fetchall()

        for row in rows:
            key = (row["series_id"], row["number"])
            existing = self._issue_map.get(key)

            pub_date = row["publication_date"]
            cover_year: int | None = None
            if pub_date:
                m = re.search(r"(\d{4})", pub_date)
                if m:
                    cover_year = int(m.group(1))
            if cover_year is None:
                key_date = row["key_date"]
                if key_date:
                    try:
                        cover_year = int(key_date.split("-")[0])
                    except (ValueError, IndexError):
                        pass

            if not existing:
                self._issue_map[key] = (row["id"], row["match_type"])
                if cover_year is not None:
                    self._issue_cover_year[key] = cover_year
            else:
                existing_type = existing[1]
                new_type = row["match_type"]
                if existing_type == "variant" or (
                    existing_type == "canonical" and new_type == "newsstand"
                ):
                    self._issue_map[key] = (row["id"], row["match_type"])
                    if cover_year is not None:
                        self._issue_cover_year[key] = cover_year

            if cover_year is not None and 1950 <= cover_year <= current_year:
                if cover_year not in self._year_to_issues:
                    self._year_to_issues[cover_year] = []
                self._year_to_issues[cover_year].append(
                    (row["series_id"], row["id"], row["number"])
                )

    def _load_barcodes(self) -> None:
        """Load barcode to issue ID mappings."""
        assert self._db is not None
        result = self._db.execute(
            "SELECT barcode, id FROM gcd_issue WHERE barcode IS NOT NULL AND deleted = 0"
        ).fetchall()
        self._barcode_map = {row["barcode"]: row["id"] for row in result}

    # === Series queries ===

    def find_series_exact(
        self, name_lower: str, publisher_normalized: str = ""
    ) -> list[dict]:
        """Find series by exact name match (case-insensitive, diacritics stripped).

        If publisher_normalized is provided, filter results by publisher.
        """
        self.ensure_loaded()
        results = self._series_map.get(name_lower, [])
        if publisher_normalized:
            results = [
                s
                for s in results
                if s.get("publisher_normalized") == publisher_normalized
            ]
        return results

    def find_series_strict(
        self, name_strict: str, publisher_normalized: str = ""
    ) -> list[dict]:
        """Find series by strict-normalized name match.

        If publisher_normalized is provided, filter results by publisher.
        """
        self.ensure_loaded()
        results = []
        for series_list in self._series_map.values():
            info = self._series_id_to_info.get(series_list[0]["id"], {})
            if info.get("name_strict") == name_strict:
                if (
                    not publisher_normalized
                    or info.get("publisher_normalized") == publisher_normalized
                ):
                    results.extend(series_list)
        return results

    def find_series_by_year(self, year: int) -> list[dict]:
        """Find series active in a given year."""
        self.ensure_loaded()
        results = []
        for series_list in self._series_map.values():
            for s in series_list:
                if s["year_began"] <= year <= (s["year_ended"] or year + 20):
                    results.append(s)
        return results

    # === Issue queries ===

    def find_issue(self, series_id: int, issue_nr: str) -> tuple[int, str] | None:
        """Find issue by series ID and number. Returns (gcd_issue_id, match_type) or None."""
        self.ensure_loaded()
        return self._issue_map.get((series_id, issue_nr))

    def find_issues_by_number_and_year(
        self, issue_nr: str, year: int
    ) -> list[tuple[int, int]]:
        """Find all issues with given number from given year (±5). Returns list of (series_id, gcd_issue_id)."""
        self.ensure_loaded()
        candidates = []
        for y in range(max(1950, year - 5), min(2026, year + 6)):
            if y in self._year_to_issues:
                for sid, iid, inr in self._year_to_issues[y]:
                    if inr == issue_nr:
                        candidates.append((sid, iid))
        return candidates

    def get_issue_cover_year(self, series_id: int, issue_nr: str) -> int | None:
        """Get the actual cover/publication year of an issue."""
        self.ensure_loaded()
        return self._issue_cover_year.get((series_id, issue_nr))

    # === Barcode queries ===

    def find_issue_by_barcode(self, barcode: str) -> int | None:
        """Find GCD issue ID by barcode. Returns gcd_issue_id or None."""
        self.ensure_loaded()
        return self._barcode_map.get(barcode)

    def find_issue_by_barcode_prefix(self, barcode: str) -> tuple[int, str] | None:
        """Find GCD issue by barcode prefix match. Returns (gcd_issue_id, matched_barcode) or None."""
        self.ensure_loaded()
        for bc_key, bc_id in self._barcode_map.items():
            if bc_key.startswith(barcode) or barcode.startswith(bc_key[:13]):
                return (bc_id, bc_key)
        return None

    def get_series_info(self, series_id: int) -> dict:
        """Get series info dict by ID. Returns empty dict if not found."""
        self.ensure_loaded()
        return self._series_id_to_info.get(series_id, {})

    def iter_series_groups(self) -> list[list[dict]]:
        """Iterate all series groups (one list per normalized name)."""
        self.ensure_loaded()
        return list(self._series_map.values())

    # === Stats ===

    @property
    def series_count(self) -> int:
        self.ensure_loaded()
        return sum(len(v) for v in self._series_map.values())

    @property
    def issue_count(self) -> int:
        self.ensure_loaded()
        return len(self._issue_map)
