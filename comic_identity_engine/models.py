"""Internal candidate models for source ingestion.

These models are now re-exported from longbox_commons.models for compatibility.
The module provides compatibility shims for deprecated methods.

Prefer importing from longbox_commons.models directly in new code.
"""

from longbox_commons.models import (
    ComicIdentity,
    IssueCandidate as LongboxIssueCandidate,
    SeriesCandidate as LongboxSeriesCandidate,
    SeriesInfo,
)

from typing import Any


class SeriesCandidate(LongboxSeriesCandidate):
    """Compatibility wrapper for longbox_commons.SeriesCandidate.

    Adds deprecated to_dict() method for backward compatibility.
    """

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Deprecated: Use .model_dump() instead (Pydantic method).
        """
        data = self.model_dump(exclude={"raw_payload"})
        return {k: v for k, v in data.items() if v is not None}


class IssueCandidate(LongboxIssueCandidate):
    """Compatibility wrapper for longbox_commons.IssueCandidate.

    Adds deprecated to_dict() and get_display_issue_number() methods
    for backward compatibility.
    """

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Deprecated: Use .model_dump() instead (Pydantic method).
        """
        data = self.model_dump(exclude={"raw_payload"})
        return {k: v for k, v in data.items() if v is not None}

    def get_display_issue_number(self) -> str:
        """Get the display form of issue number with variant suffix.

        Deprecated: Use .display_issue_number() instead.
        """
        return self.display_issue_number()


__all__ = [
    "SeriesCandidate",
    "IssueCandidate",
    "SeriesInfo",
    "ComicIdentity",
]
