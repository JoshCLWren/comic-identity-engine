"""Correction router for mapping corrections.

Provides endpoints for marking mappings as incorrect and providing corrections.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from comic_identity_engine.api.schemas import (
    CorrectionHistoryItem,
    CorrectionHistoryResponse,
    CorrectionResponse,
    MarkIncorrectRequest,
    ProvideCorrectRequest,
)
from comic_identity_engine.database.connection import get_db
from comic_identity_engine.database.models import (
    ExternalMapping,
    Issue,
    MappingCorrection,
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
