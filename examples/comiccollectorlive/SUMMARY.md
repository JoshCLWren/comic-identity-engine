# CCL X-Men #-1 Data Summary
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
| Platform | Comic Collector Live |
| Series ID | 84ac79ed-2a10-4a38-9b4c-6df3e0db37de |
| Series Name | X-Men (1991) |
| Issue Number | `-1` (displayed) |
| Publisher | Marvel Comics |
| Publish Date | July 01, 1997 |
| Sale Date | May 21, 1997 |
| Base Price | $1.95 USD |
| Newsstand Price | $1.99 USD |

## All Variants with UUIDs

| Variant | GUID | Cover | Price | Notes |
|---------|------|-------|-------|-------|
| A | 98ab98c9-a87a-4cd2-b49a-ee5232abc0ad | Carlos Pacheco | $1.95 | Direct Edition |
| B | f352ec33-f77b-4fa6-9d47-7927c39c4a9b | Chris Bachalo | $1.95 | Wizard Exclusive |
| C | e6fa653b-d05e-45db-98ee-de21965bedea | Carlos Pacheco | $1.95 | DF Signed, 1/500 |
| D | d8bb220a-4330-4749-a219-dc889e59b65c | Carlos Pacheco | $1.99 | Newsstand |

## Issue Number Handling

**EXCELLENT**: CCL handles negative numbers correctly!

- Display: Shows `-1` in title and variant codes
- URL: Preserved in path: `/issue/comic-books/X-Men-1991/-1/{guid}`
- No data loss or transformation

## Identity Implications

### Positive Observations
- ✅ **Perfect URL structure**: `-1` preserved in URL
- ✅ **UUID-based**: Each variant has unique GUID
- ✅ **Variant system**: Explicit letter codes (A, B, C, D)
- ✅ **Price tracking**: Notes price differences between variants

### Best Practices from CCL

1. **UUID for every entity**: No ambiguity, globally unique
2. **URL-safe**: Negative numbers preserved correctly
3. **Variant separation**: Each variant is distinct entity
4. **Descriptive slugs**: Variant B includes cover artist name

## Key Takeaway for Identity Engine

**CCL gets it right!**
- UUIDs prevent collision
- Negative numbers preserved in URLs
- Variant letters clearly designated
- Price differences tracked per variant

This is the model to follow for issue identification.

## Files

- `xmen-negative1-variant-a-snapshot.md` - Variant A (Direct Edition)
- Additional snapshots captured for all variants
