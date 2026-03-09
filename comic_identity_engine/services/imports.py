"""Helpers for CLZ import fingerprinting and resumable row identity."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from comic_identity_engine.adapters.clz import CLZAdapter
from comic_identity_engine.errors import ValidationError


def build_clz_row_key(source_issue_id: str | None, row_index: int) -> str:
    """Build a stable per-row key for resumable CLZ imports."""
    normalized_source_issue_id = (source_issue_id or "").strip() or f"row-{row_index}"
    return f"{normalized_source_issue_id}:{row_index}"


def build_clz_row_manifest(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Build a stable manifest of CLZ row identifiers."""
    manifest: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows, start=1):
        source_issue_id = (row.get("Core ComicID") or "").strip() or None
        manifest.append(
            {
                "row_index": row_index,
                "source_issue_id": source_issue_id,
                "row_key": build_clz_row_key(source_issue_id, row_index),
            }
        )
    return manifest


def apply_clz_import_visibility(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize derived CLZ import visibility counters.

    Preserves errors array for API responses and builds error categories.
    """
    normalized_result = dict(result)
    row_results = dict(normalized_result.get("row_results", {}) or {})
    total_rows = int(
        normalized_result.get("total_rows", 0)
        or len(normalized_result.get("row_manifest", []) or [])
    )
    processed = max(int(normalized_result.get("processed", 0) or 0), len(row_results))
    failed = max(
        int(normalized_result.get("failed", 0) or 0),
        sum(1 for row_result in row_results.values() if not row_result.get("resolved")),
    )

    active_row_keys = sorted(
        {
            str(row_key)
            for row_key in normalized_result.get("active_row_keys", []) or []
            if row_key
        }
        - set(row_results.keys())
    )
    active_row_count = len(active_row_keys)
    pending_row_count = max(total_rows - processed - active_row_count, 0)

    # Build errors array from row_results for API responses
    errors = []
    error_categories: dict[str, list[dict[str, Any]]] = {}

    for row_key, row_result in row_results.items():
        if "error" in row_result:
            error_entry = {
                "row": row_result.get("row_index"),
                "error": row_result.get("error"),
                "source_issue_id": row_result.get("source_issue_id"),
            }
            errors.append(error_entry)

            # Categorize errors for analysis
            error_msg = row_result.get("error", "")
            category = _categorize_error(error_msg)
            if category not in error_categories:
                error_categories[category] = []
            error_categories[category].append(error_entry)

    # Sort by row number for consistent ordering
    errors.sort(key=lambda e: e.get("row", 0))

    # Build error summary
    error_summary = [
        {
            "category": category,
            "count": len(entries),
            "sample_rows": [e["row"] for e in entries[:5]],
            "description": _get_error_description(category),
        }
        for category, entries in sorted(
            error_categories.items(), key=lambda x: -len(x[1])
        )
    ]

    normalized_result.update(
        {
            "processed": processed,
            "active_row_keys": active_row_keys,
            "active_row_count": active_row_count,
            "pending_row_count": pending_row_count,
            "failed_row_count": failed,
            "errors": errors,
            "error_summary": error_summary,
            "error_categories": list(error_categories.keys()),
        }
    )
    return normalized_result


def _categorize_error(error_msg: str) -> str:
    """Categorize error message for analysis."""
    error_lower = error_msg.lower()

    if "source series start year" in error_lower or "year" in error_lower:
        return "missing_series_year"
    if "multiple rows were found" in error_lower:
        return "duplicate_data"
    if "validation error" in error_lower:
        return "validation_error"
    if "resolution error" in error_lower:
        return "resolution_failed"
    if "network" in error_lower or "connection" in error_lower:
        return "network_error"
    if "timeout" in error_lower:
        return "timeout"

    return "other"


def _get_error_description(category: str) -> str:
    """Get human-readable description for error category."""
    descriptions = {
        "missing_series_year": "CSV rows with empty Year field - cannot determine which series year",
        "duplicate_data": "Database has duplicate issues/series - needs cleanup",
        "validation_error": "Invalid data format or required fields missing",
        "resolution_failed": "Could not match to existing canonical issue/series",
        "network_error": "Failed to fetch data from external platform",
        "timeout": "Request timed out",
        "other": "Uncategorized error",
    }
    return descriptions.get(category, "Unknown error type")


def build_clz_import_health(
    result: dict[str, Any],
    *,
    queue_depth: int | None = None,
) -> dict[str, Any]:
    """Build operational visibility metadata for a CLZ import."""
    visible_result = apply_clz_import_visibility(result)
    resume_count = int(visible_result.get("resume_count", 0) or 0)
    retry_failed_count = int(visible_result.get("retry_failed_count", 0) or 0)

    retry_mode = "fresh"
    if retry_failed_count > 0:
        retry_mode = "retry_failed_only"
    elif resume_count > 0:
        retry_mode = "resume"

    health: dict[str, Any] = {
        "active_row_count": visible_result["active_row_count"],
        "pending_row_count": visible_result["pending_row_count"],
        "failed_row_count": visible_result["failed_row_count"],
        "retry_state": {
            "mode": retry_mode,
            "resume_count": resume_count,
            "retry_failed_count": retry_failed_count,
        },
    }
    if queue_depth is not None:
        health["queue_depth"] = queue_depth
    return health


@dataclass(frozen=True)
class ClzImportFingerprint:
    """Prepared checksum identity for a CLZ import submission."""

    file_checksum: str
    file_size: int
    total_rows: int
    row_manifest: list[dict[str, Any]]
    file_name: str | None = None
    file_path: str | None = None

    def to_operation_result(self) -> dict[str, Any]:
        """Build initial operation state for a CLZ import."""
        summary = (
            f"Prepared {self.total_rows} CLZ rows for processing"
            if self.total_rows
            else "Prepared empty CLZ import"
        )
        return apply_clz_import_visibility(
            {
                "file_checksum": self.file_checksum,
                "file_size": self.file_size,
                "file_name": self.file_name,
                "file_path": self.file_path,
                "total_rows": self.total_rows,
                "row_manifest": self.row_manifest,
                "row_results": {},
                "processed": 0,
                "resolved": 0,
                "failed": 0,
                "errors": [],
                "progress": 0.0,
                "resume_count": 0,
                "retry_failed_count": 0,
                "summary": summary,
            }
        )


def prepare_clz_import_from_bytes(
    content: bytes,
    *,
    file_name: str | None = None,
    file_path: str | None = None,
) -> ClzImportFingerprint:
    """Build checksum and row-manifest metadata from CLZ CSV bytes."""
    adapter = CLZAdapter()
    try:
        decoded_content = content.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValidationError(f"CSV file encoding error: {e}") from e
    rows = adapter.load_csv_from_string(decoded_content)
    return ClzImportFingerprint(
        file_checksum=hashlib.sha256(content).hexdigest(),
        file_size=len(content),
        total_rows=len(rows),
        row_manifest=build_clz_row_manifest(rows),
        file_name=file_name,
        file_path=file_path,
    )


def prepare_clz_import_from_path(file_path: str | Path) -> ClzImportFingerprint:
    """Build checksum and row-manifest metadata from a CLZ CSV path."""
    resolved_path = Path(file_path)
    try:
        content = resolved_path.read_bytes()
    except OSError as e:
        raise ValidationError(f"CSV file not found: {file_path}") from e
    return prepare_clz_import_from_bytes(
        content,
        file_name=resolved_path.name,
        file_path=str(resolved_path),
    )
