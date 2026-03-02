"""SQLAlchemy ORM models for Comic Identity Engine.

SOURCE: Canonical entity model for comic books
USAGE:
- SeriesRun: Canonical series with unique identity
- Issue: Canonical issues with variant support
- Variant: Variant suffixes for issues
- ExternalMapping: Cross-platform ID mappings
- Operation: AIP-151 async operations tracking

USED BY:
- Repository layer for data access
- Alembic migrations for schema management
- API responses and queries
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from comic_identity_engine.database.connection import Base


class SeriesRun(Base):
    """Canonical series representation.

    A SeriesRun represents a unique comic book series with a specific
    start year. Multiple volumes of the same title are represented
    as separate SeriesRun entities.
    """

    __tablename__ = "series_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    start_year: Mapped[int] = mapped_column(nullable=False, index=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    issues: Mapped[list["Issue"]] = relationship(
        "Issue",
        back_populates="series_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __str__(self) -> str:
        return f"{self.title} ({self.start_year})"

    def __repr__(self) -> str:
        return f"<SeriesRun(id={self.id}, title='{self.title}', start_year={self.start_year})>"


class Issue(Base):
    """Canonical issue representation.

    An Issue represents a unique comic book issue within a SeriesRun.
    The base issue has no variant suffix - variants are represented
    as separate Variant entities.
    """

    __tablename__ = "issues"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    series_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("series_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issue_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    cover_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    upc: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        unique=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    series_run: Mapped["SeriesRun"] = relationship(
        "SeriesRun",
        back_populates="issues",
        lazy="selectin",
    )
    variants: Mapped[list["Variant"]] = relationship(
        "Variant",
        back_populates="issue",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    external_mappings: Mapped[list["ExternalMapping"]] = relationship(
        "ExternalMapping",
        back_populates="issue",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __str__(self) -> str:
        if self.series_run is None:
            return f"Issue #{self.issue_number}"
        return f"{self.series_run.title} #{self.issue_number}"

    def __repr__(self) -> str:
        return (
            f"<Issue(id={self.id}, issue_number='{self.issue_number}', "
            f"series_run_id={self.series_run_id})>"
        )


class Variant(Base):
    """Variant representation for issues.

    A Variant represents a specific cover or edition variant of an issue.
    Each variant has a unique suffix code (e.g., "A", "B", "NS" for newsstand).
    """

    __tablename__ = "variants"
    __table_args__ = (
        UniqueConstraint(
            "issue_id", "variant_suffix", name="uq_variants_issue_id_variant_suffix"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    variant_suffix: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    variant_name: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    issue: Mapped["Issue"] = relationship(
        "Issue",
        back_populates="variants",
        lazy="selectin",
    )

    def __str__(self) -> str:
        if self.issue is None:
            return f"Variant .{self.variant_suffix}"
        return f"{self.issue}.{self.variant_suffix}"

    def __repr__(self) -> str:
        return (
            f"<Variant(id={self.id}, variant_suffix='{self.variant_suffix}', "
            f"issue_id={self.issue_id})>"
        )


class ExternalMapping(Base):
    """External platform ID mapping.

    An ExternalMapping stores the relationship between a canonical Issue
    and its representation on external platforms (GCD, LoCG, CCL, etc.).
    """

    __tablename__ = "external_mappings"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "source_issue_id",
            name="uq_external_mappings_source_source_issue_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    source_series_id: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    source_issue_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    issue: Mapped["Issue"] = relationship(
        "Issue",
        back_populates="external_mappings",
        lazy="selectin",
    )

    def __str__(self) -> str:
        return f"{self.source}:{self.source_issue_id}"

    def __repr__(self) -> str:
        return (
            f"<ExternalMapping(id={self.id}, source='{self.source}', "
            f"source_issue_id='{self.source_issue_id}', issue_id={self.issue_id})>"
        )


class Operation(Base):
    """Async operation tracking for AIP-151 compliance.

    An Operation represents a long-running async operation (import, export,
    reconciliation, etc.) with status tracking and result storage.
    """

    __tablename__ = "operations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    operation_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    input_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    result: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __str__(self) -> str:
        return f"{self.operation_type}:{self.status}"

    def __repr__(self) -> str:
        return (
            f"<Operation(id={self.id}, operation_type='{self.operation_type}', "
            f"status='{self.status}')>"
        )
