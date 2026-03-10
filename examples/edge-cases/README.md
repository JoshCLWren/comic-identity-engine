# Comic Issue Number Edge Cases - Master Dataset
## ⚠️ MANDATORY: Fix Broken Code

**ALL AI AGENTS MUST READ THIS:**

When you encounter broken code, tests, or functionality in this codebase, **you are REQUIRED to fix it**. Do NOT ignore broken code. Do NOT work around it. Do NOT leave it for "later".

**If you find it, you fix it.**

This includes but is not limited to:
- Failing tests
- Syntax errors
- Import errors
- Type errors
- Logic bugs
- LSP warnings that indicate real problems
- Inconsistent behavior

**No exceptions. No excuses.**

---


Comprehensive research on problematic comic issue number formats across platforms.

## Overview

This dataset documents how different comic platforms handle non-standard issue numbers.
Research conducted across 7+ platforms: GCD, LoCG, CCL, AA, CPG, MyComicShop, HIP Comic.

## Edge Case Categories

### 1. Negative Issues ✓ RESEARCHED
**Example**: X-Men #-1

| Platform | Display | URL Encoding | ID System | Rating |
|----------|---------|--------------|-----------|--------|
| GCD | `-1` | API only | Integer | ⭐⭐⭐⭐⭐ |
| CCL | `#-1` | `/-1/` | UUID | ⭐⭐⭐⭐⭐ |
| CPG | `#-1` | `/-1/` | Alphanumeric | ⭐⭐⭐⭐⭐ |
| LoCG | `#-1` | `x-men-1` ❌ | Integer | ⭐⭐ |
| AA | `#-1` | slug ends `1` ⚠️ | Integer | ⭐⭐⭐ |
| HIP | `#-1` | `1-1` ⚠️ | Unknown | ⭐⭐ |
| MyComicShop | `#-1A` | TID/IVID | Integer | ⭐⭐⭐⭐⭐ |

**Key Finding**: URL encoding breaks down on negative numbers for several platforms.

---

### 2. Decimal Issues ✓ RESEARCHED
**Example**: X-Men #0.5 (Flashback Month)

| Platform | Has Issue | Storage Format | URL Format | Notes |
|----------|-----------|----------------|------------|-------|
| CPG | ✅ Yes | `0.5` | `/x-men-0-5/` | Uses hyphen: `0-5` |
| MyComicShop | ❓ Not found | Unknown | Unknown | May not catalog decimals |
| GCD | ⚠️ Blocked | Unknown | API only | Rate limiting |
| ComicBase | ✅ Yes | `0.5` | Internal IDs | Supports decimals |

**Key Finding**: Hyphen substitution (`0-5` vs `0.5`) is a common workaround.

---

### 3. Zero Issues ✓ RESEARCHED
**Examples**: X-Men #0 (1997), Action Comics #0 (Zero Hour)

| Platform | Has #0 | Display Format | URL Format | Notes |
|----------|---------|----------------|------------|-------|
| GCD | ✅ Yes | `#0` | API only | Handles correctly |
| IndyPlanet | ✅ Yes | `#0` | `/series-name-0` | Preserved in URL |
| CPG | ✅ Yes | `#0` | `/issue/0/` | Preserved |
| MyComicShop | ✅ Yes | `#0` | TID/IVID IDs | No issue in URLs |

**Key Finding**: Zero issues generally handled better than negative numbers.

---

### 4. High Number Issues ✓ RESEARCHED
**Examples**: Detective Comics #1000, Action Comics #1000

| Platform | Has #1000 | Display Format | URL Format | Issues |
|----------|-----------|----------------|------------|--------|
| Cover Browser | ✅ Yes | `#1000` | `/covers/detective-comics/21` | Page-based |
| GCD | ✅ Yes | `#1000` | `/issue/{id}` | ID-based |
| Wikipedia | ✅ Yes | `#1000` | Anchor links | Works fine |

**Key Finding**: 4-digit numbers work fine. No comma formatting observed (`#1000` not `#1,000`).

---

### 5. Letter Suffix Variants ✓ RESEARCHED
**Examples**: #-1A, #-1B, #1.DE, #1.NE

| Suffix Type | Examples | Platform | Complexity |
|-------------|----------|----------|------------|
| Single letter | A, B, C | All | LOW |
| Distribution | DE, NE | MyComicShop, CPG | LOW |
| Event codes | SDCC, NYCC, WIZ | MyComicShop | MEDIUM |
| Retailer codes | AMERE, BCS | CPG | HIGH |
| Complex | WIZ.SIGNED | MyComicShop | HIGH |
| Compound | DD.DE | MyComicShop | VERY HIGH |

**Storage Patterns**:
- Combined: `#-1A` (CLZ, CPG)
- Separate: Slash notation `/DE` (AA), dot notation `.DE` (MyComicShop)
- Query params: `?variant=XXXX` (LoCG)

---

### 6. Fractional Issues ✓ RESEARCHED
**Examples**: #½, #¼, #1/2

**Finding**: True fractional issues are **extremely rare** or non-existent in major databases.
- No unicode fractions (½, ¼) found
- No "1/2" format found for Batman #600
- Letter suffixes (A, B) are commonly used instead
- Year-based issues exist (e.g., `#1946` for Swedish annual)

---

### 7. Double Issues ✓ RESEARCHED
**Examples**: #50-51, #100-101

**Finding**: Actual double issues with hyphenated numbering are **extremely rare**.
- MyComicShop shows `#1-7` format → indicates **issue range available**, not double issue
- GCD doesn't support double numbering - each issue is separate record
- Hyphen notation typically means range, not double issue

---

### 8. Annuals/Specials ✓ RESEARCHED
**Examples**: Annual 1997, Special #1, Summer Special

| Platform | Format | URL Structure | Series Linkage |
|----------|--------|---------------|----------------|
| GCD | Separate series | `/series/{id}/title` | Independent entity |
| LoCG | Filtered | Under main series | With format filter |
| MyComicShop | Separate | "TPBs & Books" section | Separate catalog |
| CPG | Suffix | `/annual-1997/` | Series-connected |

**Key Finding**: Two approaches - separate entities (GCD) vs integrated with filters (LoCG).

---

### 9. Volume Numbering ✓ RESEARCHED
**Examples**: X-Men (1963), X-Men (1991), X-Men (2010)

| Platform | Volume Notation | URL Structure | Example |
|----------|----------------|---------------|---------|
| Marvel.com | Year range | `x-men_1963` | Year in URL |
| GCD | Year began | `/series/{id}/x-men-1963` | Year in display |
| LoCG | Date range | Series subtitle | Display only |
| ComicVine | Explicit | `/x-men/4050-1/` | Volume in URL |

**Key Finding**: All platforms treat each volume as separate series entity with unique ID.

---

### 10. UPC/ISBN Edge Cases ✓ RESEARCHED

**Coverage**:
- **0% coverage** for pre-1974 comics (UPC didn't exist)
- **~95%+ coverage** for post-1990 mainstream
- **Lower coverage** for indie publishers

**Missing UPC Handling**:
- GCD: Uses internal Issue ID
- MyComicShop: Uses TID/IVID system
- LoCG: Cover image matching + manual confirmation

**Collision Examples**:
- Multiple variants sharing same UPC
- Regional UPC differences (US vs Canada)
- Different printings, identical barcodes

**Alternative Identifiers**:
- Internal Issue ID (GCD)
- TID/IVID (MyComicShop)
- Cover image matching
- Publisher + Series + Issue + Date combination

---

### 11. One-Shots & TPBs ✓ RESEARCHED
**Examples**: Batman: The Killing Joke, Trade Paperbacks

| Platform | One-Shot Format | TPB Handling | ISBN Usage |
|----------|----------------|--------------|------------|
| GCD | `#1` (special) | Separate series | ISBN field |
| LoCG | `#1` | Under main series | Not prominent |
| MyComicShop | Unknown | Separate section | Likely used |

**Key Finding**: Two models - separate entities (GCD) vs integrated (LoCG).

---

## Summary of Platform Approaches

### ID System Types

| Platform | Primary ID | Secondary ID | URL Strategy |
|----------|------------|--------------|--------------|
| **GCD** | Integer Issue ID | Series ID | API only |
| **CCL** | UUID | - | Preserves issue in URL |
| **CPG** | Alphanumeric code | Series ID | Preserves issue in URL |
| **MyComicShop** | TID (Series) + IVID (Variant) | IVGroupID | ID-based navigation |
| **LoCG** | Integer ID | Variant IDs | Slug-based (broken) |
| **AA** | Item ID | Title ID | ID-based navigation |
| **HIP** | Unknown | - | `1-1` encoding |

### URL Encoding Quality

**EXCELLENT** (Preserves issue number):
- CCL: `/-1/`
- CPG: `/-1/`
- IndyPlanet: `/series-name-0/`

**BROKEN** (Loses or obscures issue number):
- LoCG: `x-men-1` for `#-1`
- HIP: `1-1` for `#-1`
- AA: Slug ends in `1` for `#-1`

**NO ISSUE NUMBERS IN URL** (ID-based only):
- GCD: API only
- MyComicShop: TID/IVID params

---

## Recommendations for Comic Identity Engine

### 1. Data Storage
- **Issue number field**: `VARCHAR(50)` - must be string
- **Never cast to int** - will lose `-1`, `0.5`, fractions
- **Store original format** - preserve what platform provided
- **Normalize for comparison** - support multiple formats

### 2. ID System
- **Internal ID**: UUID v4 for each unique issue/variant
- **External IDs**: Map all platform IDs (GCD, LoCG, CCL, AA, CPG, HIP, MyComicShop)
- **UPC/ISBN**: Store when available, but not required

### 3. Variant Handling
- **Option A**: Letter codes (A, B, C) - simple
- **Option B**: Slash notation (-1/A) - clear
- **Option C**: Dot notation (.DE, .NE) - platform-specific
- **Recommendation**: Support multiple, normalize internally

### 4. URL Strategy
- **Never rely on URL slugs** for identity
- **Use internal UUIDs** for all routing
- **Human-readable URLs** are optional display-only

### 5. Matching Algorithm
1. **Exact match** on issue number string
2. **Normalization** for decimals (0.5 = 0-5 = 1/2)
3. **UPC validation** when available
4. **Fuzzy matching** on title, year, publisher
5. **Confidence scoring** + explanation

---

## Test Cases for Identity Engine

### Required Test Cases
1. ✅ Negative: X-Men #-1
2. ✅ Decimal: X-Men #0.5
3. ✅ Zero: Action Comics #0
4. ✅ High number: Detective Comics #1000
5. ✅ Letter suffix: #-1A, #-1B
6. ✅ Distribution suffix: #1.DE, #1.NE
7. ✅ Event suffix: #1.SDCC, #1.WIZ
8. ✅ Volume distinction: X-Men (1963) vs X-Men (1991)
9. ✅ Missing UPC: Pre-1974 comics
10. ✅ Variant collision: Multiple covers, same UPC

### Optional Test Cases
11. Year-based issue: #1946
12. Complex suffix: #-1.WIZ.SIGNED
13. Retailer code: #-1-AMERE
14. TPB identification: ISBN vs issue number
15. One-shot: Single issue series

---

## Platform-Specific Notes

### MyComicShop
- **Excellent data quality**
- IVGroupID for variant grouping
- Professional cataloging
- Handles negative numbers correctly

### GCD
- **Authoritative database**
- API-based (no URLs)
- String storage for issue numbers
- Variant editions as separate records

### CCL
- **Best URL structure**
- UUID-based system
- Perfect issue number preservation
- Each variant gets unique UUID

### CPG
- **Good URL structure**
- Alphanumeric issue IDs
- Preserves issue numbers
- Price guide focus

### LoCG
- **Community-driven**
- URL slug problems
- Query param variants
- UPC validation available

### Atomic Avenue
- **ComicBase powered**
- URL slug issues
- Item ID saves it
- Slash notation for variants

### HIP Comic
- **Cryptic URL encoding**
- `1-1` for issue `-1`
- Not recommended for URL patterns

---

## Research Complete

Total platforms researched: **7**
Total edge case categories: **11**
Test cases documented: **15+**

This dataset provides a comprehensive foundation for building a robust Comic Identity Engine.
