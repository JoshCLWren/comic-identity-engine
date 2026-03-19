import argparse
import csv
import sqlite3
import re
import unicodedata
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
          AND year_began <= 2026
          AND (year_ended IS NULL OR year_ended >= 1950)
    """
    ).fetchall()

    series_map: dict[str, list[dict]] = {}
    series_id_to_info: dict[int, dict] = {}
    for row in rows:
        name = strip_diacritics(row["name"]).lower()
        name_strict = normalize_series_name_strict(name)
        series_info = {
            "id": row["id"],
            "name": row["name"],
            "name_strict": name_strict,
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
    dict[tuple[int, str], tuple[int, str]],
    dict[int, list[tuple[int, int, str]]],
    dict[tuple[int, str], int],
]:
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

    issue_map: dict[tuple[int, str], tuple[int, str]] = {}
    year_to_issues: dict[int, list[tuple[int, int, str]]] = {}
    issue_cover_year: dict[tuple[int, str], int] = {}

    for row in rows:
        key = (row["series_id"], row["number"])
        existing = issue_map.get(key)

        # Parse cover year from publication_date (the actual cover date, not GCD's key_date).
        # Falls back to key_date if publication_date is absent.
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
            issue_map[key] = (row["id"], row["match_type"])
            if cover_year is not None:
                issue_cover_year[key] = cover_year
        else:
            existing_type = existing[1]
            new_type = row["match_type"]
            if existing_type == "variant" or (
                existing_type == "canonical" and new_type == "newsstand"
            ):
                issue_map[key] = (row["id"], row["match_type"])
                if cover_year is not None:
                    issue_cover_year[key] = cover_year

        # Build year index for reverse lookup
        if cover_year is not None and 1950 <= cover_year <= 2026:
            if cover_year not in year_to_issues:
                year_to_issues[cover_year] = []
            year_to_issues[cover_year].append(
                (row["series_id"], row["id"], row["number"])
            )

    return issue_map, year_to_issues, issue_cover_year


def strip_diacritics(text: str) -> str:
    """Normalize unicode diacritics so e.g. 'Rōnin' matches 'Ronin'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def normalize_series_name(name: str) -> str:
    if not name:
        return ""

    # Remove publisher parentheticals: "(Marvel)", "(Cartoon Books)", etc.
    name = re.sub(r"\s*\([^)]*\)$", "", name)

    # Remove volume info: ", Vol. 1", ", Volume 2", etc.
    # Handles both trailing (", Vol. 1") and mid-string (", Vol. 1 Annual") patterns.
    name = re.sub(r",\s*Vol\.\s*\d+(\s+|$)", " ", name, flags=re.IGNORECASE).strip()
    name = re.sub(r",\s*Volume\s+\d+(\s+|$)", " ", name, flags=re.IGNORECASE).strip()

    # Remove extra suffixes like "II", "III" if they're separate words
    # But be careful not to remove "II" from names like "Batman II"
    name = re.sub(r"\s+II\s*$", "", name)
    name = re.sub(r"\s+III\s*$", "", name)

    return name.strip()


def normalize_series_name_strict(name: str) -> str:
    """Strip all punctuation and normalize &/and for deep matching."""
    if not name:
        return ""
    name = normalize_series_name(name)
    name = name.lower()
    name = re.sub(r"&", "and", name)
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


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
    series_map: dict[str, list[dict]],
    series_id_to_info: dict[int, dict],
    series_name: str,
    year: int | None,
    issue_nr: str | None = None,
    issue_map: dict[tuple[int, str], tuple[int, str]] | None = None,
    issue_cover_year: dict[tuple[int, str], int] | None = None,
) -> list[dict]:
    name_lower = strip_diacritics(series_name).lower()
    name_strict = normalize_series_name_strict(name_lower)
    candidates = []
    seen = set()

    def add_candidates(new_candidates):
        nonlocal candidates, seen
        for c in new_candidates:
            if c["id"] not in seen:
                seen.add(c["id"])
                candidates.append(c)

    def add_from_strict_match():
        for series_key, series_list in series_map.items():
            if (
                series_id_to_info.get(series_list[0]["id"], {}).get("name_strict")
                == name_strict
            ):
                add_candidates(series_list)

    # 1. Try strict-normalized exact match (handles &/and, punctuation)
    add_from_strict_match()

    # 1a. Try exact match
    add_candidates(series_map.get(name_lower, []))

    # 1b. Try colon-to-comma variant: CLZ uses "Series A: Series B" but GCD may use
    #     "Series A, Series B" (e.g. "Doctor Strange: Sorcerer Supreme" vs
    #     "Doctor Strange, Sorcerer Supreme").
    comma_name = name_lower.replace(": ", ", ")
    if comma_name != name_lower:
        add_candidates(series_map.get(comma_name, []))

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

    # 3b. Word-set match: handles word-order variants ("X-Men Classic" vs "Classic X-Men").
    # Always run so we don't miss reversed-word series when direct lookup found wrong-era ones.
    search_words = set(name_lower.split())
    if len(search_words) >= 2:
        for series_key, series_list in series_map.items():
            if set(series_key.split()) == search_words and series_key != name_lower:
                add_candidates(series_list)

    # 4. If no candidates (or all existing ones are from the wrong era), try substring.
    # "All wrong era" = every candidate ended >5yr before or started >5yr after target year.
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

    def _series_year_score(series: dict) -> tuple[int, int]:
        if (
            issue_map is not None
            and issue_cover_year is not None
            and issue_nr is not None
        ):
            key = (series["id"], issue_nr)
            if key in issue_map:
                cy = issue_cover_year.get(key)
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

    score = 0.0

    if s1 in s2 or s2 in s1:
        shorter = s1 if len(s1) <= len(s2) else s2
        longer = s2 if len(s1) <= len(s2) else s1
        overlap = len(shorter)
        total = len(longer)
        # Prefix match: "supreme" is a title prefix of "supreme: the new adventures"
        # but not of "doctor strange, sorcerer supreme". Boost prefix matches so they
        # beat Jaccard's flat per-word score.
        if longer.startswith(shorter):
            score = max(score, min(0.9, 1.4 * overlap / total))
        else:
            score = max(score, 0.8 * overlap / total)

    # Word-overlap Jaccard (strip punctuation so "supreme:" == "supreme")
    def _words(s: str) -> set[str]:
        return {re.sub(r"[^\w-]", "", w) for w in s.split() if re.sub(r"[^\w-]", "", w)}

    words1 = _words(s1)
    words2 = _words(s2)
    if words1 and words2:
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        score = max(score, intersection / union if union > 0 else 0.0)

    return score


def find_best_series_id(
    series_map: dict[str, list[dict]],
    series_id_to_info: dict[int, dict],
    issue_map: dict[tuple[int, str], tuple[int, str]],
    series_name: str,
    issue_nr: str,
    year: int | None,
    year_to_issues: dict[int, list[tuple[int, int, str]]] | None = None,
    issue_cover_year: dict[tuple[int, str], int] | None = None,
) -> tuple[int | None, str]:
    candidates = find_series_candidates(
        series_map,
        series_id_to_info,
        series_name,
        year,
        issue_nr,
        issue_map,
        issue_cover_year,
    )

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
            if issue_cover_year is not None and issue_nr is not None:
                cy = issue_cover_year.get((series["id"], issue_nr))
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
        # Multiple series have this issue - pick the one whose actual issue cover
        # date is closest to the CLZ year (falls back to series year_began).
        if year is not None:

            def _issue_year_distance(s: dict) -> int:
                if issue_cover_year is not None:
                    cy = issue_cover_year.get((s["id"], issue_nr))
                    if cy is not None:
                        return abs(cy - year)
                return abs(s["year_began"] - year)

            candidates_with_issue.sort(key=_issue_year_distance)
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
    issue_map, year_to_issues, issue_cover_year = load_issues(db)
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

                    # Deprioritize Series Group: try Series name first, then Series Group.
                    # CLZ uses Series Group as a category grouping, not always the correct series name.
                    # "X-Men" SG can group "X-Men Classic", "Valor" SG points to wrong series.
                    series_name = normalize_series_name(row.get("Series", ""))
                    series_group = row.get("Series Group", "").strip()

                    series_id, series_match = find_best_series_id(
                        series_map,
                        series_id_to_info,
                        issue_map,
                        series_name,
                        issue_nr,
                        year,
                        year_to_issues,
                        issue_cover_year,
                    )

                    # If Issue field has a variant suffix that Issue Nr doesn't (e.g. "52A" vs "52"),
                    # retry with the full Issue field as the issue number.
                    issue_full = row.get("Issue", "").strip()
                    issue_nr_raw = row.get("Issue Nr", "").strip()
                    issue_nr_for_lookup = issue_nr
                    if (
                        not series_id
                        and issue_full
                        and issue_full != issue_nr_raw
                        and any(c.isalpha() for c in issue_full)
                        and not any(c.isalpha() for c in issue_nr_raw)
                    ):
                        issue_nr_alt = parse_issue_nr({"Issue Nr": issue_full})
                        if issue_nr_alt and issue_nr_alt != issue_nr:
                            series_id, series_match = find_best_series_id(
                                series_map,
                                series_id_to_info,
                                issue_map,
                                series_name,
                                issue_nr_alt,
                                year,
                                year_to_issues,
                                issue_cover_year,
                            )
                            if series_id:
                                series_match = f"{series_match}_from_issue_field"
                                issue_nr_for_lookup = issue_nr_alt

                    # If Series name found nothing, retry with Series Group as a fallback.
                    # CLZ uses SG as a category/grouping, not always the correct series name,
                    # so we only use it when the actual Series name fails.
                    if not series_id and series_group:
                        series_id, series_match = find_best_series_id(
                            series_map,
                            series_id_to_info,
                            issue_map,
                            series_group,
                            issue_nr,
                            year,
                            year_to_issues,
                            issue_cover_year,
                        )
                        if series_id:
                            series_match = f"{series_match}_from_series_group"

                    # Year-gap safety net: if we have a large gap (>6yr) and SG is available,
                    # try SG as a fallback to see if it finds the right series.
                    matched_cover_yr = (
                        issue_cover_year.get((series_id, issue_nr_for_lookup))
                        if series_id
                        else None
                    )
                    large_year_gap = (
                        matched_cover_yr is not None
                        and year is not None
                        and abs(matched_cover_yr - year) >= 6
                    )
                    if large_year_gap and series_group and series_id:
                        series_id_sg, series_match_sg = find_best_series_id(
                            series_map,
                            series_id_to_info,
                            issue_map,
                            series_group,
                            issue_nr_for_lookup,
                            year,
                            year_to_issues,
                            issue_cover_year,
                        )
                        if series_id_sg is not None:
                            sg_cyr = issue_cover_year.get(
                                (series_id_sg, issue_nr_for_lookup)
                            )
                            if (
                                sg_cyr is not None
                                and year is not None
                                and matched_cover_yr is not None
                            ):
                                if abs(sg_cyr - year) < abs(matched_cover_yr - year):
                                    series_id = series_id_sg
                                    series_match = (
                                        f"{series_match_sg}_fallback_from_series"
                                    )

                    if not series_id:
                        match_type = f"no_series:{series_match}"
                    else:
                        issue_key = (series_id, issue_nr_for_lookup)
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
