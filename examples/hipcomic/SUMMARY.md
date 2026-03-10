# HIP Comic X-Men #-1 Data Summary
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


## Quick Reference

| Field | Value |
|-------|-------|
| Platform | HIP Comic |
| Series Name | X-Men (1991) |
| Issue Number | `-1` (displayed) |
| Issue Encoding | `1-1` (URL) |
| Publisher | Marvel Comics |
| Editor | Bob Harras |
| Writer | Scott Lobdell |
| Cover/Art | Carlos Pacheco, Art Thibert |

## All Variants with Pricing

| Variant | URL Path | FMV (9.2 NM-) | Notes |
|---------|----------|---------------|-------|
| Direct Edition | /1-1/direct-edition/ | $4.04 | Base issue |
| Variant Cover | /1-1/variant-cover/ | $11.48 | Different art |
| Newsstand | /1-1/newsstand-edition/ | $5.45 | Newsstand |

## Issue Number Handling

**MOST UNUSUAL**: Encodes `-1` as `1-1` in URL!

- Display: Shows `#-1` correctly in title
- URL: `/price-guide/us/marvel/comic/x-men-1991/1-1/`
- Variant URLs preserve the `1-1` encoding
- **Likely a workaround**: System may not support negative numbers natively

## Identity Implications

### Positive Observations
- ✅ Display correctly shows `-1`
- ✅ Variant system uses descriptive URL paths
- ✅ Price guide data with FMV tracking
- ✅ Active marketplace with listings

### Concerns
- ⚠️ **URL encoding is cryptic**: `1-1` for `-1`
- ⚠️ Not intuitive: `1-1` could be confused with issue #1
- ⚠️ Platform-specific encoding not standardized
- ⚠️ No unique IDs visible for issues/variants

## Key Takeaway for Identity Engine

**HIP Comic's URL encoding is problematic for identity:**

- `1-1` represents issue `-1` (but why?)
- Could be: `series_position-issue_number` or `volume-issue`
- Ambiguous: Does `1-1` mean "volume 1, issue 1" or "issue -1"?
- **Never rely on URL patterns like this for identity**

## Files

- `xmen-negative1-issue-page.md` - Page snapshot
- `xmen-negative1-issue-page.png` - Screenshot

## Comparison to Other Platforms

| Platform | Display | URL Encoding | #-1 Support | Notes |
|----------|---------|--------------|-------------|-------|
| **GCD** | ✅ `-1` | N/A (API) | ⭐⭐⭐⭐⭐ | String storage |
| **LoCG** | ✅ `#-1` | ❌ `x-men-1` | ⭐⭐ | Strips negative |
| **CCL** | ✅ `#-1` | ✅ `/-1/` | ⭐⭐⭐⭐⭐ | Perfect |
| **AA** | ✅ `#-1` | ⚠️ slug issue | ⭐⭐⭐ | ID saves it |
| **CLZ** | ✅ `#-1A` | N/A (app) | ⭐⭐⭐⭐ | Combined variant |
| **CPG** | ✅ `#-1` | ✅ `/-1/` | ⭐⭐⭐⭐⭐ | Perfect |
| **HIP** | ✅ `#-1` | ⚠️ `1-1` | ⭐⭐ | Cryptic encoding |

**HIP Comic ranks lowest for URL handling** due to non-obvious encoding.

## Additional Notes

HIP Comic is primarily a marketplace with price guide features.
The `1-1` encoding suggests the platform was built without negative issue numbers in mind.
This reinforces: **never trust URL slugs for identity**.
