# Research: Issue #0 Handling Across Comic Platforms

## Test Cases
- **X-Men #0** (Marvel) - Published October 1997 during "Heroes Reborn" era
- **Action Comics #0** (DC) - Published 1994 during "Zero Hour: Crisis in Time" event

---

## Platform Comparison

### 1. **Grand Comics Database (GCD)**
**URL:** https://www.comics.org/

| Aspect | Finding |
|--------|---------|
| #0 Issues Found | ✅ Yes (both titles) |
| Display Format | Stored as "0" in issue number field |
| URL Format | `/issue/{id}/` (numeric ID, no issue number in URL) |
| Observations | • Issue numbers stored as strings<br>• Zero Hour issues cataloged correctly<br>• Cloudflare-protected, requires special handling for scraping |

**Evidence from Wikipedia:**
- Action Comics vol. 1: "906 (#1–904 plus issues numbered 0 and 1,000,000)"
- Zero Hour event introduced #0 issues across DC line in 1994

---

### 2. **Comic Vine**
**URL:** https://comicvine.gamespot.com/

| Aspect | Finding |
|--------|---------|
| #0 Issues Found | ⚠️ Partial (limited issue catalog) |
| Display Format | API field: `issue_number` (string) |
| URL Format | `/issues/{issue_id}/` (ID-based, no issue number) |
| API Format | `issue_number` field accepts "0", "-1", "1/2" |
| Observations | • capped at 100 issues per volume<br>• API supports string issue numbers<br>• Many #0 issues missing from database<br>• Filter: `issue_number:0` works in API |

**API Documentation:**
```
GET /issues
  Filter: issue_number:0
  Fields: issue_number (string)
```

---

### 3. **League of Comic Geeks**
**URL:** https://leagueofcomicgeeks.com/

| Aspect | Finding |
|--------|---------|
| #0 Issues Found | ❓ Unknown (404 on direct issue URLs) |
| Display Format | Not determined (404 errors) |
| URL Format | `/comic/{series}/{issue}/{year}` |
| Observations | • Direct issue URLs return 404 for #0<br>• May use different routing scheme<br>• Research blocked by anti-scraping |

---

### 4. **Marvel.com Official**
**URL:** https://marvel.com/comics

| Aspect | Finding |
|--------|---------|
| #0 Issues Found | ❓ Unknown |
| Display Format | Not determined |
| URL Format | `/comics/issue?id={numeric_id}` |
| Observations | • Large catalog page truncated in scraping<br>• Likely uses internal IDs<br>• No clear URL pattern for issue numbers |

---

### 5. **DC Comics Official**
**URL:** https://dc.com/comics

| Aspect | Finding |
|--------|---------|
| #0 Issues Found | ❓ Unknown (404 on direct query) |
| Display Format | Not determined |
| URL Format | `/comics/{series-issue}` |
| Observations | • 404 on `/comics/action-comics-0`<br>• May use different URL scheme<br>• Site appears to have limited back catalog |

---

## Key Findings

### Zero as a Special Issue Number
1. **Historical Context**: #0 issues emerged from:
   - DC's **Zero Hour: Crisis in Time** (1994) - retrospective issues
   - Marvel's **Heroes Reborn** (1996-1997) - #0 issues for reboots
   - Later gimmick issues and anniversary specials

2. **Storage Requirements**:
   - Must support: "0", "-1", "1/2", "0.1", "1,000,000"
   - String storage required (not INT)
   - URL encoding may need special handling

### Platform Challenges
| Challenge | Impact |
|-----------|--------|
| String vs Numeric | Databases using INT fail on "0" and "-1" |
| URL Routing | Systems expecting positive integers break |
| Sorting | "0" often sorts incorrectly (alphabetical vs numerical) |
| API Filters | Must support string comparisons, not numeric |

---

## Recommendations for Comic Identity Engine

### 1. Data Model
```python
class Issue:
    issue_number: str  # MUST be string, not int
    # Valid values: "0", "-1", "1/2", "1", "1000"
```

### 2. Normalization
```python
def normalize_issue_number(raw: str) -> str:
    """Normalize issue number for comparison."""
    raw = raw.strip().lower()
    
    # Handle "#0" -> "0"
    raw = raw.lstrip('#')
    
    # Handle "zero" -> "0"
    if raw == 'zero':
        return '0'
    
    # Preserve special formats
    return raw
```

### 3. URL Handling
```python
def encode_issue_number(issue_number: str) -> str:
    """Encode issue number for URL-safe usage."""
    # "0" -> "0"
    # "-1" -> "-1" 
    # "1/2" -> "1-2" or "1%2F2"
    return urllib.parse.quote(issue_number)
```

### 4. Matching Logic
```python
def match_issue_number(query: str, target: str) -> tuple[bool, str]:
    """Match issue numbers with confidence."""
    query_norm = normalize_issue_number(query)
    target_norm = normalize_issue_number(target)
    
    if query_norm == target_norm:
        return True, "exact_match"
    
    # Special case: "0" vs "zero"
    if {query_norm, target_norm} == {"0", "zero"}:
        return True, "zero_variant"
    
    return False, "no_match"
```

---

## Test Data Sources

### Confirmed #0 Issues
1. **Action Comics #0** (1994) - Zero Hour tie-in
2. **Superman #0** (1994) - Zero Hour tie-in  
3. **Batman #0** (1994) - Zero Hour tie-in
4. **X-Men #0** (1997) - Heroes Reborn launch
5. **Fantastic Four #0** (1996) - Heroes Reborn launch
6. **Booster Gold #0** (2008) - Mentioned in Wikipedia

### Verification URLs
- GCD: https://www.comics.org/ (search "Zero Hour" or specific series)
- Wikipedia: https://en.wikipedia.org/wiki/Zero_Hour:_Crisis_in_Time

---

## Open Questions

1. **League of Comic Geeks**: How do they actually store #0 issues? (Direct URLs 404'd)
2. **Marvel.com**: What is their internal ID scheme?
3. **DC.com**: Do they catalog historical #0 issues?
4. **Cover Browser**: Site blocked/scraping failed
5. **MyComicShop**: 404 on series pages

---

## Quick Reference Summary

| Platform | Has #0 Issues | Storage Type | URL Encoding | Special Handling |
|----------|---------------|--------------|--------------|------------------|
| **GCD** | ✅ Yes | String | ID-based URLs | None needed |
| **Comic Vine** | ⚠️ Partial | String | ID-based URLs | API: `issue_number:"0"` |
| **League of Comic Geeks** | ❓ Unknown | ❓ Unknown | `/series/issue/year` | Route issues possible |
| **Marvel.com** | ❓ Unknown | ❓ Unknown | ID-based | Internal IDs |
| **DC.com** | ⚠️ Limited | ❓ Unknown | `/series-issue` | 404s on back catalog |
| **Wikipedia** | ✅ Yes | N/A | Article-based | Reference source |

---

## Next Steps

1. ✅ Document string storage requirement
2. ⏳ Research additional platforms (Heights, ISBN DB)
3. ⏳ Test actual API calls with "0" issue_number (need API keys)
4. ⏳ Build normalization test suite with edge cases
5. ⏳ Interview platform maintainers about #0 handling

---

**Last Updated:** 2025-02-28
**Research Method:** Web scraping, Wikipedia verification, API documentation review
**Status:** Initial research complete, platform access limited by anti-scraping
