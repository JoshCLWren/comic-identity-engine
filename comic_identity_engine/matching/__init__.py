"""GCD comic matching system."""

from .types import CLZInput, MatchConfidence, StrategyResult
from .normalizers import (
    normalize_series_name,
    normalize_series_name_strict,
    parse_issue_nr,
    parse_year,
    strip_diacritics,
    strip_vol_suffix,
)

__all__ = [
    "CLZInput",
    "MatchConfidence",
    "StrategyResult",
    "normalize_series_name",
    "normalize_series_name_strict",
    "parse_issue_nr",
    "parse_year",
    "strip_diacritics",
    "strip_vol_suffix",
]
