import argparse
import csv
import sqlite3
import logging
from pathlib import Path
from tqdm import tqdm

DB_PATH = "/mnt/bigdata/downloads/2026-03-15.db"
CSV_PATH = "../clz_export_all_columns.csv"
OUTPUT_PATH = "./clz_all_columns_enriched.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def fmt_row(row: dict) -> str:
    return (
        f"series={row.get('Series Group', row['Series'])!r} issue={row['Issue Nr']!r}"
    )


def barcode_match(db: sqlite3.Connection, barcode: str) -> int | None:
    if not barcode or barcode in ("", "00000000000000"):
        return None
    result = db.execute(
        "SELECT id FROM gcd_issue WHERE barcode = ? AND deleted = 0 LIMIT 1",
        (barcode,),
    ).fetchone()
    return result["id"] if result else None


def find_series_id(
    db: sqlite3.Connection, series_name: str, year: int | None
) -> int | None:
    if year:
        result = db.execute(
            """
            SELECT id FROM gcd_series
            WHERE name = ? COLLATE NOCASE
              AND deleted = 0
              AND language_id = 25
              AND year_began BETWEEN (?) AND (?)
            ORDER BY issue_count DESC
            LIMIT 1
            """,
            (series_name, year - 2, year + 2),
        ).fetchone()
        if result:
            return result["id"]

    result = db.execute(
        """
        SELECT id FROM gcd_series
        WHERE name = ? COLLATE NOCASE
          AND deleted = 0
          AND language_id = 25
          AND year_began BETWEEN 1950 AND 2026
        ORDER BY issue_count DESC
        LIMIT 1
        """,
        (series_name,),
    ).fetchone()
    return result["id"] if result else None


def find_issue_id(
    db: sqlite3.Connection, series_id: int, issue_nr: str
) -> tuple[int | None, str]:
    newsstand = db.execute(
        """
        SELECT id FROM gcd_issue
        WHERE series_id = ? AND number = ? AND variant_name = 'Newsstand' AND deleted = 0
        LIMIT 1
        """,
        (series_id, issue_nr),
    ).fetchone()

    if newsstand:
        return newsstand["id"], "newsstand"

    canonical = db.execute(
        """
        SELECT id FROM gcd_issue
        WHERE series_id = ? AND number = ? AND variant_of_id IS NULL AND deleted = 0
        LIMIT 1
        """,
        (series_id, issue_nr),
    ).fetchone()

    if canonical:
        return canonical["id"], "canonical"

    return None, "no_match"


def load_existing_output(output_path: str) -> dict[str, dict]:
    path = Path(output_path)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["Core ComicID"]: row for row in reader}


def parse_year(row: dict) -> int | None:
    year_str = row.get("Cover Year", "").strip()
    if not year_str or not year_str.isdigit():
        return None
    year = int(year_str)
    return year if 1950 <= year <= 2026 else None


def parse_issue_nr(row: dict) -> str | None:
    issue_nr = row["Issue Nr"].strip()
    if not issue_nr:
        logger.warning("Empty Issue Nr: %s", fmt_row(row))
        return None
    try:
        return str(int(issue_nr))
    except ValueError:
        logger.warning("Non-integer Issue Nr: %s", fmt_row(row))
        return None


def main():
    parser = argparse.ArgumentParser(description="Match CLZ comics to GCD database")
    parser.add_argument("--force", action="store_true", help="Reprocess all rows")
    args = parser.parse_args()

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        clz_rows = list(reader)
    logger.info("Loaded %d rows from %s", len(clz_rows), CSV_PATH)

    if args.force:
        pending = clz_rows
    else:
        existing = load_existing_output(OUTPUT_PATH)
        logger.info("Found %d already-processed rows", len(existing))
        pending = [r for r in clz_rows if r["Core ComicID"] not in existing]

    logger.info("Rows to enrich: %d", len(pending))

    if not pending:
        logger.info("Nothing to do")
        return

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    out_fieldnames = list(fieldnames or []) + [
        "gcd_issue_id",
        "gcd_url",
        "gcd_match_type",
    ]

    stats = {
        "barcode": 0,
        "newsstand": 0,
        "canonical": 0,
        "no_match": 0,
        "no_series": 0,
        "bad_issue_nr": 0,
    }

    with open(OUTPUT_PATH, "a", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=out_fieldnames, extrasaction="ignore")
        if not Path(OUTPUT_PATH).exists():
            writer.writeheader()

        for row in tqdm(pending, desc="Enriching"):
            barcode = row.get("Barcode", "").strip()

            gcd_issue_id = None
            match_type = None

            if barcode and barcode != "00000000000000":
                gcd_issue_id = barcode_match(db, barcode)
                if gcd_issue_id:
                    match_type = "barcode"

            if not gcd_issue_id:
                issue_nr = parse_issue_nr(row)
                if not issue_nr:
                    match_type = "bad_issue_nr"
                else:
                    series_name = row.get("Series Group", row["Series"]).strip()
                    year = parse_year(row)

                    series_id = find_series_id(db, series_name, year)
                    if not series_id:
                        match_type = "no_series"
                    else:
                        gcd_issue_id, match_type = find_issue_id(
                            db, series_id, issue_nr
                        )

            result = {
                **row,
                "gcd_issue_id": gcd_issue_id,
                "gcd_url": f"https://www.comics.org/issue/{gcd_issue_id}/"
                if gcd_issue_id
                else None,
                "gcd_match_type": match_type,
            }

            writer.writerow(result)
            out_f.flush()

            stats[match_type] += 1

    db.close()

    logger.info(
        "Results: Barcode=%d  Newsstand=%d  Canonical=%d  No match=%d",
        stats["barcode"],
        stats["newsstand"],
        stats["canonical"],
        sum(
            v
            for k, v in stats.items()
            if k not in ["barcode", "newsstand", "canonical"]
        ),
    )


if __name__ == "__main__":
    main()
