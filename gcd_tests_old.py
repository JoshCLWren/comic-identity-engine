import argparse
import csv
import json
import logging
import re
import sqlite3
from pathlib import Path
from tqdm import tqdm

DB_PATH = "/mnt/bigdata/downloads/2026-03-15.db"
CSV_PATH = "../clz_export_all_columns.csv"
OUTPUT_PATH = "./clz_all_columns_enriched.csv"
FUZZY_CACHE_PATH = "./gcd_fuzzy_matches.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SERIES_NAME_MAP = {
    "Justice League / International / America": "Justice League International",
    "New Mutants Summer Special": "The New Mutants Summer Special",
    "Malibu Sun": "The Malibu Sun",
    "Nextwave": "Nextwave: Agents of H.A.T.E.",
    "Witchfinder: The Mysteries Of Unland": "Sir Edward Grey, Witchfinder: The Mysteries of Unland",
    "Mephisto vs": "Mephisto vs. the Fantastic Four, X-Factor, the X-Men & the Avengers",
    "X-Men: Magik": "X-Men: Magik - Storm & Illyana",
    "Spider-Man / Dr. Strange": "Spider-Man / Dr. Strange: The Way to Dusty Death",
    "What If...? Donald Duck Became Wolverine": "Marvel & Disney: What If...? Donald Duck Became Wolverine",
}


def ensure_indexes(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_gcd_issue_series_number ON gcd_issue (series_id, number)"
    )
    db.commit()


def normalize_series_name(name: str) -> str:
    name = re.sub(r",\s*Vol\.\s*\d+", "", name)
    name = re.sub(r"\s*\([^)]+\)", "", name)
    name = re.sub(r"^The\s+", "", name, flags=re.IGNORECASE)
    name = re.sub(
        r"\s+(Annual|Special|HC|TP|Omnibus|TPB)(\s.*)?$", "", name, flags=re.IGNORECASE
    )
    # Strip "A " prefix
    name = re.sub(r"^A\s+", "", name, flags=re.IGNORECASE)
    # Normalize "and" vs "&"
    name = re.sub(r"\s+&\s+", " and ", name)
    # Normalize "/" spacing
    name = re.sub(r"\s+/\s+", " / ", name)
    # Normalize colons and commas (B.P.R.D.: vs B.P.R.D.,)
    name = re.sub(r"\s*:\s*", ": ", name)
    name = re.sub(r"\s*,\s*", ", ", name)
    name = name.strip(" -–—")
    return name.strip()


def lookup_series(
    db: sqlite3.Connection, name: str, year: int | None = None
) -> int | None:
    # Try with "The " prefix first (for series like "The Uncanny X-Men")
    name_with_the = f"The {name}" if not name.lower().startswith("the ") else name

    if year is not None:
        # Try year disambiguation first, but prioritize series with more issues
        # Try with "The " prefix first
        row = db.execute(
            """
            SELECT id FROM gcd_series
            WHERE name = ? COLLATE NOCASE
              AND deleted = 0
              AND language_id = 25
              AND year_began BETWEEN (? - 5) AND (? + 5)
            ORDER BY ABS(year_began - ?) ASC, issue_count DESC, year_began ASC
            LIMIT 1
        """,
            (name_with_the, year, year, year),
        ).fetchone()
        # If not found, try without "The "
        if not row and name_with_the != name:
            row = db.execute(
                """
                SELECT id FROM gcd_series
                WHERE name = ? COLLATE NOCASE
                  AND deleted = 0
                  AND language_id = 25
                  AND year_began BETWEEN (? - 5) AND (? + 5)
                ORDER BY ABS(year_began - ?) ASC, issue_count DESC, year_began ASC
                LIMIT 1
            """,
                (name, year, year, year),
            ).fetchone()
        # If no series found within ±5 years, fall back to English series 1950-2026
        if not row:
            row = db.execute(
                """
                SELECT id FROM gcd_series
                WHERE name = ? COLLATE NOCASE
                  AND deleted = 0
                  AND language_id = 25
                  AND year_began BETWEEN 1950 AND 2026
                ORDER BY issue_count DESC, year_began ASC
                LIMIT 1
            """,
                (name_with_the if name_with_the.startswith("The ") else name,),
            ).fetchone()
            if not row and name_with_the != name:
                row = db.execute(
                    """
                    SELECT id FROM gcd_series
                    WHERE name = ? COLLATE NOCASE
                      AND deleted = 0
                      AND language_id = 25
                      AND year_began BETWEEN 1950 AND 2026
                    ORDER BY issue_count DESC, year_began ASC
                    LIMIT 1
                """,
                    (name,),
                ).fetchone()
    else:
        row = db.execute(
            """
            SELECT id FROM gcd_series
            WHERE name = ? COLLATE NOCASE
              AND deleted = 0
              AND language_id = 25
              AND year_began BETWEEN 1950 AND 2026
            ORDER BY issue_count DESC, year_began ASC
            LIMIT 1
        """,
            (name_with_the,),
        ).fetchone()
        if not row and name_with_the != name:
            row = db.execute(
                """
                SELECT id FROM gcd_series
                WHERE name = ? COLLATE NOCASE
                  AND deleted = 0
                  AND language_id = 25
                  AND year_began BETWEEN 1950 AND 2026
                ORDER BY issue_count DESC, year_began ASC
                LIMIT 1
            """,
                (name,),
            ).fetchone()

    return row["id"] if row else None


def get_all_series_names(db: sqlite3.Connection) -> list[str]:
    rows = db.execute("""
        SELECT name FROM gcd_series
        WHERE deleted = 0
          AND language_id = 25
          AND year_began BETWEEN 1950 AND 2026
    """).fetchall()
    return [r["name"] for r in rows]


def load_fuzzy_cache(path: str) -> dict[str, str | None]:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_fuzzy_cache(path: str, cache: dict[str, str | None]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def get_series_id(
    db: sqlite3.Connection,
    series_name: str,
    all_series_names: list[str],
    fuzzy_cache: dict[str, str | None],
    year: int | None = None,
) -> tuple[int | None, str]:
    if series_name in SERIES_NAME_MAP:
        mapped = SERIES_NAME_MAP[series_name]
        sid = lookup_series(db, mapped, year)
        if sid:
            return sid, f"manual_map:{mapped}"

    sid = lookup_series(db, series_name, year)
    if sid:
        return sid, "exact"

    stripped_vol = re.sub(r",\s*Vol\.\s*\d+$", "", series_name).strip()
    if stripped_vol != series_name:
        sid = lookup_series(db, stripped_vol, year)
        if sid:
            return sid, "stripped_vol"

    stripped_pub = re.sub(r"\s*\([^)]+\)$", "", stripped_vol).strip()
    if stripped_pub != stripped_vol:
        sid = lookup_series(db, stripped_pub, year)
        if sid:
            return sid, "stripped_pub"

    stripped_the = re.sub(r"^The\s+", "", stripped_pub, flags=re.IGNORECASE).strip()
    if stripped_the != stripped_pub:
        sid = lookup_series(db, stripped_the, year)
        if sid:
            return sid, "stripped_the"

    stripped_suffix = re.sub(
        r"\s+(Annual|Special|HC|TP|Omnibus|TPB)(\s.*)?$",
        "",
        stripped_the,
        flags=re.IGNORECASE,
    ).strip()
    if stripped_suffix != stripped_the:
        sid = lookup_series(db, stripped_suffix, year)
        if sid:
            return sid, "stripped_suffix"

    normalized = normalize_series_name(series_name)
    if normalized not in (stripped_vol, stripped_pub, stripped_the, stripped_suffix):
        sid = lookup_series(db, normalized, year)
        if sid:
            return sid, "normalized"

    # Additional normalization variations for punctuation
    variations = [
        re.sub(r":\s+", ", ", normalized),  # "B.P.R.D.: The" -> "B.P.R.D., The"
        re.sub(r"\s*&\s+", " and ", normalized),  # "&" -> " and "
        re.sub(r"\s+/\s+", " / ", normalized),  # Normalize "/"
    ]

    for variation in variations:
        if variation and variation != normalized:
            sid = lookup_series(db, variation, year)
            if sid:
                return sid, f"variation:{variation[:30]}"

    # Skip fuzzy matching for now - it's too slow
    # Just mark as no_series
    logger.warning(
        "No series found for %r (skipping fuzzy match for speed)", series_name
    )
    return None, "no_series"


def fmt_row(row: dict) -> str:
    return f"series={row['Series']!r} issue={row['Issue Nr']!r} cover_date={row['Cover Date']!r}"


def enrich_clz_row(db: sqlite3.Connection, row: dict, series_id: int) -> dict:
    raw_issue_nr = row["Issue Nr"].strip()
    if not raw_issue_nr:
        logger.warning("Empty Issue Nr: %s", fmt_row(row))
        return {
            **row,
            "gcd_issue_id": None,
            "gcd_url": None,
            "gcd_match_type": "no_issue_nr",
        }

    try:
        issue_nr = str(int(raw_issue_nr))
    except ValueError:
        logger.warning("Non-integer Issue Nr: %s", fmt_row(row))
        return {
            **row,
            "gcd_issue_id": None,
            "gcd_url": None,
            "gcd_match_type": "bad_issue_nr",
        }

    # Try barcode matching first (highest confidence)
    barcode = row.get("Barcode", "").strip()
    if barcode and barcode not in ("", "00000000000000"):
        barcode_match = db.execute(
            """
            SELECT id FROM gcd_issue
            WHERE barcode = ?
              AND deleted = 0
            LIMIT 1
        """,
            (barcode,),
        ).fetchone()
        if barcode_match:
            return {
                **row,
                "gcd_issue_id": barcode_match["id"],
                "gcd_url": f"https://www.comics.org/issue/{barcode_match['id']}/",
                "gcd_match_type": "barcode",
            }

    # Debug logging for Majestic
    if "Majestic" in row.get("Series", ""):
        logger.info(
            "DEBUG: series=%s issue=%s series_id=%s issue_nr=%s",
            row.get("Series"),
            raw_issue_nr,
            series_id,
            issue_nr,
        )

    newsstand = db.execute(
        """
        SELECT id FROM gcd_issue
        WHERE series_id = ?
          AND number = ?
          AND variant_name = 'Newsstand'
          AND deleted = 0
        LIMIT 1
    """,
        (series_id, issue_nr),
    ).fetchone()

    if newsstand:
        gcd_issue_id = newsstand["id"]
        match_type = "newsstand"
    else:
        canonical = db.execute(
            """
            SELECT id FROM gcd_issue
            WHERE series_id = ?
              AND number = ?
              AND variant_of_id IS NULL
              AND deleted = 0
        LIMIT 1
    """,
            (series_id, issue_nr),
        ).fetchone()

        if canonical:
            gcd_issue_id = canonical["id"]
            match_type = "canonical"
        else:
            gcd_issue_id = None
            match_type = "no_match"
            logger.warning("No GCD match: %s", fmt_row(row))

    return {
        **row,
        "gcd_issue_id": gcd_issue_id,
        "gcd_url": f"https://www.comics.org/issue/{gcd_issue_id}/"
        if gcd_issue_id
        else None,
        "gcd_match_type": match_type,
    }


def no_series_result(row: dict, reason: str = "no_series") -> dict:
    return {
        **row,
        "gcd_issue_id": None,
        "gcd_url": None,
        "gcd_match_type": reason,
    }


def load_existing_output(output_path: str) -> dict[str, dict]:
    path = Path(output_path)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["Core ComicID"]: row for row in reader}


def main():
    parser = argparse.ArgumentParser(description="Match CLZ comics to GCD database")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess all rows, ignoring existing output",
    )
    args = parser.parse_args()

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        clz_rows = list(reader)
    logger.info("Loaded %d rows from %s", len(clz_rows), CSV_PATH)

    if args.force:
        logger.info("Force mode: reprocessing all rows")
        pending = clz_rows
    else:
        existing = load_existing_output(OUTPUT_PATH)
        logger.info("Found %d already-processed rows in %s", len(existing), OUTPUT_PATH)
        pending = [r for r in clz_rows if r["Core ComicID"] not in existing]

    logger.info("Rows to enrich: %d", len(pending))

    if not pending:
        logger.info("Nothing to do")
        return

    fuzzy_cache = load_fuzzy_cache(FUZZY_CACHE_PATH)
    logger.info(
        "Loaded %d fuzzy cache entries from %s", len(fuzzy_cache), FUZZY_CACHE_PATH
    )

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    logger.info("Ensuring indexes")
    ensure_indexes(db)

    logger.info("Loading all GCD series names for fuzzy matching")
    all_series_names = get_all_series_names(db)

    # Build series cache with language and date filters
    unique_series_names = list({row["Series Group"] for row in pending})
    logger.info(
        "Resolving %d unique series (using Series Group, English, 1950-2026)",
        len(unique_series_names),
    )
    series_cache: dict[tuple[str, int | None], tuple[int | None, str]] = {}
    for name in tqdm(unique_series_names, desc="Series lookup"):
        series_cache[(name, None)] = get_series_id(
            db, name, all_series_names, fuzzy_cache
        )
        save_fuzzy_cache(FUZZY_CACHE_PATH, fuzzy_cache)

    out_fieldnames = list(fieldnames or []) + [
        "gcd_issue_id",
        "gcd_url",
        "gcd_match_type",
    ]
    output_exists = Path(OUTPUT_PATH).exists()

    n_newsstand = n_canonical = n_no_match = 0

    with open(OUTPUT_PATH, "a", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=out_fieldnames, extrasaction="ignore")
        if not output_exists:
            writer.writeheader()

        for row in tqdm(pending, desc="Enriching issues"):
            # Use cached series_id based on Series Group
            series_id, match_source = series_cache[(row["Series Group"], None)]
            if series_id is None:
                result = no_series_result(row, "no_series")
            else:
                result = enrich_clz_row(db, row, series_id)

            writer.writerow(result)
            out_f.flush()

            match_type = result["gcd_match_type"]
            if match_type == "newsstand":
                n_newsstand += 1
            elif match_type == "canonical":
                n_canonical += 1
            else:
                n_no_match += 1

    db.close()

    logger.info(
        "This run: Total=%d  Newsstand=%d  Canonical=%d  No match=%d",
        len(pending),
        n_newsstand,
        n_canonical,
        n_no_match,
    )


if __name__ == "__main__":
    main()
