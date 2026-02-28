# X-Men #-1 Platform Research

This directory contains raw data and documentation about how different comic platforms handle the edge case of **X-Men #-1** (published 1997).

## Why X-Men #-1?

This issue is a canonical test case for comic identity systems because:
- Negative issue numbers are rare but valid
- Many systems cast issue numbers to integers (breaks on -1)
- Multiple publishers used #-1 issues in the late 1990s
- Different platforms handle it differently

## Research Goals

1. Document how each platform stores/displays issue number `-1`
2. Identify platform-specific IDs and metadata
3. Note any workarounds or data quality issues
4. Collect raw API responses for reference

## Platform Data

Each platform gets its own subdirectory with:
- `README.md` - Platform-specific notes
- `raw/` - Raw API responses/screenshots
- `normalized.json` - Mapped to canonical model (when ready)

## Platforms to Research

- [x] Grand Comics Database (GCD)
- [x] League of Comic Geeks
- [x] Comic Collector Live
- [x] Atomic Avenue
- [x] CLZ (Collectorz.com)
- [x] Comics Price Guide (CPG)
- [x] HIP Comic

## Notes

- All raw data preserved exactly as received
- Document API version and access date
- Note rate limits and authentication requirements
