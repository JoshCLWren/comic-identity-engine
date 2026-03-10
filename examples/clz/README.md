# CLZ (Collectorz.com) - X-Men #-1 Research
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


## Platform Overview

- **Product**: Comic Collector CLZ
- **Type**: Personal collection management software/app
- **Database**: Proprietary user-contributed database
- **License**: Commercial software
- **URL**: https://www.collectorz.com/comic

## X-Men #-1 Data (CLZ)

### Issue Identification
- **Series**: X-Men, Vol. 1
- **Issue Number**: `#-1A` (variant notation)
- **Title**: "I Had a Dream"
- **Edition**: Direct Edition
- **Release Date**: May 21, 1997
- **Cover Date**: Jul 1997
- **Publisher**: Marvel Comics
- **UPC/Barcode**: 75960601772099911
- **Pages**: 32
- **Cover Price**: $1.95

### Key Data Points

1. **Variant Notation**: Uses `#-1A` format (issue + variant letter combined)
2. **Date Distinction**: Clearly separates Release Date (May 21) from Cover Date (July)
3. **Barcode Matching**: UPC 75960601772099911 matches GCD exactly
4. **Page Count**: 32 pages (resolves GCD vs LoCG discrepancy!)

### UPC Comparison

| Platform | UPC |
|----------|-----|
| GCD | 759606017720 99911 |
| LoCG | 75960601772099911 |
| CLZ | 75960601772099911 |

Note: GCD shows with space, others without. Same UPC.

### Page Count Resolution

**Important**: CLZ lists 32 pages, which matches LoCG and differs from GCD's 44.

Possible explanation:
- GCD may include covers, ads, and editorials
- CLZ/LoCG may count only story pages
- Or GCD's count includes all content pages

### Variant Notation System

CLZ uses compact format: `#-1A`

This is different from:
- GCD: Separate variant field with text description
- LoCG: Query parameter ?variant=XXXX
- CCL: Letter codes (A, B, C) but separate from issue number
- AA: Slash notation (-1/A)

CLZ's approach: Combine issue and variant into single string.

### Creators

**Writer**: Scott Lobdell
**Cover**: Carlos Pacheco (pencils), Art Thibert (inks), Liquid! Graphics (colors)
**Interior**: Carlos Pacheco (pencils), Art Thibert (inks)
**Colors**: Christian Lichtner, Aron Lusen
**Letters**: Richard Starkings
**Editing**: Robert Harras (editor), Bob Harras (editor-in-chief)

### Characters Listed

Scarlet Witch, Professor X, Quicksilver, Magneto, Bastion, Stan Lee (cameo), Amelia Voght

### Platform-Specific Observations

1. **User-Contributed Database**: CLZ's database is built from user submissions
2. **Variant System**: Uses compact #-1A notation (efficient but parsing needed)
3. **Date Precision**: Tracks both release and cover dates separately
4. **Personal Collection Features**: Box storage, read status, personal rating, value tracking
5. **Index System**: Has internal "Index 872" - likely CLZ's internal ID

## Research Tasks

- [x] Document CLZ issue number format
- [x] Note variant notation (#-1A)
- [x] Compare UPC across platforms
- [x] Resolve page count discrepancy
- [x] Note release vs cover date distinction
- [x] Document creator credits

## Notes

CLZ is personal collection software, not a public database like GCD.
The data is user-contributed and may vary in accuracy.
The UPC match with GCD/LoCG validates this is the same issue.
