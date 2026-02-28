# Comic Collector Live - X-Men #-1 Research

## Platform Overview

- **URL**: https://www.comiccollectorlive.com
- **Type**: Comic marketplace with collection tracking
- **API**: Not publicly documented
- **License**: Proprietary

## X-Men #-1 Data (Comic Collector Live)

### Issue Identification
- **Issue ID**: 98ab98c9-a87a-4cd2-b49a-ee5232abc0ad (Variant A - Direct Edition)
- **Series**: X-Men (1991)
- **Series ID**: 84ac79ed-2a10-4a38-9b4c-6df3e0db37de
- **Issue Number**: `-1` (displayed as "-1")
- **Publication Date**: July 01, 1997
- **Sale Date**: May 21, 1997
- **Price**: $1.95 USD (Variant A, B, C) / $1.99 USD (Variant D - Newsstand)

### Key Data Points

1. **Issue Number Display**: Shown as `-1` in page title and variant designation
2. **URL Structure**: `/issue/comic-books/X-Men-1991/-1/{guid}`
3. **Variant System**: Uses variant letters (A, B, C, D) in issue designation
4. **GUID System**: Each variant has a unique UUID

### All Variants Found

| Variant | Cover Artist | Type | Price | GUID |
|---------|-------------|------|-------|------|
| **A** | Carlos Pacheco | Direct Edition | $1.95 | 98ab98c9-a87a-4cd2-b49a-ee5232abc0ad |
| **B** | Chris Bachalo | Wizard Exclusive | $1.95 | f352ec33-f77b-4fa6-9d47-7927c39c4a9b |
| **C** | Carlos Pacheco | DF Signed (1/500) | $1.95 | e6fa653b-d05e-45db-98ee-de21965bedea |
| **D** | Carlos Pacheco | Newsstand | $1.99 | d8bb220a-4330-4749-a219-dc889e59b65c |

### URL Structure Analysis

**EXCELLENT**: CCL correctly handles negative issue numbers in URLs!

```
/issue/comic-books/X-Men-1991/-1/{guid}
```

This is much better than League of Comic Geeks which strips the negative sign.

### Variant URLs

Variants use descriptive slugs:
- A: `-1/98ab98c9-a87a-4cd2-b49a-ee5232abc0ad`
- B: `-1-B-Chris-Bachalo-Cover/f352ec33-f77b-4fa6-9d47-7927c39c4a9b`
- C: `-1-C-DF-Carlos-Pacheco-Cover-Signed-by-Lobdell-1500/e6fa653b-d05e-45db-98ee-de21965bedea`
- D: `-1-D-Carlos-Pacheco-Cover-Newsstand/d8bb220a-4330-4749-a219-dc889e59b65c`

### Marketplace Data

- Multiple sellers listing copies (8+ for Variant A)
- Price range: $0.99 - $5.99 depending on condition
- Community collection tracking features
- Reviews and ratings available

## Platform-Specific Observations

1. **UUID-based system**: Every issue variant gets a unique GUID
2. **Preserves negative numbers**: URLs correctly show `-1`
3. **Variant navigation**: Previous/Next buttons between variants
4. **Price variance**: Newsstand (D) is $1.99 vs $1.95 for direct market
5. **Marketplace-first**: Focus is on buying/selling, not just cataloging

## Research Tasks

- [x] Find X-Men series page on CCL
- [x] Locate issue #-1
- [x] Document issue number format
- [x] Capture CCL issue GUIDs for all variants
- [x] Note variant information
- [x] Document URL structure
- [x] Observe marketplace features

## Notes

CCL uses UUIDs (GUIDs) for all entities, which is ideal for identity systems.
Each variant is a separate database entity with its own UUID.
