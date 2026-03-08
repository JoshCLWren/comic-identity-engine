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
        return {
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
            "summary": summary,
        }


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
