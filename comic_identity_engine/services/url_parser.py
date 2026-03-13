"""URL parser for comic platform URLs.

This module provides URL parsing for all 7 supported comic platforms:
- GCD (Grand Comics Database)
- LoCG (League of Comic Geeks)
- CCL (Comic Collector Live)
- AA (Atomic Avenue)
- CPG (Comics Price Guide)
- HIP (Hip Comic)
- CLZ (Comic Collector Live - CSV import only)

USAGE:
    from comic_identity_engine.services import parse_url

    parsed = parse_url("https://www.comics.org/issue/125295/")
    print(parsed.platform)  # "gcd"
    print(parsed.source_issue_id)  # "125295"
"""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from comic_identity_engine.errors import ParseError


@dataclass
class ParsedUrl:
    """Parsed URL data from comic platform.

    Attributes:
        platform: Platform code (gcd, locg, ccl, aa, cpg, hip, clz)
        source_series_id: Series ID on source platform (if available)
        source_issue_id: Issue ID on source platform
        variant_suffix: Variant suffix (e.g., "A", "B", "NS") if present in URL
        full_url: Full original URL (for platforms that need it like AA)
    """

    platform: str
    source_issue_id: str
    source_series_id: Optional[str] = None
    variant_suffix: Optional[str] = None
    full_url: Optional[str] = None


def parse_url(url: str) -> ParsedUrl:
    """Parse a comic platform URL into components.

    Args:
        url: URL from any supported comic platform

    Returns:
        ParsedUrl dataclass with platform, IDs, and variant info

    Raises:
        ParseError: If URL is malformed or from unsupported platform
        NotImplementedError: If platform is CLZ (CSV import only)

    Examples:
        >>> parse_url("https://www.comics.org/issue/125295/")
        ParsedUrl(platform='gcd', source_issue_id='125295', source_series_id=None, variant_suffix=None)

        >>> parse_url("https://leagueofcomicgeeks.com/comic/111275/x-men-1?variant=6930677")
        ParsedUrl(platform='locg', source_issue_id='1169529', source_series_id='111275', variant_suffix=None)

        >>> parse_url("https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991/-1/98ab98c9-a87a-4cd2-b49a-ee5232abc0ad")
        ParsedUrl(platform='ccl', source_issue_id='98ab98c9-a87a-4cd2-b49a-ee5232abc0ad', source_series_id=None, variant_suffix=None)
    """
    if not url or not isinstance(url, str):
        raise ParseError("URL must be a non-empty string")

    url = url.strip()

    if not url.startswith(("http://", "https://")):
        raise ParseError(f"URL must start with http:// or https://: {url}")

    # Strip port number if present to normalize URL
    parsed = urlparse(url)
    if parsed.port:
        # Reconstruct URL without port
        url = f"{parsed.scheme}://{parsed.netloc.split(':')[0]}{parsed.path}"
        if parsed.query:
            url += f"?{parsed.query}"
        if parsed.fragment:
            url += f"#{parsed.fragment}"

    if _is_clz_url(url):
        raise NotImplementedError(
            "CLZ (ComicBookDB) does not support URL parsing. Use CSV import instead."
        )

    platform_patterns = [
        ("GCD", _parse_gcd_url),
        ("LoCG", _parse_locg_url),
        ("CCL", _parse_ccl_url),
        ("AA", _parse_aa_url),
        ("CPG", _parse_cpg_url),
        ("HIP", _parse_hip_url),
    ]

    for platform_name, parser_func in platform_patterns:
        if _matches_platform(url, platform_name):
            try:
                return parser_func(url)
            except ParseError as e:
                raise ParseError(
                    f"Failed to parse {platform_name} URL: {e}",
                    source=platform_name.lower(),
                    original_error=e,
                ) from e

    raise ParseError(f"Unsupported or unrecognized URL format: {url}")


def _matches_platform(url: str, platform: str) -> bool:
    """Check if URL matches platform domain using urlparse.

    Args:
        url: URL to check
        platform: Platform name (GCD, LoCG, etc.)

    Returns:
        True if URL matches platform domain
    """
    domain_patterns = {
        "GCD": ["comics.org"],
        "LoCG": ["leagueofcomicgeeks.com"],
        "CCL": ["comiccollectorlive.com"],
        "AA": ["atomicavenue.com"],
        "CPG": ["comicspriceguide.com"],
        "HIP": ["hipcomic.com"],
        "CLZ": ["comicbookdb.com"],
    }

    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()

        if not hostname:
            return False

        domains = domain_patterns.get(platform, [])
        return any(
            hostname == domain or hostname.endswith(f".{domain}") for domain in domains
        )
    except Exception:
        return False


def _is_clz_url(url: str) -> bool:
    """Check if URL is from CLZ (ComicBookDB).

    Args:
        url: URL to check

    Returns:
        True if URL is from CLZ
    """
    return "comicbookdb.com" in url.lower()


def _parse_gcd_url(url: str) -> ParsedUrl:
    """Parse GCD (Grand Comics Database) URL.

    URL patterns:
    - comics.org/issue/ID/ (issue page)
    - comics.org/issue/ID (issue page without trailing slash)
    - comics.org/series/ID/ (series page - no issue ID)

    Args:
        url: GCD URL

    Returns:
        ParsedUrl with platform='gcd'

    Raises:
        ParseError: If URL cannot be parsed
    """
    issue_match = re.search(r"comics\.org/issue/(\d+)", url)
    if issue_match:
        issue_id = issue_match.group(1)
        return ParsedUrl(platform="gcd", source_issue_id=issue_id)

    series_match = re.search(r"comics\.org/series/(\d+)", url)
    if series_match:
        series_id = series_match.group(1)
        return ParsedUrl(
            platform="gcd",
            source_issue_id=series_id,
            source_series_id=series_id,
        )

    raise ParseError(f"Invalid GCD URL format: {url}")


def _parse_locg_url(url: str) -> ParsedUrl:
    """Parse LoCG (League of Comic Geeks) URL.

    URL patterns:
    - leagueofcomicgeeks.com/comic/ISSUE_ID[/slug]
    - leagueofcomicgeeks.com/comic/SERIES_ID/ISSUE_ID
    - leagueofcomicgeeks.com/comic/SERIES_ID/slug-ISSUE_NUM
    - leagueofcomicgeeks.com/comic/SERIES_ID/slug-ISSUE_NUM?variant=VARIANT_ID
    - leagueofcomicgeeks.com/comics/series/SERIES_ID/

    Args:
        url: LoCG URL

    Returns:
        ParsedUrl with platform='locg'

    Raises:
        ParseError: If URL cannot be parsed
    """
    # Check for variant query parameter (variant IDs)
    variant_match = re.search(r"variant=(\d+)", url)
    if variant_match:
        variant_id = variant_match.group(1)
        # For variant URLs, extract series ID from path
        series_match = re.search(r"/comic/(\d+)", url)
        if series_match:
            series_id = series_match.group(1)
            return ParsedUrl(
                platform="locg",
                source_issue_id=variant_id,
                source_series_id=series_id,
            )

    # Match series page
    series_match = re.search(r"/comics/series/(\d+)/", url)
    if series_match:
        series_id = series_match.group(1)
        return ParsedUrl(
            platform="locg",
            source_issue_id=series_id,
            source_series_id=series_id,
        )

    # Match issue page patterns - ORDER MATTERS!

    # Pattern 1: /comic/SERIES_ID/ISSUE_ID (two numeric IDs separated by /)
    # This matches URLs like /comic/111275/1169529 where we have two numbers
    # Must check BEFORE single ID pattern to correctly extract both IDs
    double_id_match = re.search(r"/comic/(\d+)/(\d+)(?:/|$)", url)
    if double_id_match:
        series_id = double_id_match.group(1)
        issue_id = double_id_match.group(2)
        return ParsedUrl(
            platform="locg",
            source_issue_id=issue_id,
            source_series_id=series_id,
        )

    # Pattern 2: /comic/ISSUE_ID[/slug] (single issue ID with optional slug)
    # This matches URLs like /comic/9092122/x-force-47 where 9092122 is the issue ID
    # This is the MOST COMMON LoCG URL format for issue pages
    # Must NOT match URLs already handled by Pattern 1 (double-ID URLs)
    # The regex matches: /comic/NUMBER or /comic/NUMBER/ or /comic/NUMBER/slug
    # But NOT /comic/NUMBER/NUMBER (which would be a double-ID URL)
    issue_match = re.search(r"/comic/(\d+)(?:/.*)?$", url)
    if issue_match:
        issue_id = issue_match.group(1)
        return ParsedUrl(
            platform="locg",
            source_issue_id=issue_id,
        )

    raise ParseError(f"Invalid LoCG URL format: {url}")


def _parse_ccl_url(url: str) -> ParsedUrl:
    """Parse CCL (Comic Collector Live) URL.

    URL patterns:
    - comiccollectorlive.com/issue/comic-books/SERIES-SLUG/ISSUE_NUM/GUID
    - comiccollectorlive.com/issue/SERIES_ID

    Args:
        url: CCL URL

    Returns:
        ParsedUrl with platform='ccl'

    Raises:
        ParseError: If URL cannot be parsed
    """
    guid_match = re.search(
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        url,
    )
    if guid_match:
        guid = guid_match.group(1)
        return ParsedUrl(
            platform="ccl",
            source_issue_id=guid,
        )

    raise ParseError(f"Invalid CCL URL format: {url}")


def _parse_aa_url(url: str) -> ParsedUrl:
    """Parse AA (Atomic Avenue) URL.

    URL patterns:
    - atomicavenue.com/atomic/item/ITEM_ID/1/slug
    - atomicavenue.com/atomic/series/SERIES_ID

    Args:
        url: AA URL

    Returns:
        ParsedUrl with platform='aa'

    Raises:
        ParseError: If URL cannot be parsed
    """
    item_match = re.search(r"/atomic/item/(\d+)", url)
    if item_match:
        item_id = item_match.group(1)

        variant_match = re.search(r"/item/\d+/(\d+)", url)
        if variant_match:
            variant_num = variant_match.group(1)
            if variant_num != "1":
                return ParsedUrl(
                    platform="aa",
                    source_issue_id=item_id,
                    variant_suffix=variant_num,
                    full_url=url,
                )

        return ParsedUrl(platform="aa", source_issue_id=item_id, full_url=url)

    series_match = re.search(r"/atomic/series/(\d+)", url)
    if series_match:
        series_id = series_match.group(1)
        return ParsedUrl(
            platform="aa",
            source_issue_id=series_id,
            source_series_id=series_id,
        )

    raise ParseError(f"Invalid AA URL format: {url}")


def _parse_cpg_url(url: str) -> ParsedUrl:
    """Parse CPG (Comics Price Guide) URL.

    URL patterns:
    - comicspriceguide.com/titles/SERIES_SLUG/ISSUE_NUM/ISSUE_ID
    - comicspriceguide.com/titles/SERIES_SLUG/ISSUE_NUM-VARIANT/ISSUE_ID

    Args:
        url: CPG URL

    Returns:
        ParsedUrl with platform='cpg'

    Raises:
        ParseError: If URL cannot be parsed
    """
    issue_match = re.search(r"/titles/[^/]+/([^/]+)/([a-z0-9]+)", url)
    if issue_match:
        issue_part = issue_match.group(1)
        issue_id = issue_match.group(2)

        variant_suffix = None
        if "-" in issue_part and issue_part != "-1":
            if issue_part.startswith("-1") and len(issue_part) > 2:
                variant_suffix = issue_part[2:]
            elif not issue_part.startswith("-"):
                parts = issue_part.rsplit("-", 1)
                if len(parts) == 2:
                    suffix = parts[1]
                    if suffix.isalpha():
                        variant_suffix = suffix

        return ParsedUrl(
            platform="cpg",
            source_issue_id=issue_id,
            variant_suffix=variant_suffix,
        )

    series_match = re.search(r"/titles/([^/]+)", url)
    if series_match:
        series_slug = series_match.group(1)
        return ParsedUrl(
            platform="cpg",
            source_issue_id=series_slug,
            source_series_id=series_slug,
        )

    raise ParseError(f"Invalid CPG URL format: {url}")


def _parse_hip_url(url: str) -> ParsedUrl:
    """Parse HIP (Hip Comic) URL.

    URL patterns:
    - hipcomic.com/price-guide/us/marvel/comic/SERIES_SLUG/ISSUE_ENCODED/
    - hipcomic.com/price-guide/us/marvel/comic/SERIES_SLUG/ISSUE_ENCODED/VARIANT_SLUG/

    Note: HIP uses special encoding for negative issue numbers (e.g., "1-1" for issue "-1")

    Args:
        url: HIP URL

    Returns:
        ParsedUrl with platform='hip'

    Raises:
        ParseError: If URL cannot be parsed
    """
    parsed = urlparse(url)
    path = parsed.path

    issue_match = re.search(r"/comic/([^/]+)/([^/]+)", path)
    if issue_match:
        series_slug = issue_match.group(1)
        issue_encoded = issue_match.group(2)

        variant_suffix = None
        path_parts = path.rstrip("/").split("/")
        if len(path_parts) > 1:
            last_part = path_parts[-1]
            if last_part != issue_encoded and last_part not in ["", "keywords"]:
                variant_suffix = last_part.replace("-", "").replace("_", "")

        return ParsedUrl(
            platform="hip",
            source_issue_id=issue_encoded,
            source_series_id=series_slug,
            variant_suffix=variant_suffix,
            full_url=url,
        )

    series_match = re.search(r"/comic/([^/]+)", path)
    if series_match:
        series_slug = series_match.group(1)
        return ParsedUrl(
            platform="hip",
            source_issue_id=series_slug,
            source_series_id=series_slug,
            full_url=url,
        )

    raise ParseError(f"Invalid HIP URL format: {url}")
