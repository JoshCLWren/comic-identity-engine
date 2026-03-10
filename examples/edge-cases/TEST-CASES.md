# Test Cases for Comic Identity Engine
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


Comprehensive test cases to validate the identity engine handles all edge cases.

## Priority 1: Core Test Cases (Required)

### TC-001: Negative Issue Number
**Issue**: X-Men #-1 (1997)

**Expected Behavior**:
- Accept `-1` as valid issue number
- Store as string "-1"
- Match across all 7 platforms
- Distinguish from issue #1

**Test Data**:
- GCD: Issue 125295
- CCL: UUID 98ab98c9-a87a-4cd2-b49a-ee5232abc0ad
- LoCG: ID 1169529
- UPC: 75960601772099911

### TC-002: Decimal Issue Number
**Issue**: X-Men #0.5 (1997)

**Expected Behavior**:
- Accept `0.5` as valid
- Normalize with `0-5` variant
- Handle hyphen substitution
- Match with CPG (uses `0-5`)

**Test Data**:
- CPG: URL `/x-men-0-5/1997-1/`
- Display: "X-Men #0.5"

### TC-003: Zero Issue
**Issue**: Action Comics #0 (1994)

**Expected Behavior**:
- Accept `0` as valid issue number
- NOT treat as null/missing
- Store as string "0"
- Match across platforms

**Test Data**:
- GCD: Has issue
- Publisher: DC Comics
- Year: 1994

### TC-004: High Number Issue
**Issue**: Detective Comics #1000 (2019)

**Expected Behavior**:
- Accept 4-digit issue numbers
- No integer overflow
- Display without commas
- Store as string "1000"

**Test Data**:
- Publisher: DC Comics
- Year: 2019

### TC-005: Letter Suffix Variant
**Issue**: X-Men #-1A (Direct Edition)

**Expected Behavior**:
- Parse suffix "A" from issue number
- Store as separate field: issue="-1", variant="A"
- Match with other #-1 variants
- Handle display as "#-1A"

**Test Data**:
- MyComicShop: #-1A, #-1B
- CPG: #-1 (Direct Edition)

### TC-006: Distribution Suffix
**Issue**: X-Men #1.DE (Direct Edition)

**Expected Behavior**:
- Recognize "DE" as Direct Edition
- Recognize "NE" as Newsstand
- Normalize to standard variant codes
- Match regardless of distribution suffix

**Test Data**:
- MyComicShop: Uses .DE, .NE notation
- AA: Uses /DE, /NS notation

### TC-007: UPC Match
**Issue**: X-Men #-1 (1997)

**Expected Behavior**:
- Match using UPC 75960601772099911
- 100% confidence on UPC match
- Work across GCD, LoCG, CLZ, CPG
- Handle missing UPC gracefully

**Test Data**:
- UPC: 75960601772099911
- Appears on 4 platforms

### TC-008: Volume Distinction
**Issue**: X-Men #1 (1991) vs X-Men #1 (1963)

**Expected Behavior**:
- Recognize different volumes/series
- Use year_began to distinguish
- Separate series entries
- No false matches between volumes

**Test Data**:
- X-Men (1963): Volume 1
- X-Men (1991): Volume 2
- Same issue number, different series

### TC-009: Missing UPC
**Issue**: Any pre-1974 comic

**Expected Behavior**:
- Don't require UPC
- Use alternative matching
- Publisher + Series + Issue + Year
- Cover image matching
- Lower confidence score

**Test Data**:
- Golden Age comics
- Silver Age comics
- No UPC existed

### TC-010: Variant Collision
**Issue**: Same UPC, different covers

**Expected Behavior**:
- Detect multiple covers for same UPC
- Use cover image to distinguish
- Variant suffixes for differentiation
- Handle as separate entities

**Test Data**:
- Modern incentive variants
- Convention exclusives
- Same base UPC

## Priority 2: Edge Cases (Important)

### TC-011: Zero with Suffix
**Issue**: #-1.WIZ.SIGNED

**Expected Behavior**:
- Parse complex suffixes
- Handle dot-separated suffixes
- Multiple suffix components
- Store all suffix information

**Test Data**:
- MyComicShop: #-1.WIZ.SIGNED
- Wizard Signed Edition

### TC-012: Retailer Exclusive
**Issue**: #-1-AMERE (American Entertainment)

**Expected Behavior**:
- Recognize retailer codes
- Handle hyphenated suffixes
- Platform-specific conventions
- Document retailer exclusives

**Test Data**:
- CPG: #-1-AMERE
- American Entertainment exclusive

### TC-013: Year-Based Issue
**Issue**: #1946 (Swedish annual)

**Expected Behavior**:
- Detect year used as issue number
- Tag as special case
- Don't confuse with actual year
- Handle correctly in sorting

**Test Data**:
- 91 Karlsson #1946
- Year is the issue number

### TC-014: Annual Identification
**Issue**: X-Men Annual 1997

**Expected Behavior**:
- Recognize "Annual" format
- Link to main series correctly
- Separate from regular issues
- Handle annual numbering

**Test Data**:
- GCD: Separate series
- LoCG: Under main series
- Different approaches

### TC-015: Complex Suffix
**Issue**: #1.DD.DE

**Expected Behavior**:
- Parse multiple dot-separated suffixes
- Store all suffix components
- Handle compound notation
- Maintain all information

**Test Data**:
- MyComicShop: DD.DE notation
- Multiple distribution types

## Priority 3: Edge Cases (Optional)

### TC-016: One-Shot
**Issue**: Batman: The Killing Joke

**Expected Behavior**:
- Recognize single-issue series
- Mark as one-shot
- Series has issue count = 1
- No issue number needed

**Test Data**:
- GCD: Uses #1 format
- LoCG: Uses #1 format

### TC-017: Trade Paperback
**Issue**: X-Men Vol. 1 TPB

**Expected Behavior**:
- Recognize TPB format
- Use ISBN instead of UPC
- Separate from single issues
- Collection of issues

**Test Data**:
- ISBN-based identification
- Multiple issues included
- Different cataloging

### TC-018: Fractional Display
**Issue**: Display #½ if needed

**Expected Behavior**:
- Support unicode fractions
- Support "1/2" string
- Normalize to decimal
- Display correctly

**Test Data**:
- Rare but exists
- Special issues

### TC-019: Special Notation
**Issue**: #[1] brackets (GCD convention)

**Expected Behavior**:
- Parse bracket notation
- Handle GCD-specific format
- Normalize to standard
- Preserve original format

**Test Data**:
- GCD: Uses #[1] notation
- Indexing convention

### TC-020: URL Slug Collision
**Issue**: LoCG `x-men-1` for #1 and #-1

**Expected Behavior**:
- Detect URL slug collisions
- Never rely on slugs for identity
- Use IDs for matching
- Document collision cases

**Test Data**:
- LoCG: Both #1 and #-1 use `x-men-1`
- ID is only differentiator

## Test Execution Plan

### Phase 1: Core Functionality
Run TC-001 through TC-010 to validate:
- Issue number storage
- Cross-platform matching
- UPC validation
- Variant handling
- Volume distinction

### Phase 2: Edge Cases
Run TC-011 through TC-015 to validate:
- Complex suffix parsing
- Retailer exclusives
- Special issue formats
- Annuals handling

### Phase 3: Advanced Features
Run TC-016 through TC-020 to validate:
- One-shot detection
- TPB handling
- Special notation
- Edge case coverage

## Success Criteria

### Minimum Viable Product (MVP)
- ✅ Pass TC-001 through TC-010
- ✅ Match issues across 5+ platforms
- ✅ Handle negative, decimal, zero issues
- ✅ UPC validation when available
- ✅ Variant distinction

### Full Release
- ✅ Pass all test cases
- ✅ Match across all 7 platforms
- ✅ Handle all edge cases
- ✅ Confidence scoring + explanations
- ✅ Audit trail for matches

## Test Data Repository

All test cases have corresponding data in:
- `examples/gcd/` - GCD data
- `examples/ccl/` - Comic Collector Live data
- `examples/cpg/` - Comics Price Guide data
- `examples/locg/` - League of Comic Geeks data
- `examples/atomicavenue/` - Atomic Avenue data
- `examples/hipcomic/` - HIP Comic data
- `examples/clz/` - Collectorz.com data

## Coverage Matrix

| Edge Case | Test Case | Platforms Covered | Status |
|-----------|------------|-------------------|--------|
| Negative | TC-001 | All 7 | ✅ Complete |
| Decimal | TC-002 | CPG (others TBD) | ⚠️ Partial |
| Zero | TC-003 | GCD, MyComicShop, IndyPlanet | ⚠️ Partial |
| High number | TC-004 | Cover Browser, GCD | ⚠️ Partial |
| Letter suffix | TC-005 | All 7 | ✅ Complete |
| Distribution | TC-006 | MyComicShop, AA | ⚠️ Partial |
| UPC match | TC-007 | GCD, LoCG, CLZ, CPG | ⚠️ Partial |
| Volume | TC-008 | All platforms | ⚠️ Partial |
| No UPC | TC-009 | Pre-1974 | ⚠️ Partial |
| Variant collision | TC-010 | All | ⚠️ Partial |

**Legend**: ✅ Complete | ⚠️ Partial | ❌ Not started
