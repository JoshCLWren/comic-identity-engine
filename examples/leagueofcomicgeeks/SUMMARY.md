# LoCG X-Men #-1 Data Summary
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
| Platform | League of Comic Geeks |
| Comic ID | 1169529 |
| Series ID | 111275 |
| Series Name | X-Men (1991 - 2001) |
| Issue Number | `-1` (displayed) |
| Publisher | Marvel Comics |
| Release Date | May 21, 1997 |
| Cover Date | July 1997 |
| Price | $1.95 USD |
| Pages | 32 |
| UPC | 75960601772099911 |

## Issue Number Handling

**CRITICAL FINDING**: URL slug is `x-men-1`, NOT `x-men--1`!

- Display: `X-Men #-1` (in page title)
- URL: `/comic/1169529/x-men-1`
- Likely strips special characters from slugs
- Internal ID is authoritative

## Identity Implications

### Positive Observations
- ✅ Displays "-1" correctly in UI
- ✅ Internal numeric ID provides stable reference
- ✅ Variant system uses query parameters

### Concerns
- ⚠️ **URL slug loses information**: `x-men-1` instead of `x-men--1`
- ⚠️ Relies on internal ID for uniqueness
- ⚠️ No public API documented
- ⚠️ Page count differs from GCD (32 vs 44)

## Community Features

LoCG excels at community engagement:
- User ratings: 3.9/5 (85 ratings)
- Collection tracking (1,346 have it)
- Reviews and discussions
- Pull list integration

## Files

- `xmen-negative1-issue-snapshot.md` - Page snapshot
- Screenshot unavailable (ad blocking issues)

## Key Takeaway for Identity Engine

**Never rely on URL slugs for identity!**
- LoCG strips special characters from slugs
- `/comic/1169529/x-men-1` could refer to issue #1 OR #-1
- Internal database ID is the only reliable identifier
- Always store original issue number separately from URL identifiers
