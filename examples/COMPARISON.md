# Cross-Platform Comparison: X-Men #-1

## Identity Systems Comparison

| Platform | ID Type | #-1 Display | URL Handles #-1 | Variant System | Reliability |
|----------|---------|--------------|-----------------|----------------|-------------|
| **GCD** | Integer | ✅ `"-1"` | N/A (API only) | Integer IDs | ⭐⭐⭐⭐⭐ |
| **LoCG** | Integer | ✅ `#-1` | ❌ Becomes `x-men-1` | Query params | ⭐⭐ |
| **CCL** | UUID | ✅ `#-1` | ✅ Preserves `/-1/` | UUIDs + letters | ⭐⭐⭐⭐⭐ |
| **AA** | Integer | ✅ `#-1` | ⚠️ Slug ends in `1` | Slash notation | ⭐⭐⭐ |
| **CLZ** | Unknown | ✅ `#-1A` | N/A (app) | Combined `-1A` | ⭐⭐⭐⭐ |

## Issue Number Storage

| Platform | Storage Type | Example | Notes |
|----------|--------------|---------|-------|
| GCD | String | `"number": "-1"` | ✅ Correct approach |
| LoCG | String | Displayed as `-1` | ✅ Display OK, URL broken |
| CCL | String | Displayed as `-1` | ✅ Display OK, URL perfect |
| AA | String | Displayed as `#-1` | ⚠️ Display OK, URL questionable |
| CLZ | String | Displayed as `#-1A` | ⚠️ Combined variant notation |
| CPG | String | Displayed as `#-1` | ✅ Display OK, URL perfect |

## URL Structure Analysis

### ✅ **EXCELLENT**: Comic Collector Live
```
/issue/comic-books/X-Men-1991/-1/98ab98c9-a87a-4cd2-b49a-ee5232abc0ad
```
Preserves `-1` in URL path, unique UUID per variant

### ✅ **EXCELLENT**: Comics Price Guide
```
/titles/x-men/-1/phvpiu
```
Preserves `-1` in URL path, alphanumeric issue ID

### ❌ **BAD**: League of Comic Geeks
```
/comic/1169529/x-men-1          (Issue #-1)
/comic/4117207/x-men-1          (Issue #1)
```
Both become `x-men-1`! Collision risk.

### ⚠️ **MIXED**: Atomic Avenue
```
/atomic/item/217255/1/XMen-2nd-Series-XMen-2nd-Series-1
```
Slug ends with `1`, Item ID (217255) saves it

### ⚠️ **UNUSUAL**: HIP Comic
```
/price-guide/us/marvel/comic/x-men-1991/1-1/?keywords
```
Encodes `-1` as `1-1` (cryptic, non-standard)

### ❌ **N/A**: Grand Comics Database
```
/api/issue/125295/?format=json
```
API only, no human-readable URLs

## Variant Handling

### Variant Count Comparison

| Platform | Base Issue | Variants Found | Variant IDs |
|----------|------------|----------------|-------------|
| **GCD** | 125295 | 3 | 1035261, 1125054 |
| **LoCG** | 1169529 | 3 shown | variant=6930677, 8963556 |
| **CCL** | 98ab98c9... | 4 | 4 unique UUIDs |
| **AA** | 217255 | 4 listed | Item IDs for each |
| **CPG** | phvpiu | 4 | pkxpbvq, uhyscw, pbxukx |

### Variant Naming Conventions

| Platform | Convention | Examples |
|----------|------------|----------|
| **GCD** | Plain text | "Direct Edition", "Variant Edition", "Newsstand" |
| **LoCG** | Descriptive | "Carlos Pacheco Variant", "Newsstand Edition" |
| **CCL** | Letter codes | A, B, C, D |
| **AA** | Slash notation | -1/A, -1/B, -1/NS |
| **CLZ** | Combined | #-1A, #-1B (issue + variant) |
| **CPG** | Letter codes | -1B, -1C, -1-AMERE (special exclusives) |
| **HIP** | URL paths | /direct-edition/, /variant-cover/, /newsstand-edition/ |

## Price Discrepancies

| Platform | Direct Price | Newsstand Price | Variant Premium | Page Count |
|----------|--------------|------------------|----------------|------------|
| GCD | $1.95 | Not specified | - | 44 |
| LoCG | $1.95 | Not specified | - | 32 |
| CCL | $1.95 | $1.99 | - | Not shown |
| AA | $1.95 | Not listed | A=$44.95 | Not shown |
| CLZ | $1.95 | Not specified | - | 32 |
| CPG | $1.95 | $1.99 (B) | - | Not specified |

## Key Findings for Identity Engine Design

### 1. **Never Trust URL Slugs**
- LoCG: `x-men-1` for both #1 and #-1
- AA: Slug ends with `1` for #-1
- **Always use database IDs for identity**

### 2. **Store Issue Numbers as Strings**
- GCD does this correctly: `"number": "-1"`
- Prevents data loss from int conversion
- Supports `0.5`, `-1`, `1/2`, etc.
- **CLZ exception**: Stores as `#-1A` (combined with variant)

### 3. **UUID > Integer IDs**
- CCL's UUID approach is most robust
- No centralized coordination needed
- Globally unique
- Atomic Avenue uses integers but still works (relying on central authority)

### 4. **Variant Handling Patterns**
- **Letter codes** (CCL): Simple, clear
- **Slash notation** (AA): -1/A, -1/B - also good
- **Query params** (LoCG): ?variant=XXXX - OK but relies on base ID
- **Combined notation** (CLZ): #-1A - compact but requires parsing
- **Separate entities** (GCD, CCL): Each variant gets own ID

### 5. **UPC as Cross-Platform Identifier**
- UPC `75960601772099911` matches on GCD, LoCG, CLZ, and CPG
- Can be used to validate matches across platforms
- Not all platforms display UPC (CCL, AA don't show it)
- **Strongest validation key when available**

### 6. **CPG URL Handling**
- CPG also preserves `-1` correctly like CCL
- Uses `/titles/x-men/-1/phvpiu` format
- Alphanumeric issue IDs (phvpiu, pkxpbvq, etc.)
- Another example of correct URL encoding

### 7. **HIP Comic URL Encoding**
- Uses cryptic `1-1` encoding for issue `-1`
- `/price-guide/us/marvel/comic/x-men-1991/1-1/`
- Most unusual encoding seen across all platforms
- Demonstrates why URL slugs cannot be trusted

### 8. **Display ≠ Storage**
- All platforms display `-1` correctly
- But URL handling varies wildly
- **Separate display format from storage format**

## Recommendations

### For Identity Engine

1. **Primary ID**: UUID for each unique issue/variant
2. **Issue Number**: Store as string, never convert to int
3. **URL Slugs**: Optional, never use for identity
4. **Variants**: Either letter codes or slash notation
5. **External IDs**: Store platform-specific IDs (GCD, LoCG, CCL, AA, CPG, HIP) as mappings

### Canonical Model Structure

```json
{
  "id": "uuid-v4",
  "series": {
    "name": "X-Men",
    "year_began": 1991,
    "publisher": "Marvel"
  },
  "issue": {
    "number": "-1",
    "display_number": "#-1",
    "variant": "A",
    "variant_code": null  // or "A", "B", "NS", etc.
  },
  "external_ids": {
    "gcd": 125295,
    "locg": 1169529,
    "ccl": "98ab98c9-a87a-4cd2-b49a-ee5232abc0ad",
    "atomic_avenue": 217255,
    "cpg": "phvpiu"
  }
}
```

## Platforms Completed

✅ Grand Comics Database (GCD)
✅ League of Comic Geeks (LoCG)
✅ Comic Collector Live (CCL)
✅ Atomic Avenue (AA)
✅ CLZ (Collectorz.com)
✅ Comics Price Guide (CPG)
✅ HIP Comic

## Key Insights Summary

1. **UPC Validation**: Confirms GCD, LoCG, CLZ, and CPG reference same issue
2. **Page Count**: LoCG and CLZ agree on 32 pages (GCD's 44 may include ads)
3. **URL Handling**: CCL and CPG preserve `-1` correctly; LoCG, AA, and HIP have issues
4. **Variant Notation**: Ranges from simple (CCL letters) to complex (CLZ combined, CPG exclusives)
5. **HIP Comic encoding**: Uses cryptic `1-1` format - demonstrates why URLs can't be trusted
