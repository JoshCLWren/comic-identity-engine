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


def normalize_series_name(name: str) -> str:
    """Remove publisher suffixes, volume info, articles for clean matching."""
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

    return result.strip()


def normalize_series_name_strict(name: str) -> str:
    """Strip all punctuation and normalize &/and for deep matching."""
    result = normalize_series_name(name)
    result = result.lower()
    result = result.replace("&", "and")
    result = re.sub(r"[^a-z0-9\s]", "", result)
    result = re.sub(r"\s+", " ", result)
    return result.strip()


def parse_issue_nr(row: dict) -> str | None:
    """Parse CLZ issue number from CSV row dict."""
    value = row.get("Issue Nr", "")
    if not value:
        return "1"
    try:
        return str(int(float(value)))
    except (ValueError, TypeError):
        return None


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
