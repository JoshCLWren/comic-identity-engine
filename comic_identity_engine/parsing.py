from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class ParseResult:
    success: bool
    raw: str
    canonical_issue_number: Optional[str] = None
    variant_suffix: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def parse_issue_candidate(raw: str) -> ParseResult:
    """
    Parse a comic issue number candidate string.

    Args:
        raw: Raw input string (e.g., "#-1", "0.5", "12B", "1-3")

    Returns:
        ParseResult with success status, canonical issue number, variant suffix, and/or error
    """
    # Phase 1: Preprocessing
    if raw is None:
        return ParseResult(
            success=False,
            raw="",
            error_code="EMPTY_INPUT",
            error_message="Issue number cannot be empty",
        )

    # Preserve raw input
    preserved_raw = raw

    # Trim for processing
    working = raw.strip()

    # Check for empty after trim
    if not working:
        return ParseResult(
            success=False,
            raw=preserved_raw,
            error_code="EMPTY_INPUT",
            error_message="Issue number cannot be empty",
        )

    # Detect multi-issue ranges BEFORE pattern matching
    # Pattern: digits - digits (e.g., "1-3", "10-12")
    if re.match(r"^\d+\s*-\s*\d+$", working):
        return ParseResult(
            success=False,
            raw=preserved_raw,
            error_code="MULTI_ISSUE_RANGE",
            error_message="Multiple issues detected, use single issue parsing",
        )

    # Pattern: multiple hyphen-separated numbers (e.g., "1-2-3")
    if re.search(r"\d+-\d+-\d+", working):
        return ParseResult(
            success=False,
            raw=preserved_raw,
            error_code="MULTI_ISSUE_RANGE",
            error_message="Multiple issues detected, use single issue parsing",
        )

    # Pattern: digits & digits (e.g., "5 & 6")
    if re.search(r"\d+\s*&\s*\d+", working):
        return ParseResult(
            success=False,
            raw=preserved_raw,
            error_code="MULTI_ISSUE_RANGE",
            error_message="Multiple issues detected, use single issue parsing",
        )

    # Pattern: digits , digits (e.g., "7,8")
    if re.search(r"\d+\s*,\s*\d+", working):
        return ParseResult(
            success=False,
            raw=preserved_raw,
            error_code="MULTI_ISSUE_RANGE",
            error_message="Multiple issues detected, use single issue parsing",
        )

    # Pattern: letter range (e.g., "1A-1C")
    if re.match(r"^\d+[A-Za-z]\s*-\s*\d+[A-Za-z]$", working):
        return ParseResult(
            success=False,
            raw=preserved_raw,
            error_code="MULTI_ISSUE_RANGE",
            error_message="Multiple issues detected, use single issue parsing",
        )

    # Phase 2: Canonical Extraction
    # Strip leading #
    if working.startswith("#"):
        working = working[1:]
        working = working.lstrip()  # Remove any space after #

    # Check for empty string after stripping hash (e.g., "#")
    if not working:
        return ParseResult(
            success=False,
            raw=preserved_raw,
            error_code="ONLY_SEPARATOR",
            error_message="Issue number must contain digits",
        )

    # Check for only separator after stripping
    if working in ["-", ".", "/"]:
        return ParseResult(
            success=False,
            raw=preserved_raw,
            error_code="ONLY_SEPARATOR",
            error_message="Issue number must contain digits",
        )

    # Special non-numeric issue tokens (e.g., INF for ∞ infinity issues)
    special_token_match = re.match(r"^(INF)(?=[A-Za-z.]|$)", working, re.IGNORECASE)
    if special_token_match:
        canonical_issue_number = special_token_match.group(1).upper()
        working_after = working[len(canonical_issue_number):]
    else:
        # Canonical pattern: optional leading -, digits, optional decimal, optional slash
        # Valid: -1, 0, 0.5, 1/2, 0001
        # Invalid: ABC, 1..2, 1//2, 1-2-3, X-Men -1
        canonical_pattern = r"^(-?\d+(\.\d+)?(/\d+)?)"
        match = re.match(canonical_pattern, working)

        if not match:
            return ParseResult(
                success=False,
                raw=preserved_raw,
                error_code="INVALID_FORMAT",
                error_message="Invalid issue number format",
            )

        canonical_issue_number = match.group(0)
        working_after = working[len(canonical_issue_number):]

    # Phase 3: Variant Extraction
    # Check if there's a variant suffix after the canonical number
    variant_suffix = None
    remaining = working_after
    if remaining:
        # Variant must contain only letters and dots, and must start with letter or dot+letter
        # Allow patterns like: A, .DE, WIZ.SIGNED
        if remaining and re.match(r"^(\.?)[A-Za-z]", remaining):
            if re.match(r"^[A-Za-z\.]+$", remaining):
                # Strip leading dot if present
                variant_suffix = (
                    remaining[1:] if remaining.startswith(".") else remaining
                )
            else:
                # Has variant-like suffix but invalid chars
                return ParseResult(
                    success=False,
                    raw=preserved_raw,
                    error_code="INVALID_FORMAT",
                    error_message="Invalid issue number format",
                )
        elif remaining:
            # Has trailing content that's not a valid variant
            return ParseResult(
                success=False,
                raw=preserved_raw,
                error_code="INVALID_FORMAT",
                error_message="Invalid issue number format",
            )
        elif remaining:
            # Has trailing content that's not a valid variant
            return ParseResult(
                success=False,
                raw=preserved_raw,
                error_code="INVALID_FORMAT",
                error_message="Invalid issue number format",
            )
        elif remaining:
            # Has trailing content that's not a valid variant
            return ParseResult(
                success=False,
                raw=preserved_raw,
                error_code="INVALID_FORMAT",
                error_message="Invalid issue number format",
            )

    return ParseResult(
        success=True,
        raw=preserved_raw,
        canonical_issue_number=canonical_issue_number,
        variant_suffix=variant_suffix,
    )
