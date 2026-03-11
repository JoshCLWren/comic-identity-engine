"""Tests for correction analytics API endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from comic_identity_engine.database.models import (
    ExternalMapping,
    Issue,
    MappingCorrection,
    SeriesRun,
)


@pytest.fixture
async def setup_corrections(db_session: AsyncSession):
    series = SeriesRun(
        title="Amazing Spider-Man",
        start_year=1963,
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
        source_issue_id="10001",
        is_accurate=True,
    )
    mapping2 = ExternalMapping(
        issue_id=issue2.id,
        source="gcd",
        source_issue_id="10002",
        is_accurate=False,
    )
    db_session.add_all([mapping1, mapping2])
    await db_session.flush()

    correction1 = MappingCorrection(
        issue_id=issue1.id,
        source="gcd",
        original_source_issue_id="10000",
        correct_source_issue_id="10001",
        correction_type="wrong_issue",
        review_status="applied",
        user_notes="Corrected issue number",
    )
    correction2 = MappingCorrection(
        issue_id=issue2.id,
        source="gcd",
        original_source_issue_id="10003",
        correct_source_issue_id=None,
        correction_type="wrong_series",
        review_status="pending",
        user_notes="Wrong series",
    )
    db_session.add_all([correction1, correction2])
    await db_session.commit()

    return {
        "series": series,
        "issue1": issue1,
        "issue2": issue2,
        "correction1": correction1,
        "correction2": correction2,
    }


@pytest.mark.asyncio
async def test_get_correction_stats(client: AsyncClient, setup_corrections):
    response = await client.get("/api/v1/corrections/stats")

    assert response.status_code == 200
    data = response.json()

    assert data["total_corrections"] == 2
    assert data["pending_review"] == 1
    assert data["applied"] == 1
    assert "by_platform" in data
    assert "by_correction_type" in data


@pytest.mark.asyncio
async def test_get_platform_accuracy(client: AsyncClient, setup_corrections):
    response = await client.get("/api/v1/corrections/platform-accuracy")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 7

    gcd_data = next(p for p in data if p["platform"] == "gcd")
    assert gcd_data["total_mappings"] == 2
    assert gcd_data["accurate_mappings"] == 1
    assert gcd_data["inaccurate_mappings"] == 1


@pytest.mark.asyncio
async def test_get_platform_accuracy_filtered(client: AsyncClient, setup_corrections):
    response = await client.get("/api/v1/corrections/platform-accuracy?platform=gcd")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["platform"] == "gcd"


@pytest.mark.asyncio
async def test_get_correction_patterns(client: AsyncClient, setup_corrections):
    response = await client.get("/api/v1/corrections/patterns")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) > 0

    pattern = data[0]
    assert "pattern_type" in pattern
    assert "description" in pattern
    assert "count" in pattern


@pytest.mark.asyncio
async def test_list_corrections(client: AsyncClient, setup_corrections):
    response = await client.get("/api/v1/corrections/list")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2

    correction = data[0]
    assert "id" in correction
    assert "series_title" in correction
    assert "issue_number" in correction
    assert "source" in correction
    assert "review_status" in correction


@pytest.mark.asyncio
async def test_list_corrections_filtered_by_status(
    client: AsyncClient, setup_corrections
):
    response = await client.get("/api/v1/corrections/list?review_status=pending")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["review_status"] == "pending"


@pytest.mark.asyncio
async def test_list_corrections_filtered_by_platform(
    client: AsyncClient, setup_corrections
):
    response = await client.get("/api/v1/corrections/list?platform=gcd")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2
    assert all(c["source"] == "gcd" for c in data)


@pytest.mark.asyncio
async def test_update_review_status(client: AsyncClient, setup_corrections):
    correction_id = setup_corrections["correction2"].id

    response = await client.patch(
        f"/api/v1/corrections/{correction_id}/review",
        json={
            "status": "reviewed",
            "review_notes": "Verified and reviewed",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(correction_id)
    assert data["source"] == "gcd"


@pytest.mark.asyncio
async def test_update_review_status_invalid_id(client: AsyncClient):
    response = await client.patch(
        f"/api/v1/corrections/{uuid.uuid4()}/review",
        json={
            "status": "reviewed",
            "review_notes": "Test",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_review_status_invalid_status(
    client: AsyncClient, setup_corrections
):
    correction_id = setup_corrections["correction2"].id

    response = await client.patch(
        f"/api/v1/corrections/{correction_id}/review",
        json={
            "status": "invalid_status",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_seed_data(client: AsyncClient, setup_corrections):
    response = await client.get("/api/v1/corrections/seed-data")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) == 1

    seed = data[0]
    assert seed["platform"] == "gcd"
    assert seed["correct_platform_id"] == "10001"
    assert seed["original_platform_id"] == "10000"


@pytest.mark.asyncio
async def test_get_seed_data_filtered(client: AsyncClient, setup_corrections):
    response = await client.get("/api/v1/corrections/seed-data?platform=locg")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 0
