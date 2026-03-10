# CLZ X-Men #-1 Data Summary
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
| Platform | Comic Collector CLZ |
| Series | X-Men, Vol. 1 |
| Issue Number | `#-1A` |
| Display | #-1A |
| Publisher | Marvel Comics |
| Release Date | May 21, 1997 |
| Cover Date | Jul 1997 |
| Cover Price | $1.95 |
| Pages | 32 |
| UPC | 75960601772099911 |

## Issue Number Handling

**UNIQUE**: Compact variant notation

- Format: `#-1A` (issue + variant combined)
- Different from all other platforms:
  - GCD: Separate variant field
  - LoCG: Query parameter
  - CCL: Separate variant letter
  - AA: Slash notation (-1/A)
- **Parsing required**: Must split issue number and variant code

## UPC Validation

**UPC matches across platforms!**

| Platform | UPC | Format |
|----------|-----|--------|
| GCD | 75960601772099911 | With space |
| LoCG | 75960601772099911 | No space |
| CLZ | 75960601772099911 | No space |

This confirms all three platforms reference the same physical issue.

## Page Count: Resolved!

**CLZ = 32 pages matches LoCG**

| Platform | Page Count |
|----------|------------|
| GCD | 44 pages |
| LoCG | 32 pages |
| CLZ | 32 pages |
| CCL | Not specified |

**Hypothesis**: GCD counts all pages (including ads, editorials), while LoCG/CLZ count story pages only.

## Identity Implications

### Positive Observations
- ✅ UPC provides cross-platform validation
- ✅ Release date vs cover date distinction is clear
- ✅ Compact variant notation is efficient
- ✅ Detailed creator credits

### Concerns
- ⚠️ **Variant notation requires parsing**: `-1A` must be split into `-1` + `A`
- ⚠️ User-contributed data quality varies
- ⚠️ Not a public API/database (personal software)

## Key Takeaway for Identity Engine

**UPC is the universal identifier!**

The UPC 75960601772099911 appears on:
- GCD
- LoCG
- CLZ
- The physical comic barcode

**Recommendation**: Use UPC as a cross-platform validation field.

**Variant notation**: CLZ's `#-1A` format is efficient but requires parsing.
- Issue: `-1`
- Variant: `A`
- Combined: `-1A`

## Files

Data provided from user's personal CLZ inventory.

## Comparison to Other Platforms

| Platform | Display | Variant Format | Page Count | UPC |
|----------|---------|----------------|------------|-----|
| **GCD** | `-1` | Separate field | 44 | ✅ 75960601772099911 |
| **LoCG** | `#-1` | Query param | 32 | ✅ 75960601772099911 |
| **CCL** | `#-1` | Letter code | ? | Not shown |
| **AA** | `#-1` | Slash notation | ? | Not shown |
| **CLZ** | `#-1A` | Combined `-1A` | 32 | ✅ 75960601772099911 |

**Key findings**:
1. UPC is consistent across GCD, LoCG, and CLZ
2. Page count: LoCG + CLZ = 32 (likely correct for story pages)
3. Variant notation varies widely - standardization needed
