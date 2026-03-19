import argparse
import csv
import sqlite3
import re
from collections import Counter
from pathlib import Path
from tqdm import tqdm

DB_PATH = "/mnt/bigdata/downloads/2026-03-15.db"
CSV_PATH = "../clz_export_all_columns.csv"
OUTPUT_PATH = "./clz_all_columns_enriched.csv"


def load_barcodes(db: sqlite3.Connection) -> dict[str, int]:
    result = db.execute(
        "SELECT barcode, id FROM gcd_issue WHERE barcode IS NOT NULL AND deleted = 0"
    ).fetchall()
    return {row["barcode"]: row["id"] for row in result}


def load_series(
    db: sqlite3.Connection,
) -> tuple[dict[str, list[dict]], dict[int, dict]]:
    rows = db.execute(
        """
        SELECT name, id, year_began, year_ended, issue_count
        FROM gcd_series
        WHERE deleted = 0
          AND language_id = 25
          AND year_began BETWEEN 1950 AND 2026
    """
    ).fetchall()

    series_map: dict[str, list[dict]] = {}
    series_id_to_info: dict[int, dict] = {}
    for row in rows:
        name = row["name"].lower()
        series_info = {
            "id": row["id"],
            "name": row["name"],
            "year_began": row["year_began"],
            "year_ended": row["year_ended"],
            "issue_count": row["issue_count"],
        }
        series_id_to_info[row["id"]] = series_info
        if name not in series_map:
            series_map[name] = []
        series_map[name].append(series_info)

    return series_map, series_id_to_info


def load_issues(
    db: sqlite3.Connection,
) -> tuple[
    dict[tuple[int, str], tuple[int, str]], dict[int, list[tuple[int, int, str]]]
]:
    rows = db.execute(
        """
        SELECT series_id, number, id, key_date,
               CASE WHEN variant_name = 'Newsstand' THEN 'newsstand'
                    WHEN variant_of_id IS NULL THEN 'canonical'
                    ELSE 'variant' END as match_type
        FROM gcd_issue
        WHERE deleted = 0
    """
    ).fetchall()

    issue_map: dict[tuple[int, str], tuple[int, str]] = {}
    year_to_issues: dict[int, list[tuple[int, int, str]]] = {}

    for row in rows:
        key = (row["series_id"], row["number"])
        existing = issue_map.get(key)

        if not existing:
            issue_map[key] = (row["id"], row["match_type"])
        else:
            existing_type = existing[1]
            new_type = row["match_type"]
            if existing_type == "variant" or (
                existing_type == "canonical" and new_type == "newsstand"
            ):
                issue_map[key] = (row["id"], row["match_type"])

        # Build year index for reverse lookup
        key_date = row["key_date"]
        if key_date:
            try:
                year = int(key_date.split("-")[0])
                if 1950 <= year <= 2026:
                    if year not in year_to_issues:
                        year_to_issues[year] = []
                    year_to_issues[year].append(
                        (row["series_id"], row["id"], row["number"])
                    )
            except (ValueError, IndexError):
                pass

    return issue_map, year_to_issues


def normalize_series_name(name: str) -> str:
    if not name:
        return ""

    # Remove publisher parentheticals: "(Marvel)", "(Cartoon Books)", etc.
    name = re.sub(r"\s*\([^)]*\)$", "", name)

    # Remove volume info: ", Vol. 1", ", Volume 2", etc.
    name = re.sub(r",\s*Vol\.\s*\d+$", "", name, flags=re.IGNORECASE)
    name = re.sub(r",\s*Volume\s*\d+$", "", name, flags=re.IGNORECASE)

    # Remove extra suffixes like "II", "III" if they're separate words
    # But be careful not to remove "II" from names like "Batman II"
    name = re.sub(r"\s+II\s*$", "", name)
    name = re.sub(r"\s+III\s*$", "", name)

    return name.strip()


def parse_year(row: dict) -> int | None:
    year_str = row.get("Cover Year", "").strip()
    if not year_str or not year_str.isdigit():
        return None
    year = int(year_str)
    return year if 1950 <= year <= 2026 else None


def parse_issue_nr(row: dict) -> str | None:
    issue_nr = row["Issue Nr"].strip()

    if not issue_nr:
        return "1"

    try:
        return str(int(issue_nr))
    except ValueError:
        return None


def find_series_candidates(
    series_map: dict[str, list[dict]], series_name: str, year: int | None
) -> list[dict]:
    name_lower = series_name.lower()
    candidates = []
    seen = set()

    def add_candidates(new_candidates):
        nonlocal candidates, seen
        for c in new_candidates:
            if c["id"] not in seen:
                seen.add(c["id"])
                candidates.append(c)

    # 1. Try exact match
    add_candidates(series_map.get(name_lower, []))

    # 2. Try with/without "The" prefix
    if name_lower.startswith("the "):
        add_candidates(series_map.get(name_lower[4:], []))
    else:
        add_candidates(series_map.get(f"the {name_lower}", []))

    # 3. Try removing other common articles ("a", "an") from beginning
    for article in ["a ", "an "]:
        if name_lower.startswith(article):
            add_candidates(series_map.get(name_lower[len(article) :], []))
            break

    # 4. If still no candidates and name is long enough, try substring matching
    if not candidates and len(name_lower) > 5:
        # Remove common articles from search string for matching
        search_terms = name_lower
        for prefix in ["the ", "a ", "an "]:
            if search_terms.startswith(prefix):
                search_terms = search_terms[len(prefix) :]
                break

        # Also try removing common suffixes like " the"
        search_terms_clean = search_terms.rstrip(" the")
        if search_terms_clean != search_terms:
            search_terms = search_terms_clean

        # Find series that contain our search terms or vice versa
        for series_key, series_list in series_map.items():
            if search_terms in series_key or series_key in search_terms:
                add_candidates(series_list)

    # 5. Date-based fallback: if still no candidates and we have a year, try broader search
    if not candidates and year is not None:
        for series_list in series_map.values():
            for series in series_list:
                if series["year_began"] <= year <= (series["year_ended"] or year + 20):
                    add_candidates([series])

    if not candidates:
        return []

    if year is None:
        return sorted(candidates, key=lambda x: -x["issue_count"])

    # Score each series by how likely it is
    scored = []
    for series in candidates:
        score = 0

        # Penalize heavily if series doesn't include this year
        if series["year_ended"] and series["year_ended"] < year:
            score -= 1000
        if series["year_began"] > year + 5:
            score -= 1000

        # Prefer series that started close to this year
        score -= abs(series["year_began"] - year)

        # Prefer series with more issues (more popular/mainstream)
        score += series["issue_count"] / 10

        scored.append((score, series))

    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored]


def find_issues_by_number_and_year(
    issue_map: dict[tuple[int, str], tuple[int, str]],
    issue_nr: str,
    year: int | None,
    year_to_issues: dict[int, list[tuple[int, int, str]]],
) -> list[tuple[int, int]]:
    """
    Reverse lookup: Find all issues with a given issue number, optionally filtered by year.
    Returns list of (series_id, gcd_issue_id) tuples.
    """
    if year is not None:
        # Get all issues from this year (±5 years)
        candidates = []
        for y in range(max(1950, year - 5), min(2026, year + 6)):
            if y in year_to_issues:
                for series_id, issue_id, issue_num in year_to_issues[y]:
                    if issue_num == issue_nr:
                        candidates.append((series_id, issue_id))
        return candidates
    else:
        # No year filter, return all issues with this number from all years
        candidates = []
        for y in range(1950, 2027):
            if y in year_to_issues:
                for series_id, issue_id, issue_num in year_to_issues[y]:
                    if issue_num == issue_nr:
                        candidates.append((series_id, issue_id))
        return candidates


def similarity_score(s1: str, s2: str) -> float:
    """Simple similarity score based on common substrings."""
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2:
        return 1.0
    if s1 in s2 or s2 in s1:
        return 0.8
    # Count common words
    words1 = set(s1.split())
    words2 = set(s2.split())
    if words1 and words2:
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0
    return 0.0


def find_best_series_id(
    series_map: dict[str, list[dict]],
    series_id_to_info: dict[int, dict],
    issue_map: dict[tuple[int, str], tuple[int, str]],
    series_name: str,
    issue_nr: str,
    year: int | None,
    year_to_issues: dict[int, list[tuple[int, int, str]]] | None = None,
) -> tuple[int | None, str]:
    candidates = find_series_candidates(series_map, series_name, year)

    if not candidates:
        # FALLBACK: Try reverse lookup by issue number and year
        # This helps when series name is wrong but issue exists in GCD
        if year_to_issues is not None and year is not None:
            reverse_matches = find_issues_by_number_and_year(
                issue_map, issue_nr, year, year_to_issues
            )
            if reverse_matches:
                # Get unique series IDs
                unique_series = list(set(series_id for series_id, _ in reverse_matches))
                if len(unique_series) == 1:
                    # Only one series has this issue from this year - use it!
                    series_id = unique_series[0]
                    series_info = series_id_to_info.get(series_id)
                    if series_info:
                        return (
                            series_id,
                            f"reverse_lookup_issue_year:{series_info['name']}",
                        )
                elif len(unique_series) > 1:
                    # Multiple series have this issue from this year
                    # Pick the one with series name closest to our search
                    best_series_id = None
                    best_similarity = 0
                    for series_id in unique_series:
                        series_info = series_id_to_info.get(series_id)
                        if series_info:
                            similarity = similarity_score(
                                series_name.lower(), series_info["name"].lower()
                            )
                            if similarity > best_similarity:
                                best_similarity = similarity
                                best_series_id = series_id
                    if best_series_id:
                        series_info = series_id_to_info[best_series_id]
                        return (
                            best_series_id,
                            f"reverse_lookup_closest_name:{series_info['name']}",
                        )

        return None, "no_series"

    # If only one candidate, use it (skip date filtering)
    if len(candidates) == 1:
        return candidates[0]["id"], "only_series"

    # Date-aware matching: filter candidates by date range first (only if multiple candidates)
    if year is not None and len(candidates) > 1:
        date_filtered = []
        for series in candidates:
            # Check if series was active when comic was published
            # More lenient: widened window from ±2 to ±5 years
            if series["year_began"] > year + 5:
                continue  # Series started too late
            if series["year_ended"] and series["year_ended"] < year - 5:
                continue  # Series ended too early
            date_filtered.append(series)

        # If we have date-filtered candidates, use them instead of all candidates
        if date_filtered:
            candidates = date_filtered

    # Check if issue exists in each candidate series
    candidates_with_issue = []
    for series in candidates:
        issue_key = (series["id"], issue_nr)
        if issue_key in issue_map:
            candidates_with_issue.append(series)

    if len(candidates_with_issue) == 1:
        return candidates_with_issue[0]["id"], "only_one_with_issue"

    if len(candidates_with_issue) > 1:
        # Multiple series have this issue - pick the one with closest year
        if year is not None:
            candidates_with_issue.sort(key=lambda s: abs(s["year_began"] - year))
            return candidates_with_issue[0]["id"], "closest_year_with_issue"
        return candidates_with_issue[0]["id"], "multiple_with_issue"

    # No series has this issue - try reverse lookup as fallback
    if year_to_issues is not None and year is not None:
        reverse_matches = find_issues_by_number_and_year(
            issue_map, issue_nr, year, year_to_issues
        )
        if reverse_matches:
            # Get unique series IDs
            unique_series = list(set(series_id for series_id, _ in reverse_matches))
            if len(unique_series) == 1:
                # Only one series has this issue from this year - use it!
                series_id = unique_series[0]
                series_info = series_id_to_info.get(series_id)
                if series_info:
                    return (
                        series_id,
                        f"reverse_lookup_issue_year:{series_info['name']}",
                    )
            elif len(unique_series) > 1:
                # Multiple series have this issue from this year
                # Pick the one with series name closest to our search
                best_series_id = None
                best_similarity = 0
                for series_id in unique_series:
                    series_info = series_id_to_info.get(series_id)
                    if series_info:
                        similarity = similarity_score(
                            series_name.lower(), series_info["name"].lower()
                        )
                        if similarity > best_similarity:
                            best_similarity = similarity
                            best_series_id = series_id
                if best_series_id:
                    series_info = series_id_to_info[best_series_id]
                    return (
                        best_series_id,
                        f"reverse_lookup_closest_name:{series_info['name']}",
                    )

    # No series has this issue - pick the best candidate anyway
    best = candidates[0]
    return best["id"], f"no_issue_in_{len(candidates)}_series"


def load_existing_output(output_path: str) -> dict[str, dict]:
    path = Path(output_path)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["Core ComicID"]: row for row in reader}


def main():
    parser = argparse.ArgumentParser(description="Match CLZ comics to GCD database")
    parser.add_argument("--force", action="store_true", help="Reprocess all rows")
    args = parser.parse_args()

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        clz_rows = list(reader)
    print(f"Loaded {len(clz_rows)} rows from {CSV_PATH}")

    if args.force:
        pending = clz_rows
    else:
        existing = load_existing_output(OUTPUT_PATH)
        print(f"Found {len(existing)} already-processed rows")
        pending = [r for r in clz_rows if r["Core ComicID"] not in existing]

    print(f"Rows to enrich: {len(pending)}")

    if not pending:
        print("Nothing to do")
        return

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    print("Loading barcode mappings...")
    barcode_map = load_barcodes(db)
    print(f"Loaded {len(barcode_map)} barcodes")

    print("Loading series mappings...")
    series_map, series_id_to_info = load_series(db)
    print(
        f"Loaded {sum(len(v) for v in series_map.values())} series in {len(series_map)} unique names"
    )
    print(f"Built series ID index with {len(series_id_to_info)} series")

    print("Loading issue mappings...")
    issue_map, year_to_issues = load_issues(db)
    print(f"Loaded {len(issue_map)} issues")
    print(f"Built year index with {len(year_to_issues)} years")

    db.close()

    out_fieldnames = list(fieldnames or []) + [
        "gcd_issue_id",
        "gcd_url",
        "gcd_match_type",
    ]

    stats = Counter()

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=out_fieldnames, extrasaction="ignore")
        writer.writeheader()

        for row in tqdm(pending, desc="Enriching"):
            barcode = row.get("Barcode", "").strip()

            gcd_issue_id = None
            match_type = None

            # Try barcode matching
            if barcode and barcode != "00000000000000":
                gcd_issue_id = barcode_map.get(barcode)
                if gcd_issue_id:
                    match_type = "barcode"
                else:
                    # Try prefix match for ISBNs (GCD adds suffix like "54499")
                    for bc_key, bc_id in barcode_map.items():
                        if bc_key.startswith(barcode) or barcode.startswith(
                            bc_key[:13]
                        ):
                            gcd_issue_id = bc_id
                            match_type = "barcode_prefix"
                            break

            # Fall back to series/issue matching
            if not gcd_issue_id:
                issue_nr = parse_issue_nr(row)
                if not issue_nr:
                    match_type = "bad_issue_nr"
                else:
                    year = parse_year(row)

                    # Try Series Group first, but check if it's too generic
                    series_group = row.get("Series Group", "").strip()
                    series_name = (
                        series_group
                        if series_group
                        else normalize_series_name(row.get("Series", ""))
                    )

                    series_id, series_match = find_best_series_id(
                        series_map,
                        series_id_to_info,
                        issue_map,
                        series_name,
                        issue_nr,
                        year,
                        year_to_issues,
                    )

                    # If Series Group returned candidates but no match, retry with full Series name
                    if (
                        series_group
                        and series_match.startswith("no_issue_in_")
                        and series_id
                    ):
                        # Extract candidate count from "no_issue_in_5_series"
                        parts = series_match.split("_")
                        if len(parts) >= 4:
                            try:
                                candidate_count = int(
                                    parts[3]
                                )  # "no_issue_in_5_series" -> 5
                                if candidate_count > 0:
                                    # Retry with full Series name (with volume stripped)
                                    series_name = normalize_series_name(
                                        row.get("Series", "")
                                    )
                                    series_id, series_match = find_best_series_id(
                                        series_map,
                                        series_id_to_info,
                                        issue_map,
                                        series_name,
                                        issue_nr,
                                        year,
                                        year_to_issues,
                                    )
                                    series_match = f"{series_match}_fallback_from_group"
                            except ValueError:
                                pass

                    if not series_id:
                        match_type = f"no_series:{series_match}"
                    else:
                        issue_key = (series_id, issue_nr)
                        issue_result = issue_map.get(issue_key)
                        if issue_result:
                            gcd_issue_id, issue_match = issue_result
                            match_type = f"{series_match}:{issue_match}"
                        else:
                            match_type = f"{series_match}:no_issue"

            result = {
                **row,
                "gcd_issue_id": gcd_issue_id,
                "gcd_url": f"https://www.comics.org/issue/{gcd_issue_id}/"
                if gcd_issue_id
                else None,
                "gcd_match_type": match_type or "unknown",
            }

            writer.writerow(result)
            out_f.flush()

            if match_type:
                stats[match_type.split(":")[0]] += 1

    print("\n" + "=" * 80)
    print("RESULTS:")
    print("=" * 80)
    for match_type, count in stats.most_common():
        print(f"  {match_type:30s} {count:5d}")


if __name__ == "__main__":
    main()
