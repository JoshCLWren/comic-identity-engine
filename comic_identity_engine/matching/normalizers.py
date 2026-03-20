"""Series name normalization utilities for GCD matching."""

from __future__ import annotations

import re
import unicodedata


def strip_diacritics(text: str) -> str:
    """Normalize unicode diacritics so e.g. 'Rōnin' matches 'Ronin'."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def strip_vol_suffix(name: str) -> str:
    """Strip ", Vol. X" or ", Volume X" suffix from end of series name.

    Handles all variants: "Vol. 1", "Vol 1", "Volume 1", "Vol.2", etc.
    Only strips from END of string.
    """
    pattern = r",?\s*(Vol\.?|Volume)\s*\d+\s*$"
    return re.sub(pattern, "", name, flags=re.IGNORECASE).rstrip()


def strip_subtitle(name: str) -> str:
    """Strip subtitle after colon from series name.

    Handles patterns like "WildC.A.T.s: Covert Action Teams".
    Does NOT strip dashes as they're common in series names (e.g., X-Men).
    """
    return re.sub(r"\s*[:]\s*[^:]+$", "", name)


def extract_base_series_name(name: str) -> str:
    """Extract base series name without subtitle (for fuzzy matching).

    Handles patterns like:
    - "B.P.R.D.: Hell on Earth" → "B.P.R.D."
    - "B.P.R.D.: Hell on Earth — New World" → "B.P.R.D."
    - "X-Men: Legacy" → "X-Men"

    Strips everything after the first colon or em-dash.
    """
    if not name:
        return ""
    # Strip subtitle after colon, em-dash, or en-dash (NOT regular hyphen)
    result = re.sub(r"\s*[:\u2014\u2013]\s*.+$", "", name)
    return result.strip()


def normalize_series_name(name: str) -> str:
    """Remove publisher suffixes, volume info, year parens, articles for clean matching."""
    result = name

    result = re.sub(
        r"\s*\((?:Marvel|Comic Books|Cartoon Books)[^)]*\)\s*$",
        "",
        result,
        flags=re.IGNORECASE,
    )

    result = re.sub(
        r",?\s*(?:Vol\.?|Volume)\s*\d+(\s+|$)",
        r"\1",
        result,
        flags=re.IGNORECASE,
    )

    result = re.sub(r"\s+(?:II|III)\s*$", "", result, flags=re.IGNORECASE)

    result = re.sub(r",?\s*Annual\s*$", "", result, flags=re.IGNORECASE)

    result = re.sub(r"\s*\(\d{4}\)\s*$", "", result, flags=re.IGNORECASE)

    return result.strip()


def normalize_series_name_strict(name: str) -> str:
    """Strip all punctuation and normalize &/and for deep matching."""
    result = normalize_series_name(name)
    result = result.lower()
    result = result.replace("&", "and")
    result = re.sub(r"[^a-z0-9\s]", "", result)
    result = re.sub(r"\s+", " ", result)
    return result.strip()


def normalize_issue_number(value: str) -> str | None:
    """Normalize CLZ issue number to GCD format.

    Maps special issue formats to GCD equivalents:
    - "½", "1/2" → "0.5"
    - "Annual", "Ann" → "Annual"
    - "AU" → "AU" (kept as-is for variant matching)
    """
    if not value:
        return "1"

    value = value.strip()

    # Handle half issues: ½, 1/2, 0.5
    if value == "½" or value == "1/2":
        return "0.5"

    # Handle Annual issues
    if value.lower() in ("annual", "ann"):
        return "Annual"

    # Handle AU (Age of Ultron) and similar variant suffixes - keep as-is
    if value.isalpha():
        return value

    # Handle mixed like "1AU", "2AU" - these are variants, return as-is
    if any(c.isalpha() for c in value) and any(c.isdigit() for c in value):
        return value

    # Standard numeric parsing
    try:
        return str(int(float(value)))
    except (ValueError, TypeError):
        return None


def parse_issue_nr(row: dict) -> str | None:
    """Parse CLZ issue number from CSV row dict."""
    value = row.get("Issue Nr", "")
    return normalize_issue_number(value)


def parse_year(row: dict) -> int | None:
    """Parse cover year from CSV row dict."""
    value = row.get("Cover Year", "")
    if not value:
        return None
    try:
        year = int(float(value))
        if 1950 <= year <= 2026:
            return year
        return None
    except (ValueError, TypeError):
        return None


def normalize_publisher(publisher: str) -> str:
    """Normalize publisher name for matching.

    Maps common CLZ-style names to GCD-style names:
    - "Marvel Comics" → "Marvel"
    - "DC Comics" → "DC"
    - "Image Comics" → "Image"
    - "Dark Horse Comics" → "Dark Horse"

    Also handles publishers with slashes (e.g., "DC Comics and Marvel Comics"
    returns "DC" as the primary).
    """
    if not publisher:
        return ""

    p = publisher.strip()

    p = re.sub(r"\s+and\s+.+$", "", p, flags=re.IGNORECASE)

    p = re.sub(r"\s*\(.*\)\s*$", "", p)

    p = re.sub(r"\s+Publishing\s*$", "", p, flags=re.IGNORECASE)

    p = re.sub(r"\s+Comics\s*$", "", p, flags=re.IGNORECASE)

    p = re.sub(r"\s+Entertainment\s*$", "", p, flags=re.IGNORECASE)

    return p.strip().lower()
