"""Tests for platform searcher session isolation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from comic_identity_engine.errors import DuplicateEntityError
from comic_identity_engine.services.platform_searcher import PlatformSearcher


TEST_ISSUE_ID = UUID("550e8400-e29b-41d4-a716-446655440001")
TEST_OPERATION_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def searcher():
    """Create a PlatformSearcher instance without running scraper setup."""
    instance = PlatformSearcher.__new__(PlatformSearcher)
    instance.session = MagicMock()
    instance._progress_lock = asyncio.Lock()
    instance.scrapers = {}
    return instance


@pytest.fixture
def mock_async_session_local():
    """Mock AsyncSessionLocal context manager."""
    session = AsyncMock()
    with patch(
        "comic_identity_engine.services.platform_searcher.AsyncSessionLocal"
    ) as mock:
        mock.return_value.__aenter__ = AsyncMock(return_value=session)
        mock.return_value.__aexit__ = AsyncMock(return_value=False)
        yield session


class TestPlatformSearcher:
    """Tests for isolated session behavior in PlatformSearcher."""

    @pytest.mark.asyncio
    async def test_update_platform_status_uses_isolated_session(
        self, searcher, mock_async_session_local
    ):
        """Progress updates should use a new session per write."""
        operation = MagicMock()
        operation.result = {}

        with patch(
            "comic_identity_engine.services.platform_searcher.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = MagicMock()
            mock_ops_manager.get_operation = AsyncMock(return_value=operation)
            mock_ops_manager.update_operation = AsyncMock(return_value=operation)
            mock_ops_manager_class.return_value = mock_ops_manager

            await searcher._update_platform_status(
                TEST_OPERATION_ID,
                "locg",
                "searching_retry_1",
                strategy="exact",
                retry=2,
            )

        mock_ops_manager_class.assert_called_once_with(mock_async_session_local)
        mock_ops_manager.update_operation.assert_awaited_once()
        mock_async_session_local.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_mapping_from_search_result_reuses_existing_mapping(
        self, searcher, mock_async_session_local
    ):
        """Search result mapping should not reinsert an identical mapping."""
        result = MagicMock()
        result.listings = [MagicMock(url="https://www.comicspriceguide.com/titles/x/1/pnwunt")]

        existing = MagicMock()
        existing.issue_id = TEST_ISSUE_ID

        with patch.object(
            searcher,
            "_extract_ids_from_url",
            return_value=("pnwunt", "1"),
        ), patch(
            "comic_identity_engine.services.platform_searcher.ExternalMappingRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.find_by_source = AsyncMock(return_value=existing)
            mock_repo.create_mapping = AsyncMock()
            mock_repo_class.return_value = mock_repo

            url = await searcher._create_mapping_from_search_result(
                "cpg",
                TEST_ISSUE_ID,
                result,
            )

        assert url == "https://www.comicspriceguide.com/titles/x/1/pnwunt"
        mock_repo.create_mapping.assert_not_awaited()
        mock_async_session_local.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_mapping_from_search_result_falls_back_to_result_url(
        self, searcher, mock_async_session_local
    ):
        """URL-only results should still create mappings without listings."""
        result = MagicMock()
        result.listings = []
        result.url = "https://atomicavenue.com/item/12345/1/details"

        with patch.object(
            searcher,
            "_extract_ids_from_url",
            return_value=("12345", None),
        ), patch(
            "comic_identity_engine.services.platform_searcher.ExternalMappingRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.find_by_source = AsyncMock(return_value=None)
            mock_repo.create_mapping = AsyncMock()
            mock_repo_class.return_value = mock_repo

            url = await searcher._create_mapping_from_search_result(
                "aa",
                TEST_ISSUE_ID,
                result,
            )

        assert url == "https://atomicavenue.com/item/12345/1/details"
        mock_repo.create_mapping.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_mapping_from_search_result_raises_on_conflict(
        self, searcher, mock_async_session_local
    ):
        """Conflicting platform mappings should still raise explicitly."""
        result = MagicMock()
        result.listings = [MagicMock(url="https://www.comicspriceguide.com/titles/x/1/pnwunt")]

        existing = MagicMock()
        existing.id = UUID("550e8400-e29b-41d4-a716-446655440099")
        existing.issue_id = UUID("550e8400-e29b-41d4-a716-446655440098")

        with patch.object(
            searcher,
            "_extract_ids_from_url",
            return_value=("pnwunt", "1"),
        ), patch(
            "comic_identity_engine.services.platform_searcher.ExternalMappingRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.find_by_source = AsyncMock(return_value=existing)
            mock_repo.create_mapping = AsyncMock()
            mock_repo_class.return_value = mock_repo

            with pytest.raises(DuplicateEntityError):
                await searcher._create_mapping_from_search_result(
                    "cpg",
                    TEST_ISSUE_ID,
                    result,
                )

    @pytest.mark.asyncio
    async def test_search_all_platforms_updates_as_tasks_finish(
        self, searcher
    ):
        """Results should be persisted incrementally, not after the slowest task only."""
        searcher._persist_operation_progress = AsyncMock()

        async def fake_runner(
            platform, issue_id, series_title, issue_number, year, publisher, operation_id
        ):
            delays = {"locg": 0.02, "aa": 0.0, "ccl": 0.01, "cpg": 0.0, "hip": 0.0}
            await asyncio.sleep(delays.get(platform, 0))
            return {"aa": "https://aa/item/1"}.get(platform)

        async def fake_task(
            platform, issue_id, series_title, issue_number, year, publisher, operation_id
        ):
            return platform, await fake_runner(
                platform,
                issue_id,
                series_title,
                issue_number,
                year,
                publisher,
                operation_id,
            )

        searcher._run_platform_search_task = AsyncMock(side_effect=fake_task)

        result = await searcher.search_all_platforms(
            issue_id=TEST_ISSUE_ID,
            series_title="Test",
            issue_number="1",
            year=1991,
            publisher="Marvel",
            operation_id=TEST_OPERATION_ID,
            source_platform="gcd",
            operations_manager=MagicMock(),
        )

        assert result["urls"] == {"aa": "https://aa/item/1"}
        assert result["status"]["gcd"] == "found"
        assert result["status"]["aa"] == "found"
        assert searcher._persist_operation_progress.await_count == 6
        initial_snapshot = searcher._persist_operation_progress.await_args_list[0].kwargs[
            "platform_status"
        ]
        assert initial_snapshot["gcd"] == "found"
        assert initial_snapshot["locg"] == "searching"
        assert initial_snapshot["aa"] == "searching"
