"""GCD Dump Matcher for matching comics against a GCD SQLite dump.

This module provides the GCDDumpMatcher class which implements the proven
matching logic from gcd_tests.py for matching CLZ comics to GCD database entries.

USAGE:
    from comic_identity_engine.services import GCDDumpMatcher

    matcher = GCDDumpMatcher("/path/to/gcd.db")
    result = matcher.match(
        barcode="9781302945374",
        series="X-Men",
        issue="1",
        year=1991
    )
    # result.match_type == "barcode"
    # result.gcd_issue_id == 12345

PERFORMANCE:
    - Loads all barcodes/series/issues into memory on init (~250MB)
    - Match speed: ~16K it/s
    - Typical use: Batch matching for CSV imports
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class GCDMatchResult:
    """Result of a GCD match operation.

    Attributes:
        gcd_issue_id: The GCD issue ID if matched, None otherwise
        match_type: Description of how the match was made (e.g., "barcode",
            "barcode_prefix", "closest_year_with_issue", "no_series", etc.)
        gcd_url: Full URL to the GCD issue page if matched
    """

    gcd_issue_id: Optional[int] = None
    match_type: str = "unknown"
    gcd_url: Optional[str] = None

    def __post_init__(self):
        if self.gcd_issue_id and not self.gcd_url:
            self.gcd_url = f"https://www.comics.org/issue/{self.gcd_issue_id}/"


class GCDDumpMatcher:
    """Matcher for finding comics in a GCD SQLite dump.

    This class encapsulates the proven matching logic from gcd_tests.py which
    achieves 96.4% match rate (5,014/5,203 CLZ comics).

    The matching pipeline:
    1. Barcode exact match (72.7% of matches)
    2. ISBN prefix match (GCD appends 5-digit suffix to ISBNs)
    3. Series + issue disambiguation using year proximity and issue existence

    Example:
        matcher = GCDDumpMatcher("/mnt/bigdata/downloads/gcd.db")
        result = matcher.match(
            barcode="9781302945374",
            series="The X-Men",
            issue="1",
            year=1991
        )
    """

    def __init__(self, db_path: str | Path):
        """Initialize the matcher by loading GCD data into memory.

        Args:
            db_path: Path to the GCD SQLite database file

        Loads:
            - Barcode mappings (~362K entries)
            - Series mappings (~102K series)
            - Issue mappings (~2.57M issues)

        Memory usage: ~250MB
        """
        self.db_path = Path(db_path)
        self._barcode_map: dict[str, int] = {}
        self._series_map: dict[str, list[dict]] = {}
        self._series_id_to_info: dict[int, dict] = {}
        self._issue_map: dict[tuple[int, str], tuple[int, str]] = {}
        self._year_to_issues: dict[int, list[tuple[int, int, str]]] = {}
        self._issue_cover_year: dict[tuple[int, str], int] = {}

        self._load_data()

    def _load_data(self) -> None:
        """Load all GCD data from SQLite into memory."""
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row

        try:
            self._load_barcodes(db)
            self._load_series(db)
            self._load_issues(db)
        finally:
            db.close()

    def _load_barcodes(self, db: sqlite3.Connection) -> None:
        """Load barcode to issue ID mappings."""
        result = db.execute(
            "SELECT barcode, id FROM gcd_issue WHERE barcode IS NOT NULL AND deleted = 0"
        ).fetchall()
        self._barcode_map = {row["barcode"]: row["id"] for row in result}

    def _load_series(self, db: sqlite3.Connection) -> None:
        """Load series mappings with normalized names."""
        rows = db.execute(
            """
            SELECT name, id, year_began, year_ended, issue_count
            FROM gcd_series
            WHERE deleted = 0
              AND language_id = 25
              AND year_began <= 2026
              AND (year_ended IS NULL OR year_ended >= 1950)
            """
        ).fetchall()

        for row in rows:
            name = self._strip_diacritics(row["name"]).lower()
            name_strict = self._normalize_series_name_strict(name)
            series_info = {
                "id": row["id"],
                "name": row["name"],
                "name_strict": name_strict,
                "year_began": row["year_began"],
                "year_ended": row["year_ended"],
                "issue_count": row["issue_count"],
            }
            self._series_id_to_info[row["id"]] = series_info
            if name not in self._series_map:
                self._series_map[name] = []
            self._series_map[name].append(series_info)

    def _load_issues(self, db: sqlite3.Connection) -> None:
        """Load issue mappings with cover year extraction."""
        rows = db.execute(
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

            # Parse cover year from publication_date (actual cover date)
            pub_date = row["publication_date"]
            cover_year: Optional[int] = None
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

            # Build year index for reverse lookup
            if cover_year is not None and 1950 <= cover_year <= 2026:
                if cover_year not in self._year_to_issues:
                    self._year_to_issues[cover_year] = []
                self._year_to_issues[cover_year].append(
                    (row["series_id"], row["id"], row["number"])
                )

    @staticmethod
    def _strip_diacritics(text: str) -> str:
        """Normalize unicode diacritics so e.g. 'Rōnin' matches 'Ronin'."""
        return (
            unicodedata.normalize("NFKD", text)
            .encode("ascii", "ignore")
            .decode("ascii")
        )

    @staticmethod
    def normalize_series_name(name: str) -> str:
        """Normalize series name for matching.

        Removes:
            - Publisher parentheticals: "(Marvel)", "(Cartoon Books)"
            - Volume info: ", Vol. 1", ", Volume 2"
            - Roman numeral suffixes: " II", " III"

        Args:
            name: Raw series name from CLZ

        Returns:
            Normalized series name
        """
        if not name:
            return ""

        # Remove publisher parentheticals
        name = re.sub(r"\s*\([^)]*\)$", "", name)

        # Remove volume info (handles both trailing and mid-string)
        name = re.sub(r",\s*Vol\.\s*\d+(\s+|$)", " ", name, flags=re.IGNORECASE).strip()
        name = re.sub(
            r",\s*Volume\s+\d+(\s+|$)", " ", name, flags=re.IGNORECASE
        ).strip()

        # Remove Roman numeral suffixes
        name = re.sub(r"\s+II\s*$", "", name)
        name = re.sub(r"\s+III\s*$", "", name)

        return name.strip()

    @classmethod
    def _normalize_series_name_strict(cls, name: str) -> str:
        """Strip all punctuation and normalize &/and for deep matching."""
        if not name:
            return ""
        name = cls.normalize_series_name(name)
        name = name.lower()
        name = re.sub(r"&", "and", name)
        name = re.sub(r"[^\w\s]", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    @staticmethod
    def strip_volume(name: str) -> str:
        """Strip volume information from series name.

        Legacy alias for normalize_series_name. Kept for backward compatibility.

        Args:
            name: Series name that may contain volume info

        Returns:
            Series name with volume info removed
        """
        return GCDDumpMatcher.normalize_series_name(name)

    def _find_series_candidates(
        self,
        series_name: str,
        year: Optional[int],
        issue_nr: Optional[str] = None,
    ) -> list[dict]:
        """Find candidate series matching the given series name.

        Uses multiple matching strategies:
        1. Strict normalized match (handles &/and, punctuation)
        2. Exact match
        3. Colon-to-comma variant
        4. With/without "The" prefix
        5. Word-set match (handles word-order variants)
        6. Substring match (if no candidates or all from wrong era)
        """
        name_lower = self._strip_diacritics(series_name).lower()
        name_strict = self._normalize_series_name_strict(name_lower)
        candidates = []
        seen = set()

        def add_candidates(new_candidates):
            for c in new_candidates:
                if c["id"] not in seen:
                    seen.add(c["id"])
                    candidates.append(c)

        def add_from_strict_match():
            for series_key, series_list in self._series_map.items():
                if (
                    self._series_id_to_info.get(series_list[0]["id"], {}).get(
                        "name_strict"
                    )
                    == name_strict
                ):
                    add_candidates(series_list)

        # 1. Try strict-normalized exact match
        add_from_strict_match()

        # 1a. Try exact match
        add_candidates(self._series_map.get(name_lower, []))

        # 1b. Try colon-to-comma variant
        comma_name = name_lower.replace(": ", ", ")
        if comma_name != name_lower:
            add_candidates(self._series_map.get(comma_name, []))

        # 2. Try with/without "The" prefix
        if name_lower.startswith("the "):
            add_candidates(self._series_map.get(name_lower[4:], []))
        else:
            add_candidates(self._series_map.get(f"the {name_lower}", []))

        # 3. Try removing other common articles
        for article in ["a ", "an "]:
            if name_lower.startswith(article):
                add_candidates(self._series_map.get(name_lower[len(article) :], []))
                break

        # 3b. Word-set match (handles "X-Men Classic" vs "Classic X-Men")
        search_words = set(name_lower.split())
        if len(search_words) >= 2:
            for series_key, series_list in self._series_map.items():
                if set(series_key.split()) == search_words and series_key != name_lower:
                    add_candidates(series_list)

        # 4. Substring match if no candidates or all from wrong era
        all_wrong_era = (
            year is not None
            and bool(candidates)
            and all(
                (s["year_ended"] is not None and s["year_ended"] < year - 5)
                or s["year_began"] > year + 5
                for s in candidates
            )
        )
        if (not candidates or all_wrong_era) and len(name_lower) >= 4:
            search_terms = name_lower
            for prefix in ["the ", "a ", "an "]:
                if search_terms.startswith(prefix):
                    search_terms = search_terms[len(prefix) :]
                    break

            search_terms_clean = search_terms.rstrip(" the")
            if search_terms_clean != search_terms:
                search_terms = search_terms_clean

            for series_key, series_list in self._series_map.items():
                if search_terms in series_key or series_key in search_terms:
                    add_candidates(series_list)

        # 5. Date-based fallback
        if not candidates and year is not None:
            for series_list in self._series_map.values():
                for series in series_list:
                    if (
                        series["year_began"]
                        <= year
                        <= (series["year_ended"] or year + 20)
                    ):
                        add_candidates([series])

        if not candidates:
            return []

        if year is None:
            return sorted(candidates, key=lambda x: -x["issue_count"])

        # Score candidates by year proximity and issue existence
        def _series_year_score(series: dict) -> tuple[int, int]:
            if issue_nr is not None:
                key = (series["id"], issue_nr)
                if key in self._issue_map:
                    cy = self._issue_cover_year.get(key)
                    if cy is not None:
                        return cy, abs(cy - year)
            return series["year_began"], abs(series["year_began"] - year)

        scored = []
        for series in candidates:
            score = 0
            year_for_series, distance = _series_year_score(series)

            if series["year_ended"] and series["year_ended"] < year_for_series:
                score -= 1000
            if year_for_series > year + 5:
                score -= 1000

            score -= distance
            score += series["issue_count"] / 10

            scored.append((score, series))

        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored]

    def _similarity_score(self, s1: str, s2: str) -> float:
        """Simple similarity score based on common substrings."""
        s1, s2 = s1.lower(), s2.lower()
        if s1 == s2:
            return 1.0

        score = 0.0

        if s1 in s2 or s2 in s1:
            shorter = s1 if len(s1) <= len(s2) else s2
            longer = s2 if len(s1) <= len(s2) else s1
            overlap = len(shorter)
            total = len(longer)
            if longer.startswith(shorter):
                score = max(score, min(0.9, 1.4 * overlap / total))
            else:
                score = max(score, 0.8 * overlap / total)

        def _words(s: str) -> set[str]:
            return {
                re.sub(r"[^\w-]", "", w) for w in s.split() if re.sub(r"[^\w-]", "", w)
            }

        words1 = _words(s1)
        words2 = _words(s2)
        if words1 and words2:
            intersection = len(words1 & words2)
            union = len(words1 | words2)
            score = max(score, intersection / union if union > 0 else 0.0)

        return score

    def _find_best_series_id(
        self,
        series_name: str,
        issue_nr: str,
        year: Optional[int],
    ) -> tuple[Optional[int], str]:
        """Find the best matching series ID for the given parameters.

        Returns:
            Tuple of (series_id, match_reason)
        """
        candidates = self._find_series_candidates(series_name, year, issue_nr)

        if not candidates:
            # Fallback: reverse lookup by issue number and year
            if year is not None:
                reverse_matches = self._find_issues_by_number_and_year(issue_nr, year)
                if reverse_matches:
                    unique_series = list(
                        set(series_id for series_id, _ in reverse_matches)
                    )
                    if len(unique_series) == 1:
                        series_id = unique_series[0]
                        series_info = self._series_id_to_info.get(series_id)
                        if series_info:
                            return (
                                series_id,
                                f"reverse_lookup_issue_year:{series_info['name']}",
                            )
                    elif len(unique_series) > 1:
                        best_series_id = None
                        best_similarity = 0
                        for series_id in unique_series:
                            series_info = self._series_id_to_info.get(series_id)
                            if series_info:
                                similarity = self._similarity_score(
                                    series_name.lower(), series_info["name"].lower()
                                )
                                if similarity > best_similarity:
                                    best_similarity = similarity
                                    best_series_id = series_id
                        if best_series_id:
                            series_info = self._series_id_to_info[best_series_id]
                            return (
                                best_series_id,
                                f"reverse_lookup_closest_name:{series_info['name']}",
                            )

            return None, "no_series"

        if len(candidates) == 1:
            return candidates[0]["id"], "only_series"

        # Date-aware filtering
        if year is not None and len(candidates) > 1:
            date_filtered = []
            for series in candidates:
                cy = self._issue_cover_year.get((series["id"], issue_nr))
                if cy is not None:
                    if cy > year + 5 or cy < year - 5:
                        continue
                    date_filtered.append(series)
                    continue
                if series["year_began"] > year + 5:
                    continue
                if series["year_ended"] and series["year_ended"] < year - 5:
                    continue
                date_filtered.append(series)

            if date_filtered:
                candidates = date_filtered

        # Check if issue exists in each candidate
        candidates_with_issue = []
        for series in candidates:
            issue_key = (series["id"], issue_nr)
            if issue_key in self._issue_map:
                candidates_with_issue.append(series)

        if len(candidates_with_issue) == 1:
            return candidates_with_issue[0]["id"], "only_one_with_issue"

        if len(candidates_with_issue) > 1:
            if year is not None:

                def _issue_year_distance(s: dict) -> int:
                    cy = self._issue_cover_year.get((s["id"], issue_nr))
                    if cy is not None:
                        return abs(cy - year)
                    return abs(s["year_began"] - year)

                candidates_with_issue.sort(key=_issue_year_distance)
                return candidates_with_issue[0]["id"], "closest_year_with_issue"
            return candidates_with_issue[0]["id"], "multiple_with_issue"

        # No series has this issue - try reverse lookup
        if year is not None:
            reverse_matches = self._find_issues_by_number_and_year(issue_nr, year)
            if reverse_matches:
                unique_series = list(set(series_id for series_id, _ in reverse_matches))
                if len(unique_series) == 1:
                    series_id = unique_series[0]
                    series_info = self._series_id_to_info.get(series_id)
                    if series_info:
                        return (
                            series_id,
                            f"reverse_lookup_issue_year:{series_info['name']}",
                        )
                elif len(unique_series) > 1:
                    best_series_id = None
                    best_similarity = 0
                    for series_id in unique_series:
                        series_info = self._series_id_to_info.get(series_id)
                        if series_info:
                            similarity = self._similarity_score(
                                series_name.lower(), series_info["name"].lower()
                            )
                            if similarity > best_similarity:
                                best_similarity = similarity
                                best_series_id = series_id
                    if best_series_id:
                        series_info = self._series_id_to_info[best_series_id]
                        return (
                            best_series_id,
                            f"reverse_lookup_closest_name:{series_info['name']}",
                        )

        best = candidates[0]
        return best["id"], f"no_issue_in_{len(candidates)}_series"

    def _find_issues_by_number_and_year(
        self, issue_nr: str, year: Optional[int]
    ) -> list[tuple[int, int]]:
        """Reverse lookup: Find all issues with a given issue number, optionally filtered by year."""
        candidates = []
        if year is not None:
            for y in range(max(1950, year - 5), min(2026, year + 6)):
                if y in self._year_to_issues:
                    for series_id, issue_id, issue_num in self._year_to_issues[y]:
                        if issue_num == issue_nr:
                            candidates.append((series_id, issue_id))
        else:
            for y in range(1950, 2027):
                if y in self._year_to_issues:
                    for series_id, issue_id, issue_num in self._year_to_issues[y]:
                        if issue_num == issue_nr:
                            candidates.append((series_id, issue_id))
        return candidates

    def _try_barcode_match(self, barcode: str) -> tuple[Optional[int], Optional[str]]:
        """Try to match by barcode (exact or ISBN prefix).

        Returns:
            Tuple of (gcd_issue_id, match_type) or (None, None) if no match
        """
        if not barcode or barcode == "00000000000000":
            return None, None

        # Exact match
        if barcode in self._barcode_map:
            return self._barcode_map[barcode], "barcode"

        # ISBN prefix match (GCD adds suffix like "54499")
        for bc_key, bc_id in self._barcode_map.items():
            if bc_key.startswith(barcode) or barcode.startswith(bc_key[:13]):
                return bc_id, "barcode_prefix"

        return None, None

    def match(
        self,
        barcode: Optional[str] = None,
        series: Optional[str] = None,
        issue: Optional[str] = None,
        year: Optional[int] = None,
        series_group: Optional[str] = None,
    ) -> GCDMatchResult:
        """Match a comic to GCD using the proven matching algorithm.

        This is the main entry point for matching. It implements the full
        matching pipeline that achieves 96.4% accuracy on CLZ data.

        Args:
            barcode: UPC or ISBN barcode (optional)
            series: Series name (optional, but required if no barcode match)
            issue: Issue number (optional, but required if no barcode match)
            year: Publication year for disambiguation (optional)
            series_group: Alternative series name from CLZ (optional)

        Returns:
            GCDMatchResult with gcd_issue_id, match_type, and gcd_url

        Example:
            matcher = GCDDumpMatcher("/path/to/gcd.db")

            # Barcode match (preferred)
            result = matcher.match(barcode="9781302945374")

            # Series + issue match
            result = matcher.match(
                series="X-Men",
                issue="1",
                year=1991
            )

            # With series group fallback
            result = matcher.match(
                series="X-Men Classic",
                issue="1",
                year=1990,
                series_group="X-Men"
            )
        """
        # Try barcode matching first
        if barcode:
            gcd_issue_id, match_type = self._try_barcode_match(barcode)
            if gcd_issue_id:
                return GCDMatchResult(
                    gcd_issue_id=gcd_issue_id, match_type=match_type or "barcode"
                )

        # Fall back to series/issue matching
        if not series or not issue:
            return GCDMatchResult(match_type="missing_data")

        # Parse/normalize inputs
        normalized_series = self.normalize_series_name(series)
        issue_nr = self._parse_issue_nr(issue)

        if not issue_nr:
            return GCDMatchResult(match_type="bad_issue_nr")

        # Find best series
        series_id, series_match = self._find_best_series_id(
            normalized_series, issue_nr, year
        )

        # Try issue field if different from issue_nr (handles variant suffixes)
        issue_nr_for_lookup = issue_nr
        if (
            not series_id
            and issue
            and issue != issue_nr
            and any(c.isalpha() for c in issue)
            and not any(c.isalpha() for c in issue_nr)
        ):
            issue_nr_alt = self._parse_issue_nr(issue)
            if issue_nr_alt and issue_nr_alt != issue_nr:
                series_id, series_match = self._find_best_series_id(
                    normalized_series, issue_nr_alt, year
                )
                if series_id:
                    series_match = f"{series_match}_from_issue_field"
                    issue_nr_for_lookup = issue_nr_alt

        # Fallback to series_group if provided
        if not series_id and series_group:
            series_id, series_match = self._find_best_series_id(
                series_group, issue_nr, year
            )
            if series_id:
                series_match = f"{series_match}_from_series_group"

        # Year-gap safety net: try series_group if large year gap detected
        matched_cover_yr = (
            self._issue_cover_year.get((series_id, issue_nr_for_lookup))
            if series_id
            else None
        )
        large_year_gap = (
            matched_cover_yr is not None
            and year is not None
            and abs(matched_cover_yr - year) >= 6
        )
        if large_year_gap and series_group and series_id:
            series_id_sg, series_match_sg = self._find_best_series_id(
                series_group, issue_nr_for_lookup, year
            )
            if series_id_sg is not None:
                sg_cyr = self._issue_cover_year.get((series_id_sg, issue_nr_for_lookup))
                if (
                    sg_cyr is not None
                    and matched_cover_yr is not None
                    and year is not None
                ):
                    sg_year_diff = abs(sg_cyr - year)
                    matched_year_diff = abs(matched_cover_yr - year)
                    if sg_year_diff < matched_year_diff:
                        series_id = series_id_sg
                        series_match = f"{series_match_sg}_fallback_from_series"

        if not series_id:
            return GCDMatchResult(match_type=f"no_series:{series_match}")

        # Look up the issue
        issue_key = (series_id, issue_nr_for_lookup)
        issue_result = self._issue_map.get(issue_key)
        if issue_result:
            gcd_issue_id, issue_match = issue_result
            return GCDMatchResult(
                gcd_issue_id=gcd_issue_id,
                match_type=f"{series_match}:{issue_match}",
            )

        return GCDMatchResult(match_type=f"{series_match}:no_issue")

    @staticmethod
    def _parse_issue_nr(issue_str: str) -> Optional[str]:
        """Parse issue number string, returning normalized form or None."""
        issue_nr = issue_str.strip()

        if not issue_nr:
            return "1"

        try:
            return str(int(issue_nr))
        except ValueError:
            return None

    def get_stats(self) -> dict:
        """Get statistics about loaded GCD data.

        Returns:
            Dict with counts of barcodes, series, and issues
        """
        return {
            "barcodes": len(self._barcode_map),
            "series": len(self._series_id_to_info),
            "unique_series_names": len(self._series_map),
            "issues": len(self._issue_map),
            "years_indexed": len(self._year_to_issues),
        }
