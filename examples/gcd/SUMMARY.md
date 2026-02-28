# GCD X-Men #-1 Data Summary

## Quick Reference

| Field | Value |
|-------|-------|
| Platform | Grand Comics Database |
| Issue ID | 125295 |
| Series ID | 4254 |
| Series Name | X-Men (1991 series) |
| Issue Number | `-1` (string) |
| Publisher | Marvel Comics |
| Publication Date | July 1997 |
| On-sale Date | 1997-05-21 |
| Price | $1.95 USD / $2.75 CAD |
| Pages | 44 |
| Barcode | 759606017720 99911 |

## Issue Number Handling

**CRITICAL**: GCD stores the issue number as a **string** `"-1"`, not an integer.

This is the correct approach for identity systems:
- JSON field: `"number": "-1"`
- Type: string
- Prevents data loss from casting to int

## Variants

| Variant | Issue ID | Notes |
|---------|----------|-------|
| Direct Edition | 125295 | Base issue |
| Variant Edition | 1035261 | Different cover |
| Newsstand | 1125054 | Newsstand distribution |

## Contents

1. **Flashback** (cover, 1 page)
   - Pencils: Carlos Pacheco
   - Inks: Art Thibert

2. **I Had a Dream** (comic story, 22 pages)
   - Script: Scott Lobdell
   - Pencils: Carlos Pacheco
   - Inks: Art Thibert
   - Synopsis: Stan introduces a past tale of Xavier and Magneto

3. **Let's Visit the X-Men** (letters page, 2 pages)

4. **Operation Zero Tolerance Interview** (text article, 3 pages)

## Identity Implications

### Positive Observations
- ✅ Issue number stored as string
- ✅ Internal IDs are positive integers
- ✅ API provides stable URLs
- ✅ Variant system is explicit

### Concerns
- ⚠️ Indexer note "Published between X-Men #65 and #66" suggests sorting ambiguity
- ⚠️ Negative numbers in dropdowns may confuse users
- ⚠️ No canonical issue UUID outside GCD's internal system

## Files

- `xmen-negative1-api-response.json` - Full issue API data
- `xmen-1991-series-api-response.json` - Series data
- `xmen-negative1-issue-snapshot.md` - Page snapshot
- `xmen-negative1-issue-page.png` - Screenshot
