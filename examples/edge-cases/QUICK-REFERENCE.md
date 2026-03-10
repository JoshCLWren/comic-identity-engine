# Platform Quick Reference - Edge Case Handling
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


Quick comparison of how platforms handle problematic issue numbers.

## Negative Issues (#-1)

| Platform | Display | URL | Quality |
|----------|---------|-----|---------|
| CCL | `#-1` | `/-1/` | ⭐⭐⭐⭐⭐ |
| CPG | `#-1` | `/-1/` | ⭐⭐⭐⭐⭐ |
| MyComicShop | `#-1A` | ID-based | ⭐⭐⭐⭐⭐ |
| GCD | `-1` | API | ⭐⭐⭐⭐⭐ |
| IndyPlanet | `#-1` | `/-1/` | ⭐⭐⭐⭐⭐ |
| AA | `#-1` | Slug issue | ⭐⭐⭐ |
| LoCG | `#-1` | `x-men-1` ❌ | ⭐⭐ |
| HIP | `#-1` | `1-1` ⚠️ | ⭐⭐ |

## Decimal Issues (#0.5)

| Platform | Has | Storage | URL | Notes |
|----------|-----|--------|-----|-------|
| CPG | ✅ | `0.5` | `/x-men-0-5/` | Uses hyphen |
| MyComicShop | ❓ | Unknown | Unknown | May not have |
| GCD | ⚠️ | Unknown | API | Rate blocked |

## Zero Issues (#0)

| Platform | Has | Display | URL | Notes |
|----------|-----|---------|-----|-------|
| GCD | ✅ | `#0` | API | Works |
| MyComicShop | ✅ | `#0` | ID-based | Works |
| CPG | ✅ | `#0` | `/0/` | Works |
| IndyPlanet | ✅ | `#0` | `/series-0` | Preserved |

## High Numbers (#1000)

| Platform | Has | Display | Formatting | Issues |
|----------|-----|---------|-----------|--------|
| GCD | ✅ | `#1000` | Plain | None |
| Cover Browser | ✅ | `#1000` | Plain | None |
| Wikipedia | ✅ | `#1000` | Plain | None |

**Key**: No comma formatting (`1,000`) observed. All use plain numbers.

## Letter Suffixes

| Suffix Type | Examples | Platforms | Complexity |
|-------------|----------|-----------|------------|
| A, B, C | #-1A, #-1B | All | Low |
| DE, NE | #1.DE | MyComicShop, CPG | Low |
| /DE, /NS | #-1/DE | AA | Low |
| SDCC, NYCC | #1.SDCC | MyComicShop | Medium |
| WIZ.SIGNED | #-1.WIZ.SIGNED | MyComicShop | High |
| AMERE, BCS | #-1-AMERE | CPG | High |

## Annuals/Specials

| Platform | Format | Separate Series? | Notes |
|----------|--------|------------------|-------|
| GCD | Annual 1997 | ✅ Yes | Independent entity |
| LoCG | Annual 1997 | ❌ No | Filtered under main |
| MyComicShop | Annual 1997 | ✅ Yes | Separate catalog |
| CPG | annual-1997 | ❌ No | URL suffix |

## UPC Coverage

| Era | Coverage | Notes |
|-----|----------|-------|
| Pre-1974 | 0% | UPC didn't exist |
| 1974-1980 | ~50% | Gradual adoption |
| 1980s | ~80% | More consistent |
| 1990s+ | ~95%+ | Standard |
| Indie comics | ~70% | Less consistent |

## Variant Collision

| Situation | Frequency | Platforms Affected | Solution |
|-----------|-----------|-------------------|----------|
| Same UPC, different covers | Common | All | Cover image matching |
| Regional UPC differences | Medium | MyComicShop, GCD | Separate UPCs |
| Newsstand vs Direct | Common | All | Price difference |
| Convention exclusives | Rare | MyComicShop | Suffix notation |

## ID System Comparison

| Platform | ID Type | Format | Stability |
|----------|--------|--------|-----------|
| GCD | Integer | 125295 | ⭐⭐⭐⭐⭐ |
| CCL | UUID | 98ab98c9-... | ⭐⭐⭐⭐⭐ |
| CPG | Alphanumeric | phvpiu | ⭐⭐⭐⭐⭐ |
| MyComicShop | Integer | TID/IVID | ⭐⭐⭐⭐⭐ |
| LoCG | Integer | 1169529 | ⭐⭐⭐⭐ |
| AA | Integer | 217255 | ⭐⭐⭐⭐ |
| HIP | Unknown | ??? | ⭐⭐ |

**UUID > Alphanumeric > Integer** for stability and global uniqueness.

## URL Strategy Recommendations

❌ **NEVER** use for identity:
- LoCG slugs (`x-men-1` for `#-1`)
- HIP encoding (`1-1` for `#-1`)
- AA slugs (truncates negatives)
- Any user-editable URL component

✅ **CAN** use for display:
- CCL format (`/-1/`)
- CPG format (`/-1/`)
- IndyPlanet format (`/-1/`)

⭐ **MUST** use for identity:
- Internal UUIDs
- Platform external IDs (GCD, CCL, etc.)
- UPC when available
- Publisher + Series + Issue + Date combination

## Matching Priority

For issue reconciliation, use in order:

1. **UPC/ISBN match** (when available) - 100% confidence
2. **Exact issue number + series + year** - 95% confidence
3. **Normalized issue number** (0.5 = 0-5) - 90% confidence
4. **Title + publisher + date** - 70% confidence
5. **Cover image similarity** - 60% confidence

Always provide confidence score + explanation.
