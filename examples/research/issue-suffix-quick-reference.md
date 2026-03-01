# Issue Suffix Formats - Quick Reference

## Summary Table: Suffix Formats Found | Platform | Storage Method | Complexity Level | Examples

| Suffix Format | Platform | Storage Method | Complexity | Examples |
|---------------|----------|----------------|-------------|----------|
| **Letter Variants** | | | | |
| A/B/C single letters | CLZ, CPG, AA | Combined string | LOW | `#-1A`, `#-1B`, `#1/C` |
| **Distribution Codes** | | | | |
| .DE, .NE (dot notation) | MyComicShop, CPG | Combined string | LOW | `#1.DE`, `#1.NE` |
| /DE, /NS (slash notation) | Atomic Avenue | Slash separator | LOW | `#-1/DE`, `#-1/NS` |
| **Event Codes** | | | | |
| .WIZ (Wizard World) | MyComicShop | Combined string | MEDIUM | `#-1.WIZ` |
| .SDCC, .NYCC | MyComicShop | Combined string | MEDIUM | `#1.SDCC`, `#1.NYCC` |
| .EMERALDCITY | MyComicShop | Combined string | MEDIUM | `#1.EMERALDCITY` |
| **Complex Event Codes** | | | | |
| .WIZ.SIGNED | MyComicShop | Multi-part dot-separated | HIGH | `#-1.WIZ.SIGNED` |
| .SDCC.EXCLUSIVE | MyComicShop | Multi-part dot-separated | HIGH | `#1.SDCC.EXCLUSIVE` |
| **Retailer Codes** | | | | |
| -AMERE (American Entertainment) | CPG | Hyphen-separated | HIGH | `#-1-AMERE` |
| -BCS, -FW, -LCSD | Various | Hyphen-separated | HIGH | `#1-BCS`, `#1-FW` |
| **Special Edition Types** | | | | |
| .Annual | MyComicShop | Combined string | MEDIUM | `#1.Annual` |
| .Special | MyComicShop | Combined string | MEDIUM | `#1.Special` |
| .Preview | MyComicShop | Combined string | MEDIUM | `#1.Preview` |
| .Director | MyComicShop | Combined string | MEDIUM | `#1.Director` |
| **Compound Suffixes** | | | | |
| Multiple dot-separated | MyComicShop | Multi-part dot-separated | VERY HIGH | `#1.DD.DE` |
| Multiple hyphen-separated | CPG | Multi-part hyphen-separated | VERY HIGH | `#1-AMERE-NEW` |
| **GCD Approach** | | | | |
| None (separate entities) | GCD | Separate issue IDs | N/A | Each variant = unique ID |
| **AA Approach** | | | | |
| Slash notation | Atomic Avenue | Slash separator | LOW | `#-1/A`, `#-1/B`, `#-1/NS` |
| **CCL Approach** | | | | |
| UUID-based | CCL | Separate UUID entities | N/A | UUID per variant |

## Complexity Categories

### LOW Complexity
- Single letter variants: A, B, C, D...
- Standard distribution codes: DE, NE, NS
- Predictable 2-3 character codes
- Simple parsing: extract after issue number

**Parsing Approach**: Split on separator or take last character(s)

### MEDIUM Complexity
- Named editions: Annual, Special, Preview, Director
- Event codes: SDCC, NYCC, WIZ, ETC
- Variable length but standardized terms
- Case normalization may be needed

**Parsing Approach**: Dictionary lookup for known terms, normalize to uppercase

### HIGH Complexity
- Retailer-specific codes: AMERE, BCS, FW, LCSD
- Multi-part suffixes: WIZ.SIGNED, SDCC.EXCLUSIVE
- Requires lookup table or external reference
- May have ambiguous abbreviations

**Parsing Approach**: Maintain registry of codes, tokenize on dots/hyphens

### VERY HIGH Complexity
- Compound suffixes with multiple separators
- Unknown or custom retailer codes
- Non-standard combinations
- May require platform-specific parsing

**Parsing Approach**: Per-platform parsing rules, fallback to raw string

## Storage Method Patterns

### Combined String (Most Common)
- Platforms: MyComicShop, CPG, CLZ
- Format: Issue number + suffix without space or with dot
- Examples: `#-1A`, `#1.DE`, `#-1.WIZ.SIGNED`
- Pros: Compact, human-readable
- Cons: Requires parsing, ambiguous without context

### Slash Notation
- Platforms: Atomic Avenue
- Format: Issue number + slash + code
- Examples: `#-1/A`, `#-1/NS`
- Pros: Clear separator, easy to parse
- Cons: Not universal, inconsistent across platforms

### Hyphen-Separated
- Platforms: CPG (for retailer codes)
- Format: Issue number + hyphen + code
- Examples: `#-1-AMERE`
- Pros: Clear separator for complex codes
- Cons: Inconsistent with dot notation elsewhere

### Separate Entities
- Platforms: GCD, CCL
- Format: Each variant is a separate record
- Examples: Unique ID per variant, no suffix in issue number
- Pros: Cleanest data model, no parsing needed
- Cons: Less intuitive for simple cases

## Edge Cases by Platform

### MyComicShop
- Most complex suffix combinations
- Uses dot notation extensively
- May have 3+ parts: `#1.DD.DE.VARIANT`
- Case sensitive (all uppercase)

### GCD
- No suffix system - each variant is separate issue
- Issue number stored as plain string: `"number": "-1"`
- Variant information in descriptive text field
- Cleanest but requires separate records

### CPG
- Uses hyphens for complex retailer codes
- Mix of simple letters and complex codes: `-1B`, `-1-AMERE`
- Alphanumeric issue IDs separate from issue number

### Atomic Avenue
- Consistent slash notation
- Simple codes only: A, B, NS, DE
- Most predictable of combined-string approaches

### CLZ
- No separator between issue and variant
- Compact: `#-1A`
- Ambiguous: Is `-1A` one token or two?

### CCL
- UUID-based system, suffix is display-only
- Cleanest model but requires database
- Not parseable from string representation

## Recommendations for Implementation

### 1. Parse in Stages
```
Raw string → Extract issue number → Extract suffix → Classify suffix → Tokenize components
```

### 2. Use Separator Detection
- If contains `/`: Slash notation (AA)
- If contains `.` in suffix part: Dot notation (MCS)
- If contains `-`: Hyphen notation (CPG)
- If no separator: Combined (CLZ) or single entity (GCD)

### 3. Maintain Suffix Registry
```json
{
  "distribution": {
    "DE": "direct_edition",
    "NE": "newsstand_edition",
    "NS": "newsstand"
  },
  "retailers": {
    "AMERE": "american_entertainment",
    "BCS": "big_bland_comics"
  },
  "events": {
    "SDCC": "san_diego_comic_con",
    "NYCC": "new_york_comic_con",
    "WIZ": "wizard_world"
  }
}
```

### 4. Handle Unknown Suffixes
- Preserve raw suffix value
- Flag for manual review
- Don't fail on unrecognized codes

## Test Cases

```python
# Simple letter variants
parse("#-1A") → {issue: "-1", suffix: "A", type: "letter"}
parse("#1B") → {issue: "1", suffix: "B", type: "letter"}

# Distribution codes
parse("#1.DE") → {issue: "1", suffix: "DE", type: "distribution"}
parse("#-1/NS") → {issue: "-1", suffix: "NS", type: "distribution"}

# Event codes
parse("#1.SDCC") → {issue: "1", suffix: "SDCC", type: "event"}
parse("#-1.WIZ") → {issue: "-1", suffix: "WIZ", type: "event"}

# Complex suffixes
parse("#-1.WIZ.SIGNED") → {issue: "-1", suffix: "WIZ.SIGNED", type: "event", components: ["WIZ", "SIGNED"]}
parse("#1-AMERE") → {issue: "1", suffix: "AMERE", type: "retailer"}

# Edge cases
parse("#-1") → {issue: "-1", suffix: null}
parse("#0.5") → {issue: "0.5", suffix: null}
parse("#1/2") → {issue: "1/2", suffix: null}
```
