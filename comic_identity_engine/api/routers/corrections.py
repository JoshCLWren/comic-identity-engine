"""Correction router for mapping corrections.

Provides endpoints for marking mappings as incorrect and providing corrections.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from comic_identity_engine.api.schemas import (
    CorrectionHistoryItem,
    CorrectionHistoryResponse,
    CorrectionListItem,
    CorrectionPatternResponse,
    CorrectionResponse,
    CorrectionStatsResponse,
    MarkIncorrectRequest,
    PlatformAccuracyResponse,
    ProvideCorrectRequest,
    UpdateReviewStatusRequest,
)
from comic_identity_engine.database.connection import get_db
from comic_identity_engine.database.models import (
    ExternalMapping,
    Issue,
    MappingCorrection,
)
from comic_identity_engine.services.correction_analytics import (
    CorrectionAnalyticsService,
)

router = APIRouter(prefix="/corrections", tags=["Corrections"])


@router.post("/mark-incorrect", response_model=CorrectionResponse)
async def mark_mapping_incorrect(
    request: MarkIncorrectRequest,
    db: AsyncSession = Depends(get_db),
) -> CorrectionResponse:
    """Mark a mapping as incorrect.

    This:
    1. Creates a MappingCorrection record
    2. Sets is_accurate=False on the ExternalMapping
    """
    mapping_query = select(ExternalMapping).where(
        ExternalMapping.issue_id == request.issue_id,
        ExternalMapping.source == request.source,
        ExternalMapping.source_issue_id == request.source_issue_id,
    )
    result = await db.execute(mapping_query)
    mapping = result.scalar_one_or_none()

    if not mapping:
        raise HTTPException(
            status_code=404,
            detail=f"Mapping not found: {request.source}:{request.source_issue_id}",
        )

    mapping.is_accurate = False

    correction = MappingCorrection(
        issue_id=request.issue_id,
        source=request.source,
        original_source_issue_id=request.source_issue_id,
        correction_type=request.correction_type,
        user_notes=request.notes,
    )
    db.add(correction)
    await db.commit()
    await db.refresh(correction)

    return CorrectionResponse(
        id=correction.id,
        issue_id=correction.issue_id,
        source=correction.source,
        correction_type=correction.correction_type,
        created_at=correction.created_at,
    )


@router.post("/provide-correct", response_model=CorrectionResponse)
async def provide_correct_mapping(
    request: ProvideCorrectRequest,
    db: AsyncSession = Depends(get_db),
) -> CorrectionResponse:
    """Provide the correct mapping ID for a previously marked incorrect mapping.

    This:
    1. Creates a MappingCorrection record with the correct ID
    2. Updates the ExternalMapping with the correct source_issue_id
    3. Sets is_accurate=True on the ExternalMapping
    """
    mapping_query = select(ExternalMapping).where(
        ExternalMapping.issue_id == request.issue_id,
        ExternalMapping.source == request.source,
        ExternalMapping.source_issue_id == request.incorrect_source_issue_id,
    )
    result = await db.execute(mapping_query)
    mapping = result.scalar_one_or_none()

    if not mapping:
        raise HTTPException(
            status_code=404,
            detail=f"Mapping not found: {request.source}:{request.incorrect_source_issue_id}",
        )

    existing_correct = await db.execute(
        select(ExternalMapping).where(
            ExternalMapping.source == request.source,
            ExternalMapping.source_issue_id == request.correct_source_issue_id,
        )
    )
    if existing_correct.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Correct mapping already exists: {request.source}:{request.correct_source_issue_id}",
        )

    mapping.source_issue_id = request.correct_source_issue_id
    mapping.is_accurate = True

    correction = MappingCorrection(
        issue_id=request.issue_id,
        source=request.source,
        original_source_issue_id=request.incorrect_source_issue_id,
        correct_source_issue_id=request.correct_source_issue_id,
        correction_type="corrected",
        user_notes=request.notes,
    )
    db.add(correction)
    await db.commit()
    await db.refresh(correction)

    return CorrectionResponse(
        id=correction.id,
        issue_id=correction.issue_id,
        source=correction.source,
        correction_type=correction.correction_type,
        created_at=correction.created_at,
    )


@router.get("/history/{issue_id}", response_model=CorrectionHistoryResponse)
async def get_correction_history(
    issue_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CorrectionHistoryResponse:
    """Get correction history for an issue."""
    issue_result = await db.execute(select(Issue).where(Issue.id == issue_id))
    if not issue_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Issue not found")

    corrections_result = await db.execute(
        select(MappingCorrection)
        .where(MappingCorrection.issue_id == issue_id)
        .order_by(MappingCorrection.created_at.desc())
    )
    corrections = corrections_result.scalars().all()

    return CorrectionHistoryResponse(
        issue_id=issue_id,
        corrections=[
            CorrectionHistoryItem(
                id=c.id,
                source=c.source,
                original_source_issue_id=c.original_source_issue_id,
                correct_source_issue_id=c.correct_source_issue_id,
                correction_type=c.correction_type,
                user_notes=c.user_notes,
                created_at=c.created_at,
            )
            for c in corrections
        ],
    )


@router.get("/stats", response_model=CorrectionStatsResponse)
async def get_correction_stats(
    db: AsyncSession = Depends(get_db),
) -> CorrectionStatsResponse:
    """Get overall correction statistics."""
    analytics = CorrectionAnalyticsService(db)
    stats = await analytics.get_correction_stats()

    return CorrectionStatsResponse(
        total_corrections=stats.total_corrections,
        pending_review=stats.pending_review,
        reviewed=stats.reviewed,
        applied=stats.applied,
        rejected=stats.rejected,
        by_platform=stats.by_platform,
        by_correction_type=stats.by_correction_type,
        by_review_status=stats.by_review_status,
    )


@router.get("/platform-accuracy", response_model=list[PlatformAccuracyResponse])
async def get_platform_accuracy(
    platform: Optional[str] = Query(None, description="Filter to specific platform"),
    db: AsyncSession = Depends(get_db),
) -> list[PlatformAccuracyResponse]:
    """Get accuracy metrics for platforms."""
    analytics = CorrectionAnalyticsService(db)
    accuracies = await analytics.get_platform_accuracy(platform)

    return [
        PlatformAccuracyResponse(
            platform=acc.platform,
            total_mappings=acc.total_mappings,
            accurate_mappings=acc.accurate_mappings,
            inaccurate_mappings=acc.inaccurate_mappings,
            corrected_mappings=acc.corrected_mappings,
            accuracy_rate=acc.accuracy_rate,
            correction_rate=acc.correction_rate,
        )
        for acc in accuracies
    ]


@router.get("/patterns", response_model=list[CorrectionPatternResponse])
async def get_correction_patterns(
    db: AsyncSession = Depends(get_db),
) -> list[CorrectionPatternResponse]:
    """Identify patterns from corrections for algorithm improvement."""
    analytics = CorrectionAnalyticsService(db)
    patterns = await analytics.identify_patterns()

    return [
        CorrectionPatternResponse(
            pattern_type=p.pattern_type,
            description=p.description,
            count=p.count,
            examples=p.examples,
        )
        for p in patterns
    ]


@router.get("/list", response_model=list[CorrectionListItem])
async def list_corrections(
    limit: int = Query(50, ge=1, le=500),
    review_status: Optional[str] = Query(None, description="Filter by review status"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    db: AsyncSession = Depends(get_db),
) -> list[CorrectionListItem]:
    """Get recent corrections with optional filters."""
    analytics = CorrectionAnalyticsService(db)
    corrections = await analytics.get_recent_corrections(
        limit=limit,
        review_status=review_status,
        platform=platform,
    )

    return [
        CorrectionListItem(
            id=c.id,
            issue_id=c.issue_id,
            series_title=c.issue.series_run.title if c.issue else "Unknown",
            issue_number=c.issue.issue_number if c.issue else "?",
            source=c.source,
            original_source_issue_id=c.original_source_issue_id,
            correct_source_issue_id=c.correct_source_issue_id,
            correction_type=c.correction_type,
            review_status=c.review_status,
            created_at=c.created_at,
        )
        for c in corrections
    ]


@router.patch("/{correction_id}/review", response_model=CorrectionResponse)
async def update_review_status(
    correction_id: UUID,
    request: UpdateReviewStatusRequest,
    db: AsyncSession = Depends(get_db),
) -> CorrectionResponse:
    """Update the review status of a correction."""
    analytics = CorrectionAnalyticsService(db)

    try:
        correction = await analytics.update_review_status(
            correction_id=correction_id,
            status=request.status,
            review_notes=request.review_notes,
        )

        return CorrectionResponse(
            id=correction.id,
            issue_id=correction.issue_id,
            source=correction.source,
            correction_type=correction.correction_type,
            created_at=correction.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/seed-data")
async def get_seed_data(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get verified correct mappings as seed data for algorithms."""
    analytics = CorrectionAnalyticsService(db)
    seed_data = await analytics.get_correction_seed_data(platform=platform)
    return seed_data
