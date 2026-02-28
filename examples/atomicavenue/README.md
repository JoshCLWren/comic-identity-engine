# Atomic Avenue - X-Men #-1 Research

## Platform Overview

- **URL**: https://atomicavenue.com
- **Type**: Comic marketplace (owned by Human Computing, makers of ComicBase)
- **API**: Not publicly documented
- **License**: Proprietary
- **Backing**: Powered by ComicBase database

## X-Men #-1 Data (Atomic Avenue)

### Issue Identification
- **Item ID**: 217255
- **Title ID** (Series): 16287
- **Series**: X-Men (2nd Series)
- **Issue Number**: `-1` (displayed as "#-1")
- **Publication Date**: July, 1997
- **Cover Price**: $1.95
- **Writer**: Scott Lobdell
- **Artist**: Carlos Pacheco
- **Story**: "Flashback" / "I Had a Dream"

### Key Data Points

1. **Issue Number Display**: Shown as `#-1` in page title
2. **Variant System**: Uses dropdown with slash notation:
   - `-1` (base issue)
   - `-1/A` (Variation A - Chris Bachalo Wizard Exclusive)
   - `-1/B` (Variation B - Carlos Pacheco DF Signed)
   - `-1/NS` (Newsstand)
3. **URL Structure**: `/atomic/item/{item_id}/1/XMen-2nd-Series-XMen-2nd-Series-1`
4. **Marketplace**: 10 copies available from $1.58 to $3.50 (base issue)

### URL Structure Analysis

**POTENTIAL ISSUE**: URL slug ends with `1` not `-1`!

```
/atomic/item/217255/1/XMen-2nd-Series-XMen-2nd-Series-1
```

The item ID (217255) is authoritative, but the URL slug appears to truncate the negative sign.

### All Variants Found

| Variant | Item ID | Display Name | Price Range | Notes |
|---------|----------|--------------|-------------|-------|
| **Base** | 217255 | X-Men (2nd Series) #-1 | $1.58 - $3.50 | Direct Edition |
| **A** | 99122 | X-Men (2nd Series) #-1 Variation A | $44.95 | Chris Bachalo Wizard Exclusive |
| **B** | ? | X-Men (2nd Series) #-1/B | ? | Carlos Pacheco DF Signed |
| **NS** | ? | X-Men (2nd Series) #-1/NS | ? | Newsstand Edition |

### Marketplace Data

- **Base Issue**: 10 copies available
- **Price Range**: $1.58 - $3.50
- **Variation A**: 1 copy at $44.95 (significant premium)
- **Condition**: Near Mint to Very Fine/Near Mint

## Platform-Specific Observations

1. **ComicBase Integration**: Uses Human Computing's ComicBase database
2. **Item ID System**: Every issue/variant has unique numeric ID
3. **Variant Notation**: Uses slash (A, B, NS) similar to CCL
4. **Marketplace-First**: Focus on buying/selling, not just cataloging
5. **URL Slug Issue**: May truncate negative numbers in slugs

## Research Tasks

- [x] Find X-Men series page on Atomic Avenue
- [x] Locate issue #-1
- [x] Document issue number format
- [x] Capture AA item ID
- [x] Note variant information
- [x] Document URL structure
- [x] Observe marketplace features

## Notes

Atomic Avenue uses the ComicBase database, which is one of the oldest and most respected comic databases.
The item ID system appears to be the primary identifier, with URL slugs being secondary/for SEO.
