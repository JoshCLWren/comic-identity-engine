# League of Comic Geeks - X-Men #-1 Research

## Platform Overview

- **URL**: https://leagueofcomicgeeks.com
- **Type**: Community comic database with collection tracking
- **API**: Not publicly documented
- **License**: Proprietary

## X-Men #-1 Data (League of Comic Geeks)

### Issue Identification
- **Comic ID**: 1169529
- **URL**: https://leagueofcomicgeeks.com/comic/1169529/x-men-1
- **Series**: X-Men (1991 - 2001)
- **Series ID**: 111275
- **Issue Number**: `-1` (displayed as "#-1")
- **Publication Date**: May 21, 1997 (release date)
- **Cover Date**: July 1997
- **Price**: $1.95 USD
- **UPC**: 75960601772099911
- **Page Count**: 32 pages

### Key Data Points

1. **Issue Number Display**: Shown as `X-Men #-1` in title
2. **URL Structure**: Uses `x-men-1` slug (not `x-men--1` - the hyphen is stripped!)
3. **Sorting**: Positioned between #65 and #66 in series navigation
4. **Variants**: 2 variants shown (Carlos Pacheco Variant, Newsstand Edition)
5. **Community Features**: Ratings (3.9/5, 85 ratings), reviews, collection tracking

### URL Structure Analysis

**CRITICAL**: The URL slug is `x-men-1`, NOT `x-men--1`!

```
/comic/1169529/x-men-1
```

This suggests:
- The platform may strip or normalize special characters in slugs
- Internal ID (1169529) is the authoritative identifier
- Slug is for SEO/readability, not identity

### Variants

1. **Carlos Pacheco Variant**: variant=6930677
2. **Newsstand Edition**: variant=8963556

Variant URL format:
```
/comic/1169529/x-men-1?variant=6930677
```

### Community Data

- **Rating**: 3.9/5 (85 ratings)
- **Collection Status**:
  - 1,346 users have it
  - 677 users read it
  - 668 users want it
- **Reviews**: 2 user reviews
- **Discussions**: Community threads mention difficulty finding this issue

### Page Count Discrepancy

**Issue**: LoCG lists 32 pages vs GCD's 44 pages

Possible explanations:
- Different counting methodology (ads vs content)
- GCD includes covers/ads in count
- LoCG counts only story pages
- Needs investigation

## Raw Data Files

- `raw/xmen-negative1-issue-snapshot.md` - Page accessibility snapshot
- Screenshot failed due to page load/ad blocking issues

## Platform-Specific Observations

1. Community-focused with ratings and reviews
2. Heavy on ads/script tracking (causes scraping issues)
3. Uses numeric IDs internally
4. URL slugs may not be unique identifiers
5. Variant system uses query parameters

## Research Tasks

- [x] Find X-Men series page on LoCG
- [x] Locate issue #-1
- [x] Document issue number format
- [x] Capture LoCG comic ID
- [x] Note any variant information
- [x] Observe URL structure issues
- [x] Document community features
