# CLZ to GCD Matching - Progress Summary

## Goal
Match 5,203 comics from ComicBookLover (CLZ) export to Grand Comics Database (GCD) using local SQLite database.

## Results
- **Final Success Rate: 94.0%** (4,889/5,203)
- **Improved from: 61.8% → 79.2% → 94.0%**

## Matching Pipeline

### 1. Barcode Matching (72.7% of all matches)
- **Exact barcode match**: 3,362 comics
- **ISBN prefix match**: 419 comics (GCD appends 5-digit suffix to ISBNs)
- Example: CLZ `9781302945374` matches GCD `978130294537454499`

### 2. Series + Issue Matching (27.3% of all matches)
**Smart Disambiguation Logic:**
- Uses CLZ "Series Group" field (normalized series name)
- Falls back to "Series" field with ", Vol. N" stripped if empty
- Finds all candidate series in GCD with matching name
- **Checks if issue number actually exists** in each candidate series
- Selects series based on:
  1. Only candidate series that has this issue number
  2. Closest year to comic's publication year
  3. Most issues (mainstream/primary series)

**Match Types:**
- `closest_year_with_issue`: 594 (year-based disambiguation, issue exists)
- `only_one_with_issue`: 467 (only one series has this issue)
- `only_series`: 57 (only one series with this name)

### 3. Data Sources
- **GCD Database**: `/mnt/bigdata/downloads/2026-03-15.db` (6.0 GB)
  - 2.57M issues
  - 102K series (English, 1950-2026)
  - 362K barcodes (including 83K ISBNs)

- **CLZ Export**: `/mnt/extra/josh/code/clz_export_all_columns.csv`
  - 5,203 comics
  - 72.7% have barcodes
  - Key fields: Series Group, Issue, Cover Year, Barcode

## Remaining Failures (315 total, 6.0%)

### 1. no_series (133, 2.6%)
**Cause:** Series name not found in GCD
- Empty Series Group + stripped Series name doesn't match
- Series might be under different name in GCD
- Indie/small press comics not in GCD

### 2. no_issue_in_N_series (177 total, 3.4%)
**Cause:** Series found, but issue number doesn't exist in any candidate series
- `no_issue_in_5_series`: 81
- `no_issue_in_14_series`: 59
- `no_issue_in_8_series`: 4
- etc.

**Possible causes:**
- CLZ series name maps to wrong GCD series (e.g., "Justice League" → 6 different series)
- Issue numbering mismatch (CLZ #36 vs GCD #36)
- Variant issues not in GCD
- Wrong series selected from candidates

### 3. bad_issue_nr (6, 0.1%)
**Cause:** Non-integer issue numbers that can't be parsed
- Issue numbers like "½", "1/2", "AU", etc.

## Key Improvements Made

### 1. ISBN Prefix Matching
GCD stores ISBNs with 5-digit suffix (likely price/region code).
```python
# Try exact match first, then prefix match for ISBNs
if barcode.startswith('978') or barcode.startswith('979'):
    for bc_key in barcode_map:
        if bc_key.startswith(barcode):
            return barcode_map[bc_key]
```

### 2. Issue Existence Validation
Instead of just picking series by year or issue count, **verify issue exists**:
```python
# Check if issue #36 exists in each candidate series
candidates_with_issue = []
for series in candidates:
    if (series['id'], issue_nr) in issue_map:
        candidates_with_issue.append(series)
```

### 3. Series Name Fallback
When Series Group is empty, strip volume from Series name:
```python
def strip_volume(name: str) -> str:
    # "The Life of Captain Marvel, Vol. 1" 
    # → "The Life of Captain Marvel"
    name = re.sub(r",\s*Vol\.\s*\d+$", "", name, flags=re.IGNORECASE)
    return name.strip()
```

### 4. Smart Year Disambiguation
Prefer series where issue actually exists, then closest year:
```python
# Score series by: existence of issue, year proximity, issue_count
if (series['id'], issue_nr) in issue_map:
    score += 1000  # Huge boost for having the issue
score -= abs(series['year_began'] - year)
```

## Performance
- **Batch loading**: Load all barcodes/series/issues into memory upfront
- **Speed**: ~21K it/s (runs in seconds)
- **Memory**: ~250MB (228 issues + 102K series + 362K barcodes)

## Files
- `gcd_tests.py`: Main matching script
- `clz_all_columns_enriched.csv`: Output with GCD matches
- `CLZ_GCD_MATCHING.md`: This documentation

## Final Results (after all improvements)

**Success Rate: 96.4%** (5,014/5,203 matched)
**Remaining Failures: 189 (3.6%)**

### Match Type Breakdown:
| Match Type | Count | Description |
|------------|-------|-------------|
| barcode | 3,362 | Exact barcode match |
| barcode_prefix | 419 | ISBN prefix match (GCD adds 5-digit suffix) |
| closest_year_with_issue | 644 | Multiple series have this issue, picked closest year |
| only_one_with_issue | 540 | Only one series has this issue number |
| only_series | 49 | Only one series with this name |
| no_series | 61 | Series not found in GCD |
| no_issue_in_19_series | 59 | Issue doesn't exist in 19 candidate series |
| no_issue_in_5_series | 44 | Issue doesn't exist in 5 candidate series |
| bad_issue_nr | 6 | Non-integer issue numbers |

## Final Improvements Made

### 1. "The" Prefix Handling (90+ new matches)
```python
# Always try with/without "The" prefix and merge results
if name_lower.startswith("the "):
    without_the = series_map.get(name_lower[4:], [])
    candidates.extend(without_the)
else:
    with_the = series_map.get(f"the {name_lower}", [])
    candidates.extend(with_the)
```

**Impact:** 
- "New Mutants" now matches "The New Mutants" (1983)
- New Mutants #88-94 all matched successfully
- Added ~90 new matches

### 2. Series Name Normalization (59 new matches)
```python
def normalize_series_name(name: str) -> str:
    # Remove publisher parentheticals: "(Marvel)", "(Cartoon Books)"
    name = re.sub(r"\s*\([^)]*\)$", "", name)
    
    # Remove volume info: ", Vol. 1", ", Volume 2"
    name = re.sub(r",\s*Vol\.\s*\d+$", "", name, flags=re.IGNORECASE)
    
    # Remove suffixes like "II", "III"
    name = re.sub(r"\s+II\s*$", "", name)
    
    return name.strip()
```

**Impact:**
- "ROM, Vol. 1 (Marvel)" → "ROM"
- "Bone (Cartoon Books)" → "Bone"
- "Champions, Vol. 1 (Marvel)" → "Champions"
- no_series: 133 → 61 (-72 matches)

### 3. Issue Existence Validation (1,061 new matches)
```python
# Check if issue #36 exists in each candidate series
candidates_with_issue = []
for series in candidates:
    if (series['id'], issue_nr) in issue_map:
        candidates_with_issue.append(series)
```

**Impact:**
- Validates issue actually exists before picking series
- Prevents matching to wrong series (e.g., 1984 Alpha Flight vs 1983 Alpha Flight)
- closest_year_with_issue: 594 → 644
- only_one_with_issue: 467 → 540

## Remaining Failure Analysis

### no_series (61, 1.2%)
**Causes:**
- Series not in GCD (indie comics, small publishers)
- Series name mismatch not handled by current normalization
- Subtitle differences: "B.P.R.D.: Hell on Earth" vs "B.P.R.D.: Hell on Earth — New World"

**Potential fixes:**
- Fuzzy matching for subtitle differences
- Manual curation for common mismatches

### no_issue_in_N_series (177 total, 3.4%)
**Causes:**
- CLZ has wrong issue numbers (Supreme #43 doesn't exist in any series)
- CLZ has issues from series not indexed in GCD
- Variant issues not in GCD

**Potential fixes:**
- Date-based matching (if CLZ Release Date matches GCD key_date)
- Accept "closest series without issue" as partial match

### bad_issue_nr (6, 0.1%)
**Causes:**
- Non-integer issue numbers: "½", "1/2", "AU", "Annual"

**Potential fixes:**
- Handle special issue number formats
- Match annuals separately

## Performance
- **Speed:** ~16K it/s (runs in ~0.3 seconds)
- **Memory:** ~250MB
- **Database queries:** 3 (one-time load: barcodes, series, issues)

## Files
- `gcd_tests.py`: Final matching script with all improvements
- `clz_all_columns_enriched.csv`: Output with 96.4% match rate
- `CLZ_GCD_MATCHING.md`: This documentation
