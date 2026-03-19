"""CLI for GCD matching using round-robin strategy selection."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from collections import Counter

from .adapter import GCDLocalAdapter
from .service import GCDMatchingService
from .types import CLZInput

CSV_PATH = Path("/mnt/extra/josh/code/clz_export_all_columns.csv")
OUTPUT_PATH = Path(
    "/mnt/extra/josh/code/comic-identity-engine/clz_all_columns_enriched.csv"
)


def main():
    parser = argparse.ArgumentParser(description="Match CLZ comics to GCD database")
    parser.add_argument("--force", action="store_true", help="Reprocess all rows")
    parser.add_argument("--debug", action="store_true", help="Show top mismatches")
    parser.add_argument(
        "--report-fp",
        action="store_true",
        help="Report potential false positives (|gcd_cover_year - clz_year| > 2, non-barcode)",
    )
    args = parser.parse_args()

    # Load CLZ data
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        clz_rows = list(reader)
    print(f"Loaded {len(clz_rows)} rows from {CSV_PATH}")

    # Load existing output if not --force
    existing = {}
    if not args.force and OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing = {row["Core ComicID"]: row for row in reader}
        print(f"Found {len(existing)} already-processed rows")

    pending = [r for r in clz_rows if r["Core ComicID"] not in existing]
    print(f"Rows to enrich: {len(pending)}")

    if not pending:
        print("Nothing to do")
        if args.report_fp:
            _print_false_positive_report()
        return

    # Initialize adapter and service
    print("Loading GCD database...")
    adapter = GCDLocalAdapter()
    adapter.load()
    print(f"  {adapter.series_count} series, {adapter.issue_count} issues")

    service = GCDMatchingService(adapter)

    # Process rows
    stats = Counter()
    debug_rows = []

    fieldnames = list(clz_rows[0].keys()) + [
        "gcd_issue_id",
        "gcd_url",
        "gcd_match_type",
        "gcd_strategy",
        "gcd_series_id",
        "gcd_series_name",
        "gcd_cover_year",
    ]

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for i, row in enumerate(pending):
            clz_input = CLZInput.from_csv_row(row)
            result = service.match(clz_input)

            # Get series name for URL
            series_name = ""
            if result.gcd_series_id:
                info = adapter.get_series_info(result.gcd_series_id)
                series_name = info.get("name", "")

            gcd_url = (
                f"https://www.comics.org/issue/{result.gcd_issue_id}/"
                if result.gcd_issue_id
                else None
            )

            match_type = (
                f"{result.strategy_name}:{result.confidence.name}"
                if result.is_match()
                else "no_match"
            )

            out_row = {
                **row,
                "gcd_issue_id": result.gcd_issue_id,
                "gcd_url": gcd_url,
                "gcd_match_type": match_type,
                "gcd_strategy": result.strategy_name,
                "gcd_series_id": result.gcd_series_id,
                "gcd_series_name": series_name,
                "gcd_cover_year": (
                    adapter.get_issue_cover_year(
                        result.gcd_series_id, clz_input.issue_nr
                    )
                    if result.gcd_series_id
                    else None
                ),
            }

            writer.writerow(out_row)

            if result.strategy_name:
                stats[result.strategy_name] += 1
            else:
                stats["no_match"] += 1

            # Debug: collect mismatches
            if args.debug and result.is_match() and clz_input.year:
                cy = (
                    adapter.get_issue_cover_year(
                        result.gcd_series_id, clz_input.issue_nr
                    )
                    if result.gcd_series_id
                    else None
                )
                if cy and abs(cy - clz_input.year) >= 5:
                    debug_rows.append(
                        {
                            "id": clz_input.comic_id,
                            "series": clz_input.series_name,
                            "issue": clz_input.issue_nr,
                            "clz_year": clz_input.year,
                            "gcd_year": cy,
                            "strategy": result.strategy_name,
                            "gap": cy - clz_input.year,
                        }
                    )

            if (i + 1) % 500 == 0:
                print(f"  Processed {i + 1}/{len(pending)}...")

    print("\n" + "=" * 80)
    print("RESULTS:")
    print("=" * 80)
    for strategy, count in stats.most_common():
        print(f"  {strategy:30s} {count:5d}")

    if args.debug and debug_rows:
        print("\n" + "=" * 80)
        print("YEAR MISMATCHES (gap >= 5):")
        print("=" * 80)
        for row in sorted(debug_rows, key=lambda x: -abs(x["gap"]))[:20]:
            print(
                f"  {row['series'][:40]:40s} #{row['issue']:6s} CLZ:{row['clz_year']} GCD:{row['gcd_year']} ({row['gap']:+d}) [{row['strategy']}]"
            )

    if args.report_fp:
        _print_false_positive_report()


def _print_false_positive_report() -> None:
    fp_rows = []
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                strategy = row.get("gcd_strategy", "")
                if not strategy or strategy == "no_match" or "barcode" in strategy:
                    continue
                clz_year_str = row.get("Cover Year", "")
                gcd_year_str = row.get("gcd_cover_year", "")
                if not clz_year_str or not gcd_year_str:
                    continue
                try:
                    clz_year = int(float(clz_year_str))
                    gcd_year = int(float(gcd_year_str))
                except (ValueError, TypeError):
                    continue
                gap = gcd_year - clz_year
                if abs(gap) > 2:
                    fp_rows.append(
                        {
                            "id": row.get("Core ComicID", ""),
                            "series": row.get("Series", ""),
                            "issue": row.get("Issue Nr", ""),
                            "clz_year": clz_year,
                            "gcd_year": gcd_year,
                            "strategy": strategy,
                            "gap": gap,
                        }
                    )
    print("\n" + "=" * 80)
    print(f"POTENTIAL FALSE POSITIVES (|gap| > 2, non-barcode): {len(fp_rows)}")
    print("=" * 80)
    for row in sorted(fp_rows, key=lambda x: -abs(x["gap"]))[:50]:
        print(
            f"  {row['series'][:40]:40s} #{row['issue']:6s} CLZ:{row['clz_year']} GCD:{row['gcd_year']} ({row['gap']:+d}) [{row['strategy']}]"
        )


if __name__ == "__main__":
    main()
