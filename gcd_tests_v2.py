#!/usr/bin/env python3
"""
Improved CLZ to GCD matching using longbox-matcher library.

Memory and performance efficient:
1. Exact database lookups first (indexed, fast)
2. Normalized variations second
3. Fuzzy matching ONLY as last resort, with database filtering
"""

import csv
import json
import logging
import re
import sqlite3
from pathlib import Path
from tqdm import tqdm

# Import from longbox-matcher
import sys

sys.path.insert(0, "/mnt/extra/josh/code/longbox-matcher")

from longbox_matcher import (
    normalize_for_fuzzy,
    combined_similarity,
)

DB_PATH = "/mnt/bigdata/downloads/2026-03-15.db"
CSV_PATH = "../clz_export_all_columns.csv"
OUTPUT_PATH = "./clz_enriched_v2.csv"
FUZZY_CACHE_PATH = "./gcd_fuzzy_matches_v2.json"
STATS_PATH = "./matching_stats_v2.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Manual mappings for known difficult cases
SERIES_NAME_MAP = {
    "Justice League / International / America": "Justice League International",
}


def ensure_indexes(db: sqlite3.Connection) -> None:
    """Ensure database indexes exist for performance."""
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_gcd_issue_series_number ON gcd_issue (series_id, number)"
    )
    db.commit()


def lookup_series_exact(db: sqlite3.Connection, name: str) -> list[dict]:
    """Exact name lookup (case-insensitive)."""
    rows = db.execute(
        """
        SELECT id, name, year_began, year_ended, publisher_id
        FROM gcd_series
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
          AND deleted = 0
        ORDER BY year_began ASC
    """,
        (name,),
    ).fetchall()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "year_began": row["year_began"],
            "year_ended": row["year_ended"],
            "publisher_id": row["publisher_id"],
        }
        for row in rows
    ]


def normalize_series_name(name: str) -> str:
    """Normalize series name for exact matching."""
    name = re.sub(r",\s*Vol\.\s*\d+", "", name)
    name = re.sub(r"\s*\([^)]+\)", "", name)
    name = re.sub(r"^The\s+", "", name, flags=re.IGNORECASE)
    name = re.sub(
        r"\s+(Annual|Special|HC|TP|Omnibus|TPB)(\s.*)?$", "", name, flags=re.IGNORECASE
    )
    name = name.strip(" -–—")
    return name.strip()


def disambiguate_by_year(
    candidates: list[dict], target_year: int | None
) -> dict | None:
    """Disambiguate multiple series matches by year."""
    if len(candidates) == 1:
        return candidates[0]

    if target_year is None:
        return candidates[0]

    best_match = None
    best_diff = float("inf")

    for series in candidates:
        if series["year_began"]:
            diff = abs(series["year_began"] - target_year)
            if diff <= 5 and diff < best_diff:
                best_diff = diff
                best_match = series

    return best_match if best_match else candidates[0]


def fuzzy_match_with_filtering(
    db: sqlite3.Connection,
    clz_series: str,
    clz_year: int | None,
    fuzzy_cache: dict,
    threshold: float = 0.85,
) -> tuple[dict | None, str, float]:
    """
    Fuzzy match with database filtering for performance.

    Only loads candidate series from database (by year/publisher),
    then fuzzy matches against those.
    """
    clz_norm = normalize_for_fuzzy(clz_series)

    # Build WHERE clause for filtering
    where_conditions = ["deleted = 0"]
    params = []

    # Filter by year if available (huge performance win)
    if clz_year:
        where_conditions.append("(year_began BETWEEN ? AND ?)")
        params.extend([clz_year - 10, clz_year + 5])

    where_clause = " AND ".join(where_conditions)

    # Load ONLY candidate series (filtered by year)
    query = f"""
        SELECT id, name, year_began, year_ended, publisher_id
        FROM gcd_series
        WHERE {where_clause}
        ORDER BY year_began ASC
    """

    rows = db.execute(query, params).fetchall()

    if not rows:
        return None, "no_series", 0.0

    # Fuzzy match against filtered candidates only
    best_match = None
    best_score = 0.0

    for row in rows:
        gcd_name = row["name"]
        gcd_norm = normalize_for_fuzzy(gcd_name)
        score = combined_similarity(clz_norm, gcd_norm)

        if score >= threshold and score > best_score:
            best_match = {
                "id": row["id"],
                "name": row["name"],
                "year_began": row["year_began"],
                "year_ended": row["year_ended"],
                "publisher_id": row["publisher_id"],
            }
            best_score = score

    if best_match:
        match_type = f"fuzzy:{best_score:.3f}"
        return best_match, match_type, best_score

    return None, "no_series", 0.0


def find_series(
    db: sqlite3.Connection,
    clz_series: str,
    clz_year: int | None,
    fuzzy_cache: dict,
) -> tuple[dict | None, str, float]:
    """
    Find GCD series using layered approach:
    1. Manual mapping
    2. Exact match
    3. Normalized variations
    4. Fuzzy match (with filtering)
    """
    # 1. Manual mapping
    if clz_series in SERIES_NAME_MAP:
        mapped = SERIES_NAME_MAP[clz_series]
        matches = lookup_series_exact(db, mapped)
        if matches:
            return disambiguate_by_year(matches, clz_year), "manual_map", 1.0

    # 2. Exact match
    matches = lookup_series_exact(db, clz_series)
    if matches:
        return disambiguate_by_year(matches, clz_year), "exact", 1.0

    # 3. Check cache
    if clz_series in fuzzy_cache:
        cached = fuzzy_cache[clz_series]
        if cached is None:
            return None, "no_series", 0.0
        matches = lookup_series_exact(db, cached)
        if matches:
            return disambiguate_by_year(matches, clz_year), "fuzzy_cached", 0.85

    # 4. Normalized variations
    variations = [
        normalize_series_name(clz_series),
        re.sub(r",\s*Vol\.\s*\d+$", "", clz_series).strip(),
        re.sub(r"\s*\([^)]+\)$", "", clz_series).strip(),
        re.sub(r"^The\s+", "", clz_series, flags=re.IGNORECASE).strip(),
    ]

    for variation in set(variations):
        if variation and variation != clz_series:
            matches = lookup_series_exact(db, variation)
            if matches:
                return (
                    disambiguate_by_year(matches, clz_year),
                    f"normalized:{variation[:20]}",
                    0.95,
                )

    # 5. Fuzzy match (only as last resort, with filtering)
    series, match_type, score = fuzzy_match_with_filtering(
        db, clz_series, clz_year, fuzzy_cache
    )

    if series:
        fuzzy_cache[clz_series] = series["name"]
        return series, match_type, score

    fuzzy_cache[clz_series] = None
    return None, "no_series", 0.0


def enrich_clz_row(
    db: sqlite3.Connection,
    row: dict,
    series_info: dict | None,
) -> dict:
    """Enrich CLZ row with GCD issue info."""
    if series_info is None:
        return {
            **row,
            "gcd_issue_id": None,
            "gcd_url": None,
            "gcd_match_type": "no_series",
        }

    series_id = series_info["id"]
    raw_issue_nr = row["Issue Nr"].strip()

    if not raw_issue_nr:
        return {
            **row,
            "gcd_issue_id": None,
            "gcd_url": None,
            "gcd_match_type": "no_issue_nr",
        }

    try:
        issue_nr = raw_issue_nr.rstrip("ABC")
        issue_nr = str(int(issue_nr))
    except ValueError:
        return {
            **row,
            "gcd_issue_id": None,
            "gcd_url": None,
            "gcd_match_type": "bad_issue_nr",
        }

    # Try newsstand first
    newsstand = db.execute(
        """
        SELECT id FROM gcd_issue
        WHERE series_id = ? AND number = ?
          AND variant_name = 'Newsstand' AND deleted = 0
        LIMIT 1
    """,
        (series_id, issue_nr),
    ).fetchone()

    if newsstand:
        return {
            **row,
            "gcd_issue_id": newsstand["id"],
            "gcd_url": f"https://www.comics.org/issue/{newsstand['id']}/",
            "gcd_match_type": "newsstand",
        }

    # Fall back to canonical
    canonical = db.execute(
        """
        SELECT id FROM gcd_issue
        WHERE series_id = ? AND number = ?
          AND variant_of_id IS NULL AND deleted = 0
        LIMIT 1
    """,
        (series_id, issue_nr),
    ).fetchone()

    if canonical:
        return {
            **row,
            "gcd_issue_id": canonical["id"],
            "gcd_url": f"https://www.comics.org/issue/{canonical['id']}/",
            "gcd_match_type": "canonical",
        }

    return {
        **row,
        "gcd_issue_id": None,
        "gcd_url": None,
        "gcd_match_type": "no_issue_match",
    }


def load_existing_output(output_path: str) -> dict[str, dict]:
    """Load already-enriched rows."""
    path = Path(output_path)
    if not path.exists():
        return {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["Core ComicID"]: row for row in reader}


def load_fuzzy_cache(path: str) -> dict[str, str | None]:
    """Load fuzzy cache."""
    p = Path(path)
    if not p.exists():
        return {}

    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_fuzzy_cache(path: str, cache: dict) -> None:
    """Save fuzzy cache."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def main():
    """Main processing function."""
    logger.info("Loading CLZ export...")
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        clz_rows = list(reader)

    logger.info("Loaded %d rows from %s", len(clz_rows), CSV_PATH)

    existing = load_existing_output(OUTPUT_PATH)
    logger.info("Found %d already-processed rows", len(existing))

    pending = [r for r in clz_rows if r["Core ComicID"] not in existing]
    logger.info("Rows to process: %d", len(pending))

    if not pending:
        logger.info("Nothing to do")
        return

    fuzzy_cache = load_fuzzy_cache(FUZZY_CACHE_PATH)
    logger.info("Loaded %d fuzzy cache entries", len(fuzzy_cache))

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    logger.info("Ensuring indexes...")
    ensure_indexes(db)

    # Build unique series list
    unique_series = {}
    for row in pending:
        series_name = row["Series"]
        if series_name not in unique_series:
            year = None
            if row.get("Cover Year"):
                try:
                    year = int(row["Cover Year"])
                except ValueError:
                    pass
            elif row.get("Release Year"):
                try:
                    year = int(row["Release Year"])
                except ValueError:
                    pass

            unique_series[series_name] = year

    logger.info("Resolving %d unique series...", len(unique_series))

    series_cache = {}
    stats = {
        "exact_matches": 0,
        "normalized_matches": 0,
        "fuzzy_matches": 0,
        "no_matches": 0,
        "manual_maps": 0,
    }

    for series_name, year in tqdm(unique_series.items(), desc="Resolving series"):
        series, match_type, score = find_series(db, series_name, year, fuzzy_cache)

        series_cache[series_name] = (series, match_type, score)

        if match_type == "exact":
            stats["exact_matches"] += 1
        elif match_type.startswith("normalized"):
            stats["normalized_matches"] += 1
        elif match_type.startswith("fuzzy"):
            stats["fuzzy_matches"] += 1
        elif match_type == "manual_map":
            stats["manual_maps"] += 1
        else:
            stats["no_matches"] += 1

        if len(series_cache) % 50 == 0:
            save_fuzzy_cache(FUZZY_CACHE_PATH, fuzzy_cache)

    save_fuzzy_cache(FUZZY_CACHE_PATH, fuzzy_cache)

    logger.info("Series resolution stats:")
    logger.info("  Exact matches: %d", stats["exact_matches"])
    logger.info("  Normalized matches: %d", stats["normalized_matches"])
    logger.info("  Fuzzy matches: %d", stats["fuzzy_matches"])
    logger.info("  Manual maps: %d", stats["manual_maps"])
    logger.info("  No matches: %d", stats["no_matches"])

    # Enrich rows
    out_fieldnames = list(fieldnames or []) + [
        "gcd_issue_id",
        "gcd_url",
        "gcd_match_type",
    ]
    output_exists = Path(OUTPUT_PATH).exists()

    issue_stats = {
        "newsstand": 0,
        "canonical": 0,
        "no_issue_nr": 0,
        "bad_issue_nr": 0,
        "no_issue_match": 0,
        "no_series": 0,
    }

    with open(OUTPUT_PATH, "a", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=out_fieldnames, extrasaction="ignore")

        if not output_exists:
            writer.writeheader()

        for row in tqdm(pending, desc="Enriching issues"):
            series_info, _, _ = series_cache[row["Series"]]
            result = enrich_clz_row(db, row, series_info)

            writer.writerow(result)
            out_f.flush()

            match_type = result["gcd_match_type"]
            if match_type in issue_stats:
                issue_stats[match_type] += 1

    db.close()

    logger.info("Issue matching stats:")
    logger.info("  Newsstand: %d", issue_stats["newsstand"])
    logger.info("  Canonical: %d", issue_stats["canonical"])
    logger.info("  No series: %d", issue_stats["no_series"])
    logger.info("  No issue match: %d", issue_stats["no_issue_match"])

    total = len(pending)
    success = issue_stats["newsstand"] + issue_stats["canonical"]
    success_rate = (success / total * 100) if total > 0 else 0
    logger.info("Success rate: %.1f%% (%d/%d)", success_rate, success, total)

    all_stats = {
        "series_resolution": stats,
        "issue_matching": issue_stats,
        "total_processed": total,
        "success_rate": success_rate,
    }

    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_stats, f, indent=2)

    logger.info("Stats saved to %s", STATS_PATH)


if __name__ == "__main__":
    main()
