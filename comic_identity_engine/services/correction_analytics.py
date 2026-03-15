"""Correction analytics service for algorithm improvement.

Analyzes mapping corrections to identify patterns and improve matching algorithms.
"""

import structlog
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from comic_identity_engine.database.models import (
    ExternalMapping,
    Issue,
    MappingCorrection,
)

logger = structlog.get_logger(__name__)


@dataclass
class CorrectionStats:
    """Statistics about corrections."""

    total_corrections: int = 0
    pending_review: int = 0
    reviewed: int = 0
    applied: int = 0
    rejected: int = 0
    by_platform: dict[str, int] = field(default_factory=dict)
    by_correction_type: dict[str, int] = field(default_factory=dict)
    by_review_status: dict[str, int] = field(default_factory=dict)


@dataclass
class CorrectionPattern:
    """Identified pattern from corrections."""

    pattern_type: str
    description: str
    count: int
    examples: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PlatformAccuracy:
    """Accuracy metrics for a platform."""

    platform: str
    total_mappings: int
    accurate_mappings: int
    inaccurate_mappings: int
    corrected_mappings: int
    accuracy_rate: float
    correction_rate: float


class CorrectionAnalyticsService:
    """Service for analyzing corrections and improving algorithms."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_correction_stats(self) -> CorrectionStats:
        """Get overall correction statistics."""
        total_result = await self.session.execute(
            select(func.count(MappingCorrection.id))
        )
        total = total_result.scalar() or 0

        pending_result = await self.session.execute(
            select(func.count(MappingCorrection.id)).where(
                MappingCorrection.review_status == "pending"
            )
        )
        pending = pending_result.scalar() or 0

        reviewed_result = await self.session.execute(
            select(func.count(MappingCorrection.id)).where(
                MappingCorrection.review_status == "reviewed"
            )
        )
        reviewed = reviewed_result.scalar() or 0

        applied_result = await self.session.execute(
            select(func.count(MappingCorrection.id)).where(
                MappingCorrection.review_status == "applied"
            )
        )
        applied = applied_result.scalar() or 0

        rejected_result = await self.session.execute(
            select(func.count(MappingCorrection.id)).where(
                MappingCorrection.review_status == "rejected"
            )
        )
        rejected = rejected_result.scalar() or 0

        by_platform_result = await self.session.execute(
            select(
                MappingCorrection.source,
                func.count(MappingCorrection.id),
            ).group_by(MappingCorrection.source)
        )
        by_platform = dict(by_platform_result.all())

        by_type_result = await self.session.execute(
            select(
                MappingCorrection.correction_type,
                func.count(MappingCorrection.id),
            ).group_by(MappingCorrection.correction_type)
        )
        by_type = dict(by_type_result.all())

        by_status_result = await self.session.execute(
            select(
                MappingCorrection.review_status,
                func.count(MappingCorrection.id),
            ).group_by(MappingCorrection.review_status)
        )
        by_status = dict(by_status_result.all())

        return CorrectionStats(
            total_corrections=total,
            pending_review=pending,
            reviewed=reviewed,
            applied=applied,
            rejected=rejected,
            by_platform=by_platform,
            by_correction_type=by_type,
            by_review_status=by_status,
        )

    async def get_platform_accuracy(
        self, platform: Optional[str] = None
    ) -> list[PlatformAccuracy]:
        """Get accuracy metrics for platforms."""
        platforms_to_check = (
            [platform]
            if platform
            else ["gcd", "locg", "ccl", "aa", "cpg", "hip", "clz"]
        )

        results = []
        for plat in platforms_to_check:
            total_result = await self.session.execute(
                select(func.count(ExternalMapping.id)).where(
                    ExternalMapping.source == plat
                )
            )
            total = total_result.scalar() or 0

            accurate_result = await self.session.execute(
                select(func.count(ExternalMapping.id)).where(
                    and_(
                        ExternalMapping.source == plat,
                        ExternalMapping.is_accurate == True,
                    )
                )
            )
            accurate = accurate_result.scalar() or 0

            inaccurate_result = await self.session.execute(
                select(func.count(ExternalMapping.id)).where(
                    and_(
                        ExternalMapping.source == plat,
                        ExternalMapping.is_accurate == False,
                    )
                )
            )
            inaccurate = inaccurate_result.scalar() or 0

            corrected_result = await self.session.execute(
                select(func.count(MappingCorrection.id)).where(
                    and_(
                        MappingCorrection.source == plat,
                        MappingCorrection.correct_source_issue_id.isnot(None),
                    )
                )
            )
            corrected = corrected_result.scalar() or 0

            accuracy_rate = (accurate / total * 100) if total > 0 else 0.0
            correction_rate = (corrected / total * 100) if total > 0 else 0.0

            results.append(
                PlatformAccuracy(
                    platform=plat,
                    total_mappings=total,
                    accurate_mappings=accurate,
                    inaccurate_mappings=inaccurate,
                    corrected_mappings=corrected,
                    accuracy_rate=round(accuracy_rate, 2),
                    correction_rate=round(correction_rate, 2),
                )
            )

        return results

    async def identify_patterns(self) -> list[CorrectionPattern]:
        """Identify patterns from corrections."""
        patterns = []

        wrong_series_corrections = await self.session.execute(
            select(MappingCorrection)
            .where(MappingCorrection.correction_type == "wrong_series")
            .options(selectinload(MappingCorrection.issue))
            .limit(100)
        )
        wrong_series = wrong_series_corrections.scalars().all()

        if wrong_series:
            series_confusion = defaultdict(list)
            for correction in wrong_series:
                if correction.issue:
                    series_title = correction.issue.series_run.title
                    series_confusion[series_title].append(
                        {
                            "original_id": correction.original_source_issue_id,
                            "correct_id": correction.correct_source_issue_id,
                            "platform": correction.source,
                            "notes": correction.user_notes,
                        }
                    )

            for series_title, examples in sorted(
                series_confusion.items(), key=lambda x: len(x[1]), reverse=True
            )[:5]:
                patterns.append(
                    CorrectionPattern(
                        pattern_type="series_confusion",
                        description=f"Series '{series_title}' frequently has wrong mappings",
                        count=len(examples),
                        examples=examples[:3],
                    )
                )

        wrong_issue_corrections = await self.session.execute(
            select(MappingCorrection)
            .where(MappingCorrection.correction_type == "wrong_issue")
            .options(selectinload(MappingCorrection.issue))
            .limit(100)
        )
        wrong_issues = wrong_issue_corrections.scalars().all()

        if wrong_issues:
            issue_number_issues = defaultdict(list)
            for correction in wrong_issues:
                if correction.issue:
                    issue_num = correction.issue.issue_number
                    issue_number_issues[issue_num].append(
                        {
                            "original_id": correction.original_source_issue_id,
                            "correct_id": correction.correct_source_issue_id,
                            "platform": correction.source,
                            "series": correction.issue.series_run.title,
                        }
                    )

            for issue_num, examples in sorted(
                issue_number_issues.items(), key=lambda x: len(x[1]), reverse=True
            )[:5]:
                patterns.append(
                    CorrectionPattern(
                        pattern_type="issue_number_confusion",
                        description=f"Issue #{issue_num} frequently has wrong mappings",
                        count=len(examples),
                        examples=examples[:3],
                    )
                )

        platform_issues = await self.session.execute(
            select(
                MappingCorrection.source,
                MappingCorrection.correction_type,
                func.count(MappingCorrection.id).label("count"),
            )
            .group_by(MappingCorrection.source, MappingCorrection.correction_type)
            .order_by(func.count(MappingCorrection.id).desc())
        )

        platform_issue_list = platform_issues.all()
        for source, correction_type, count in platform_issue_list[:5]:
            patterns.append(
                CorrectionPattern(
                    pattern_type="platform_issue",
                    description=f"Platform {source.upper()} has {count} {correction_type} corrections",
                    count=count,
                    examples=[],
                )
            )

        return patterns

    async def get_recent_corrections(
        self,
        limit: int = 50,
        review_status: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> list[MappingCorrection]:
        """Get recent corrections with optional filters."""
        query = (
            select(MappingCorrection)
            .options(
                selectinload(MappingCorrection.issue).selectinload(Issue.series_run)
            )
            .order_by(MappingCorrection.created_at.desc())
        )

        if review_status:
            query = query.where(MappingCorrection.review_status == review_status)

        if platform:
            query = query.where(MappingCorrection.source == platform)

        query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_review_status(
        self,
        correction_id: UUID,
        status: str,
        reviewed_by: Optional[str] = None,
        review_notes: Optional[str] = None,
    ) -> MappingCorrection:
        """Update the review status of a correction."""
        result = await self.session.execute(
            select(MappingCorrection).where(MappingCorrection.id == correction_id)
        )
        correction = result.scalar_one_or_none()

        if not correction:
            raise ValueError(f"Correction {correction_id} not found")

        valid_statuses = ["pending", "reviewed", "applied", "rejected"]
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid status: {status}. Must be one of {valid_statuses}"
            )

        correction.review_status = status
        correction.reviewed_by = reviewed_by
        correction.reviewed_at = datetime.utcnow()
        correction.review_notes = review_notes

        await self.session.commit()
        await self.session.refresh(correction)

        logger.info(
            "Updated correction review status",
            correction_id=str(correction_id),
            status=status,
            reviewed_by=reviewed_by,
        )

        return correction

    async def get_correction_seed_data(
        self, platform: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Extract verified correct mappings as seed data for algorithms."""
        query = (
            select(MappingCorrection)
            .where(
                and_(
                    MappingCorrection.review_status == "applied",
                    MappingCorrection.correct_source_issue_id.isnot(None),
                )
            )
            .options(
                selectinload(MappingCorrection.issue).selectinload(Issue.series_run)
            )
        )

        if platform:
            query = query.where(MappingCorrection.source == platform)

        result = await self.session.execute(query)
        corrections = result.scalars().all()

        seed_data = []
        for correction in corrections:
            if correction.issue:
                seed_data.append(
                    {
                        "canonical_issue_id": str(correction.issue.id),
                        "series_title": correction.issue.series_run.title,
                        "series_year": correction.issue.series_run.start_year,
                        "issue_number": correction.issue.issue_number,
                        "platform": correction.source,
                        "correct_platform_id": correction.correct_source_issue_id,
                        "original_platform_id": correction.original_source_issue_id,
                        "correction_type": correction.correction_type,
                    }
                )

        return seed_data
