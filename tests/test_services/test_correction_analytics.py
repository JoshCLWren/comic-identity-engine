"""Tests for correction analytics service."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from comic_identity_engine.database.models import (
    ExternalMapping,
    Issue,
    MappingCorrection,
    SeriesRun,
)
from comic_identity_engine.services.correction_analytics import (
    CorrectionAnalyticsService,
    CorrectionStats,
    CorrectionPattern,
    PlatformAccuracy,
)


@pytest.fixture
async def sample_data(db_session: AsyncSession):
    import uuid as uuid_module

    unique_suffix = str(uuid_module.uuid4())[:8]
    series = SeriesRun(
        title=f"X-Men-{unique_suffix}",
        start_year=1991,
        publisher="Marvel",
    )
    db_session.add(series)
    await db_session.flush()

    issue1 = Issue(
        series_run_id=series.id,
        issue_number="1",
    )
    issue2 = Issue(
        series_run_id=series.id,
        issue_number="2",
    )
    db_session.add_all([issue1, issue2])
    await db_session.flush()

    mapping1 = ExternalMapping(
        issue_id=issue1.id,
        source="gcd",
        source_issue_id=f"12345-{unique_suffix}",
        is_accurate=True,
    )
    mapping2 = ExternalMapping(
        issue_id=issue2.id,
        source="gcd",
        source_issue_id=f"12346-{unique_suffix}",
        is_accurate=False,
    )
    mapping3 = ExternalMapping(
        issue_id=issue1.id,
        source="locg",
        source_issue_id=f"67890-{unique_suffix}",
        is_accurate=True,
    )
    db_session.add_all([mapping1, mapping2, mapping3])
    await db_session.flush()

    correction1 = MappingCorrection(
        issue_id=issue1.id,
        source="gcd",
        original_source_issue_id=f"12344-{unique_suffix}",
        correct_source_issue_id=f"12345-{unique_suffix}",
        correction_type="wrong_issue",
        review_status="applied",
    )
    correction2 = MappingCorrection(
        issue_id=issue2.id,
        source="gcd",
        original_source_issue_id=f"12347-{unique_suffix}",
        correct_source_issue_id=f"12346-{unique_suffix}",
        correction_type="wrong_issue",
        review_status="pending",
    )
    correction3 = MappingCorrection(
        issue_id=issue1.id,
        source="locg",
        original_source_issue_id=f"67891-{unique_suffix}",
        correct_source_issue_id=None,
        correction_type="wrong_series",
        review_status="reviewed",
    )
    db_session.add_all([correction1, correction2, correction3])
    await db_session.flush()

    return {
        "series": series,
        "issue1": issue1,
        "issue2": issue2,
        "mapping1": mapping1,
        "mapping2": mapping2,
        "mapping3": mapping3,
        "correction1": correction1,
        "correction2": correction2,
        "correction3": correction3,
    }


@pytest.mark.asyncio
async def test_get_correction_stats(db_session: AsyncSession, sample_data):
    analytics = CorrectionAnalyticsService(db_session)
    stats = await analytics.get_correction_stats()

    assert isinstance(stats, CorrectionStats)
    assert stats.total_corrections == 3
    assert stats.pending_review == 1
    assert stats.reviewed == 1
    assert stats.applied == 1
    assert stats.by_platform.get("gcd") == 2
    assert stats.by_platform.get("locg") == 1
    assert stats.by_correction_type.get("wrong_issue") == 2
    assert stats.by_correction_type.get("wrong_series") == 1


@pytest.mark.asyncio
async def test_get_platform_accuracy(db_session: AsyncSession, sample_data):
    analytics = CorrectionAnalyticsService(db_session)
    accuracies = await analytics.get_platform_accuracy(platform="gcd")

    assert len(accuracies) == 1
    gcd_accuracy = accuracies[0]

    assert isinstance(gcd_accuracy, PlatformAccuracy)
    assert gcd_accuracy.platform == "gcd"
    assert gcd_accuracy.total_mappings == 2
    assert gcd_accuracy.accurate_mappings == 1
    assert gcd_accuracy.inaccurate_mappings == 1
    assert gcd_accuracy.corrected_mappings == 2


@pytest.mark.asyncio
async def test_get_platform_accuracy_all_platforms(
    db_session: AsyncSession, sample_data
):
    analytics = CorrectionAnalyticsService(db_session)
    accuracies = await analytics.get_platform_accuracy()

    assert len(accuracies) == 7

    gcd_accuracy = next(a for a in accuracies if a.platform == "gcd")
    assert gcd_accuracy.total_mappings == 2

    locg_accuracy = next(a for a in accuracies if a.platform == "locg")
    assert locg_accuracy.total_mappings == 1


@pytest.mark.asyncio
async def test_identify_patterns(db_session: AsyncSession, sample_data):
    analytics = CorrectionAnalyticsService(db_session)
    patterns = await analytics.identify_patterns()

    assert len(patterns) > 0
    assert all(isinstance(p, CorrectionPattern) for p in patterns)

    platform_issue_pattern = next(
        (p for p in patterns if p.pattern_type == "platform_issue"), None
    )
    assert platform_issue_pattern is not None
    assert platform_issue_pattern.count > 0


@pytest.mark.asyncio
async def test_get_recent_corrections(db_session: AsyncSession, sample_data):
    analytics = CorrectionAnalyticsService(db_session)

    corrections = await analytics.get_recent_corrections(limit=10)
    assert len(corrections) == 3

    corrections = await analytics.get_recent_corrections(
        limit=10, review_status="pending"
    )
    assert len(corrections) == 1
    assert corrections[0].review_status == "pending"

    corrections = await analytics.get_recent_corrections(limit=10, platform="gcd")
    assert len(corrections) == 2


@pytest.mark.asyncio
async def test_update_review_status(db_session: AsyncSession, sample_data):
    analytics = CorrectionAnalyticsService(db_session)
    correction_id = sample_data["correction2"].id

    updated = await analytics.update_review_status(
        correction_id=correction_id,
        status="reviewed",
        reviewed_by="test_user",
        review_notes="Verified correction",
    )

    assert updated.review_status == "reviewed"
    assert updated.reviewed_by == "test_user"
    assert updated.reviewed_at is not None
    assert updated.review_notes == "Verified correction"


@pytest.mark.asyncio
async def test_update_review_status_invalid_correction(db_session: AsyncSession):
    analytics = CorrectionAnalyticsService(db_session)

    with pytest.raises(ValueError, match="not found"):
        await analytics.update_review_status(
            correction_id=uuid.uuid4(),
            status="reviewed",
        )


@pytest.mark.asyncio
async def test_update_review_status_invalid_status(
    db_session: AsyncSession, sample_data
):
    analytics = CorrectionAnalyticsService(db_session)
    correction_id = sample_data["correction2"].id

    with pytest.raises(ValueError, match="Invalid status"):
        await analytics.update_review_status(
            correction_id=correction_id,
            status="invalid_status",
        )


@pytest.mark.asyncio
async def test_get_correction_seed_data(db_session: AsyncSession, sample_data):
    analytics = CorrectionAnalyticsService(db_session)
    seed_data = await analytics.get_correction_seed_data()

    assert len(seed_data) == 1
    assert seed_data[0]["platform"] == "gcd"
    assert (
        seed_data[0]["correct_platform_id"] == sample_data["mapping1"].source_issue_id
    )
    assert (
        seed_data[0]["original_platform_id"]
        == sample_data["correction1"].original_source_issue_id
    )
    assert seed_data[0]["correction_type"] == "wrong_issue"


@pytest.mark.asyncio
async def test_get_correction_seed_data_by_platform(
    db_session: AsyncSession, sample_data
):
    analytics = CorrectionAnalyticsService(db_session)
    seed_data = await analytics.get_correction_seed_data(platform="locg")

    assert len(seed_data) == 0

    seed_data = await analytics.get_correction_seed_data(platform="gcd")
    assert len(seed_data) == 1
