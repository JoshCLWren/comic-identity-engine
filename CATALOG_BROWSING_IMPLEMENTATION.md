# Catalog Browsing Implementation - GCD Dump Strategy

**Status:** Implemented | **Created:** 2026-03-19 | **Updated:** 2026-03-20

**Strategy:** Replaced HTTP scraping with local SQLite database for 10-100x faster matching.

**Implementation:** `GCDLocalAdapter` (`comic_identity_engine/matching/adapter.py`) + `GCDMatchingService` (`comic_identity_engine/matching/service.py`)

---

## Overview

GCD publishes a full SQLite database dump that contains 2.57M issues and 102K series. Rather than scraping GCD's website, we load this dump once and match against it locally. This approach is:

- **10-100x faster** than HTTP scraping (local lookups vs network requests)
- **More reliable** (no rate limiting, no anti-bot protection)
- **Deterministic** (same input always produces same output)
- **Cacheable** (in-memory indices for instant lookups)

---

## Core Components

### 1. `GCDLocalAdapter` (`comic_identity_engine/matching/adapter.py`)

Low-level SQLite adapter that loads the GCD dump into memory.

```python
from comic_identity_engine.matching.adapter import GCDLocalAdapter

adapter = GCDLocalAdapter()
adapter.load()  # Load dump into memory (~250MB)

# Series lookups
series = adapter.find_series_exact("x-men", "marvel")
series = adapter.find_series_strict("xmen", "marvel")
series = adapter.find_series_by_year(1991)

# Issue lookups
issue = adapter.find_issue(4254, "4")  # (gcd_issue_id, match_type)
covers = adapter.find_issues_by_number_and_year("4", 1991)

# Barcode lookups
gcd_id = adapter.find_issue_by_barcode("1234567890123")
gcd_id = adapter.find_issue_by_barcode_prefix("9781302945374")

# Series info
info = adapter.get_series_info(4254)  # Returns dict with name, year_began, etc.

# Access loaded data
adapter.series_count  # ~102K series
adapter.issue_count   # ~2.57M issues
```

**Data Structures:**

| Structure | Type | Purpose |
|-----------|------|---------|
| `_series_map` | `dict[str, list[dict]]` | Normalized name → series list |
| `_series_id_to_info` | `dict[int, dict]` | Series ID → full info |
| `_issue_map` | `dict[(int, str), (int, str)]` | (series_id, issue_nr) → (gcd_issue_id, match_type) |
| `_year_to_issues` | `dict[int, list]` | Cover year → issue list |
| `_barcode_map` | `dict[str, int]` | Barcode → gcd_issue_id |

**Match Types:**
- `canonical` - Main/release issue (preferred)
- `newsstand` - Newsstand variant
- `variant` - Other variant

### 2. `GCDMatchingService` (`comic_identity_engine/matching/service.py`)

High-level matching service with round-robin strategy selection.

```python
from comic_identity_engine.matching import GCDMatchingService, GCDLocalAdapter, CLZInput

adapter = GCDLocalAdapter()
service = GCDMatchingService(adapter)

# Create input from CLZ CSV row
clz_input = CLZInput.from_csv_row(row)

# Match to GCD
result = service.match(clz_input)

if result.is_match():
    print(f"GCD Issue ID: {result.gcd_issue_id}")
    print(f"Strategy: {result.strategy_name}")
    print(f"Confidence: {result.confidence.name}")
```

---

## 3-Stage Matching Pipeline

### Stage 1: Barcode Matching (Confidence: 100)

**Fastest and most reliable.** Tries exact barcode match first, then ISBN prefix.

```python
# Stage 1a: Exact barcode
gcd_id = adapter.find_issue_by_barcode("1234567890123")  # Direct UPC/EAN match

# Stage 1b: ISBN prefix (GCD adds 5-digit suffix)
# CLZ:  9781302945374
# GCD:  978130294537454499
result = adapter.find_issue_by_barcode_prefix("9781302945374")
# Returns (gcd_issue_id, matched_barcode)
```

**Coverage:** 72.7% of CLZ comics match via barcode (3,781 of 5,203).

### Stage 2: Series + Issue Matching (Confidence: 90-85)

When barcode fails, match by series name + issue number.

**Normalization Pipeline:**
```python
def _gcd_normalize_name(name: str) -> str:
    # 1. strip_diacritics - handles unicode variants (Rōnin → Ronin)
    # 2. strip_subtitle - removes " : Subtitle"
    # 3. normalize_series_name - removes Vol. X, publisher parens, II/III, Annual, (YYYY)
    # 4. lower - case-insensitive comparison
```

**Matching Strategies (tried in order):**

| Strategy | Confidence | Description |
|----------|------------|-------------|
| `exact_one_issue` | 90 | Exact name + issue exists in exactly one series |
| `exact_closest_year` | 85 | Exact name + multiple series, pick closest cover year |
| `exact_series` | 80 | Exact name + single series (no issue check) |
| `normalized_series` | 75 | Strict normalization (&/and, punctuation) |
| `word_order_series` | 70 | Word-set match (reversed order) |
| `colon_comma_series` | 68 | Colon/comma variant |
| `article_series` | 60 | With/without "The" prefix |
| `substring_series` | 50 | Substring match (last resort) |
| `reverse_lookup` | 65/55 | Issue+year found, pick by name similarity |

**Disambiguation Logic:**
```python
# 1. Check if issue exists in each candidate series
candidates_with_issue = []
for series in candidates:
    if (series['id'], issue_nr) in issue_map:
        candidates_with_issue.append(series)

# 2. If multiple, pick by cover year proximity
if len(candidates_with_issue) > 1:
    # Prefer series where issue cover date matches CLZ year
    candidates.sort(key=lambda s: abs(issue_cover_year - clz_year))
```

### Stage 3: Fallback (Confidence: 0)

If no match found, return failure with reason.

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLZ CSV Import                                 │
│                           (comic_identity_engine/jobs/tasks.py)            │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CLZAdapter.fetch_issue_from_csv_row()                 │
│                        → IssueCandidate (CLZ internal model)                │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         _try_gcd_match(row, issue_candidate)                 │
│                        (comic_identity_engine/jobs/tasks.py)                │
│                                                                             │
│  1. CLZInput.from_csv_row(row) → CLZInput                                  │
│  2. _get_gcd_matching_service() → GCDMatchingService (singleton)           │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       GCDMatchingService.match(clz_input)                   │
│                        (comic_identity_engine/matching/)                    │
│                                                                             │
│  ┌─────────────┐     ┌──────────────────┐     ┌────────────────────────┐   │
│  │  CLZInput   │────▶│ Round-Robin Loop │────▶│  GCDLocalAdapter       │   │
│  │             │     │ (all strategies) │     │  (SQLite dump in RAM)  │   │
│  └─────────────┘     └──────────────────┘     └────────────────────────┘   │
│                                                        │                    │
│                                                        │                    │
│                              ┌─────────────────────────┼───────────────┐    │
│                              │                         │               │    │
│                              ▼                         ▼               ▼    │
│                     ┌──────────────┐          ┌──────────────┐ ┌──────────┐│
│                     │  Barcode Map  │          │ Series Index │ │ Issue Map││
│                     │  (_barcode)   │          │ (_series_map)│ │(_issue) ││
│                     └──────────────┘          └──────────────┘ └──────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                          ┌──────────────────┐
                          │  StrategyResult  │
                          │  - confidence    │
                          │  - gcd_issue_id  │
                          │  - strategy_name │
                          └──────────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
             ┌──────────────┐              ┌──────────────┐
             │ Match Found  │              │ No Match     │
             │ (confidence≥90)│             │ (confidence<90)│
             └──────────────┘              └──────────────┘
                     │                               │
                     ▼                               ▼
             ┌──────────────┐              ┌──────────────────────────────┐
             │ Link to GCD  │              │ Fallback: IdentityResolver   │
             │ via existing │              │ + PlatformSearcher          │
             │ mapping      │              │ (HTTP-based resolution)      │
             └──────────────┘              └──────────────────────────────┘
                     │                               │
                     └───────────────┬─────────────────┘
                                     ▼
             ┌──────────────────────────────────────────────┐
             │              PostgreSQL DB                    │
             │     (comic_identity_engine database)          │
             │                                              │
             │  external_mappings                           │
             │  ├── source = 'gcd' (if high-confidence)     │
             │  ├── source = 'clz' (always)                 │
             │  └── issue_id = <uuid>                       │
             └──────────────────────────────────────────────┘
```

---

## Dump Location and Refresh Strategy

### Dump Location

| Environment | Path |
|-------------|------|
| Production | `/mnt/bigdata/downloads/{date}.db` |
| Local Dev | Same path (mounted volume) |

**Current Dump Stats:**
- **Size:** 6.0 GB
- **Issues:** 2.57M
- **Series:** 102K (English, 1950-2026)
- **Barcodes:** 362K (including 83K ISBNs)
- **Memory Usage:** ~250MB (loaded into Python dicts)

### Refresh Strategy

GCD publishes dumps periodically (typically monthly).

```bash
# Download latest dump
wget https://www.comics.org/downloads/comics.db.gz
gunzip comics.db.gz

# Verify dump
sqlite3 comics.db "SELECT COUNT(*) FROM gcd_issue;"

# Restart service to reload (adapter.load() reads on startup)
```

**Recommended Refresh Cadence:**
- **Monthly** for production
- **Weekly** for high-volume imports

---

## Failure Modes

### Failure Reasons

| Reason | Count | % | Cause |
|--------|-------|---|-------|
| `no_series` | 61 | 1.2% | Series name not in GCD |
| `no_issue_in_N_series` | 122 | 2.3% | Series exists, issue doesn't |
| `bad_issue_nr` | 6 | 0.1% | Non-integer issue numbers |

### `no_series` - Series Not Found

**Causes:**
- Indie/small press comics not in GCD
- Series name mismatch not handled by normalization
- Subtitle differences (e.g., "B.P.R.D.: Hell on Earth" vs "B.P.R.D.: Hell on Earth — New World")

**Potential Fixes:**
```python
# Try fuzzy matching for subtitle differences
# Use Levenshtein distance for similar names
# Manual curation for common mismatches
```

### `no_issue_in_N_series` - Issue Doesn't Exist

**Causes:**
- CLZ has wrong issue numbers (e.g., "Suprem #43" doesn't exist)
- Variant issues not in GCD
- Numbering mismatch (CLZ #36 vs GCD #36)

**Potential Fixes:**
```python
# Date-based matching (CLZ Release Date vs GCD key_date)
# Accept "closest series without issue" as partial match
# Check variant suffixes in Issue field
```

### `bad_issue_nr` - Non-Integer Issue Numbers

**Causes:**
- Fractions: "½", "1/2"
- Letter suffixes: "AU", "A", "B"
- Annuals: "Annual"

**Handling:**
```python
# These are currently skipped
# Future: Match annuals separately
# Future: Handle special formats like "52A"
```

---

## Confidence Scores

| Score | Level | Action |
|-------|-------|--------|
| 100 | BARCODE | Authoritative match, use directly |
| 90 | EXACT_ONE_ISSUE | High confidence, use directly |
| 85 | EXACT_CLOSEST_YEAR | High confidence, use directly |
| 75-80 | SERIES_ONLY | Use with caution, may need verification |
| 50-68 | FUZZY | Lower confidence, consider fallback |
| 0 | NO_MATCH | No match found |

**Threshold:** Matches with confidence ≥ 85 are auto-imported. Lower confidence matches may trigger fallback to PlatformSearcher.

---

## Usage Example

```python
from comic_identity_engine.matching import GCDMatchingService, GCDLocalAdapter, CLZInput

# Initialize once at startup (load takes ~5 seconds)
adapter = GCDLocalAdapter()
adapter.load()
service = GCDMatchingService(adapter)

# Process CLZ CSV row
row = {
    "Core ComicID": "12345",
    "Series": "X-Men",
    "Series Group": "X-Men 1991",
    "Issue": "4",
    "Issue Nr": "4",
    "Cover Year": "1991",
    "Barcode": "75960609663900411",
    "Publisher": "Marvel Comics",
}

clz_input = CLZInput.from_csv_row(row)
result = service.match(clz_input)

print(f"""
Match Result:
  GCD Issue ID: {result.gcd_issue_id}
  GCD Series ID: {result.gcd_series_id}
  Confidence: {result.confidence.name} ({result.confidence.value})
  Strategy: {result.strategy_name}
  Year Distance: {result.year_distance}
  Details: {result.match_details}
""")
```

**Output:**
```
Match Result:
  GCD Issue ID: 50800
  GCD Series ID: 4254
  Confidence: BARCODE (100)
  Strategy: barcode
  Year Distance: None
  Details: 
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Speed** | ~16,000 matches/second |
| **Memory** | ~250MB |
| **Database queries** | 3 (one-time load) |
| **Startup time** | ~5 seconds (load dump) |
| **Match rate** | 96.4% on CLZ collection |

**Comparison to HTTP scraping:**
- HTTP: ~1-2 seconds per match (network latency)
- Dump: ~0.00006 seconds per match (in-memory)
- **Speedup: 16,000x faster**

---

## Files Reference

### Core Implementation

| File | Purpose |
|------|---------|
| `comic_identity_engine/matching/adapter.py` | `GCDLocalAdapter` - SQLite dump loader |
| `comic_identity_engine/matching/service.py` | `GCDMatchingService.match(clz_input)` - Round-robin matcher |
| `comic_identity_engine/matching/types.py` | `CLZInput`, `StrategyResult`, `MatchConfidence` |
| `comic_identity_engine/matching/normalizers.py` | Series name normalization functions |

### Integration Points

| File | Function | Purpose |
|------|----------|---------|
| `comic_identity_engine/jobs/tasks.py` | `_get_gcd_matching_service()` | Singleton getter for GCDMatchingService |
| `comic_identity_engine/jobs/tasks.py` | `_try_gcd_match(row, issue_candidate)` | Integration point - tries GCD match before HTTP fallback |

### Test/Validation

| File | Purpose |
|------|---------|
| `gcd_tests.py` | CLI tool for batch matching CLZ exports |
| `tests/matching/test_adapter.py` | Unit tests for adapter |

### Documentation

| File | Purpose |
|------|---------|
| `CATALOG_BROWSING_IMPLEMENTATION.md` | This file |
| `CATALOG_BROWSING_PLAN.md` | Strategy and progress tracking |
| `CLZ_GCD_MATCHING.md` | Match rate analysis and improvements |

---

## Integration Checklist

- [x] `GCDLocalAdapter` loads SQLite dump into memory
- [x] `GCDMatchingService` implements round-robin strategy selection
- [x] Barcode matching (exact + prefix)
- [x] Series name normalization (The, Vol., publisher parens)
- [x] Issue existence validation
- [x] Year-based disambiguation
- [x] 96.4% match rate on CLZ collection
- [x] Wire into CLZ import pipeline (`_get_gcd_matching_service`, `_try_gcd_match` in jobs/tasks.py)
- [x] High-confidence matches (≥90) link to existing GCD mappings
- [x] Low-confidence matches fall back to IdentityResolver + PlatformSearcher
- [ ] Add unit/integration tests
- [ ] Document refresh strategy for production deployment

---

## Future Improvements

1. **Fuzzy matching** for subtitle differences
2. **Date-based fallback** (CLZ Release Date vs GCD key_date)
3. **Variant issue handling** for special formats (1/2, AU, Annual) - partially implemented via `variant_fallback`
4. **Caching** with scrapekit for frequent series lookups
5. **Confidence threshold tuning** for optimal match rate vs precision
6. **Progress tracking** for batch imports

---

**Last Updated:** 2026-03-20
**Owner:** @josh
**Status:** Implemented - fully integrated in CLZ import pipeline
