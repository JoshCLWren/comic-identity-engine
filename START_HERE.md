# START_HERE.md - How to Use Comic Identity Engine

**Status:** ✅ WORKING - Cross-platform search functional  
**Date:** 2026-03-05  
**Recent Fix:** Replaced `comic-web-scrapers` with `comic-search-lib` (simplified, no Redis dependency)

---

## Quick Start

### 1. Make sure services are running

```bash
# Check Docker containers
docker ps | grep comic-identity-engine

# You should see:
# - comic-identity-engine-postgres-app-1 (port 5434)
# - comic-identity-engine-redis-1 (port 6381)
# - cie-api-server (port 8000)
# - cie-worker
```

### 2. Try resolving a comic URL

```bash
# Using the CLI
uv run cie-find "https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991/1/60580fdf-e19b-40dc-84c9-0f043807992c" -o json

# Or verbose mode
uv run cie-find "https://www.comics.org/issue/125295/" -v
```

### 3. Using the API directly

```bash
# Start the API (if not running)
uv run cie-api

# In another terminal:
curl -X POST "http://localhost:8000/api/v1/resolve" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991/1/60580fdf-e19b-40dc-84c9-0f043807992c"}'
```

---

## What This System Does

1. **Parse any comic URL** from supported platforms (GCD, LoCG, CCL, AA, HipComic, CPG, CLZ)
2. **Fetch issue data** from that platform
3. **Search cross-platform** to find the same comic on other platforms
4. **Store mappings** in database for future lookups
5. **Return all URLs** for that comic across all platforms

---

## Supported Platforms

- ✅ GCD (Grand Comics Database)
- ✅ LoCG (League of Comic Geeks)
- ✅ CCL (Comic Collector Live)
- ✅ AA (Atomic Avenue)
- ✅ HipComic
- ✅ CPG (Comics Price Guide)
- ✅ CLZ (Collectorz)

---

## CLI Commands

```bash
# Resolve a URL
cie-find <URL>

# Output formats
cie-find <URL> -o json    # JSON output
cie-find <URL> -o table   # Table format
cie-find <URL> -o urls    # Just the URLs

# Options
--no-wait      # Submit and return immediately (don't wait for completion)
--timeout 60   # Max wait time
--api-url      # Custom API URL
-v             # Verbose output
```

---

## Running Tests

```bash
# All tests
uv run pytest tests/ -v

# Specific test
uv run pytest tests/adapters/test_gcd.py -v

# With coverage
uv run pytest --cov=comic_identity_engine tests/
```

---

## Development

See `AGENTS.md` for:
- Code style guidelines
- Testing requirements  
- Architecture patterns
- Build commands

---

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://comic_user:comic_pass@localhost:5434/comic_identity

# Redis
REDIS_URL=redis://localhost:6381/1

# API
API_HOST=0.0.0.0
API_PORT=8000
```

---

## Recent Changes (2026-03-05)

**Fixed:** Cross-platform search now works!
- Created `comic-search-lib` package (simplified scrapers, no Redis)
- Integrated into `identity_resolver.py`
- Removed dependency on `comic-web-scrapers`

**Tests:** All passing (1,186 tests)
