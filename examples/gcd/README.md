# Grand Comics Database (GCD) - X-Men #-1 Research

## Platform Overview

- **URL**: https://www.comics.org
- **Type**: Non-profit community database
- **API**: Available (in initial version, not fully stable)
- **License**: Creative Commons Attribution-ShareAlike 4.0

## X-Men #-1 Data (GCD)

### Issue Identification
- **GCD Issue ID**: 125295
- **Series**: X-Men (1991 series)
- **Series ID**: 4254
- **Issue Number**: `-1` (stored as string "-1")
- **Variant**: Direct Edition
- **Publication Date**: July 1997
- **On-sale Date**: 1997-05-21
- **Price**: 1.95 USD; 2.75 CAD

### Key Data Points

1. **Issue Number Storage**: Stored as string `"-1"` in the `number` field
2. **Sorting**: Positioned between issue #65 and #66 in the series dropdown
3. **Variants**: 2 additional variants exist (Variant Edition, Newsstand)
4. **Barcode**: 759606017720 99911
5. **Page Count**: 44 pages

### API Endpoint Structure

```
https://www.comics.org/api/issue/{issue_id}/?format=json
```

Example: `https://www.comics.org/api/issue/125295/?format=json`

### API Response Fields

Key fields for identity resolution:
- `number`: "-1" (string, not integer)
- `series`: URL to series API endpoint
- `variant_of`: null (this is the base issue)
- `publication_date`: "July 1997"
- `key_date`: "1997-07-00"
- `barcode`: "75960601772099911"
- `variant_name`: "Direct Edition"

### Variants

1. **Variant Edition**: Issue ID 1035261
2. **Newsstand Edition**: Issue ID 1125054

### Notes from Indexer

"Published between X-Men #65 and 66"

## Raw Data Files

- `raw/xmen-negative1-api-response.json` - Full API response
- `raw/xmen-negative1-issue-snapshot.md` - Page accessibility snapshot
- `raw/xmen-negative1-issue-page.png` - Screenshot

## Research Tasks

- [x] Find X-Men series page on GCD
- [x] Locate issue #-1
- [x] Document issue number format
- [x] Capture GCD issue ID
- [x] Note any variant information
- [x] Save raw API response

## Platform-Specific Observations

1. GCD correctly handles negative issue numbers as strings
2. Internal IDs are all positive integers
3. Sorting logic handles "-1" correctly (between #65 and #66)
4. Barcode includes "99911" suffix (likely variant indicator)
