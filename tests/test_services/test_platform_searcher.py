"""Tests for platform searcher behavior and session isolation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

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
    async def test_create_mapping_from_search_result_uses_selected_url(
        self, searcher, mock_async_session_local
    ):
        """The returned URL should be the validated candidate URL."""
        result = MagicMock()

        url = await searcher._create_mapping_from_search_result(
            "cpg",
            TEST_ISSUE_ID,
            result,
            "https://www.comicspriceguide.com/titles/x-men/-1/pnwunt",
        )

        assert url == "https://www.comicspriceguide.com/titles/x-men/-1/pnwunt"
        mock_async_session_local.commit.assert_not_awaited()

    def test_select_candidate_url_rejects_atomic_avenue_series_page(self, searcher):
        """AA series pages are not valid issue matches."""
        result = MagicMock()
        result.listings = []
        result.url = "https://atomicavenue.com/atomic/atomic/series/17202/1/Uncanny-XMen-The"

        url, detail = searcher._select_candidate_url(
            platform="aa",
            result=result,
            series_title="X-Men",
            issue_number="-1",
        )

        assert url is None
        assert "issue page" in detail

    def test_select_candidate_url_accepts_cpg_issue_match(self, searcher):
        """CPG matches should require the requested issue number."""
        listing = MagicMock()
        listing.title = "X-Men #-1"
        listing.url = "https://www.comicspriceguide.com/titles/x-men/-1/phvpiu"
        result = MagicMock(listings=[listing], url=None)

        url, detail = searcher._select_candidate_url(
            platform="cpg",
            result=result,
            series_title="X-Men",
            issue_number="-1",
        )

        assert url == listing.url
        assert "matched" in detail

    def test_select_candidate_url_accepts_ccl_issue_match(self, searcher):
        """CCL issue URLs should be recognized as exact issue matches."""
        listing = MagicMock()
        listing.title = "X-Men #-1"
        listing.url = (
            "https://www.comiccollectorlive.com/issue/comic-books/"
            "X-Men-1991/-1/98ab98c9-a87a-4cd2-b49a-ee5232abc0ad"
        )
        result = MagicMock(listings=[listing], url=listing.url)

        url, detail = searcher._select_candidate_url(
            platform="ccl",
            result=result,
            series_title="X-Men",
            issue_number="-1",
        )

        assert url == listing.url
        assert "matched" in detail

    def test_select_candidate_url_rejects_hip_wrong_issue(self, searcher):
        """Hip results must match the requested issue, not just the title."""
        listing = MagicMock()
        listing.title = "X-Men (1991) 2-A FN"
        listing.url = "https://www.hipcomic.com/listing/x-men-1991-2-a-fn/14132846"
        result = MagicMock(listings=[listing], url=None)

        url, detail = searcher._select_candidate_url(
            platform="hip",
            result=result,
            series_title="X-Men",
            issue_number="-1",
        )

        assert url is None
        assert "requested issue" in detail

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
            if platform == "aa":
                return {
                    "url": "https://aa/item/1",
                    "status": "found",
                    "reason": "match_found",
                    "detail": "matched via strategy=exact",
                    "strategy": "exact",
                    "retry": 1,
                }
            return {
                "url": None,
                "status": "not_found",
                "reason": "no_match",
                "detail": "no match after 1 attempts across exact",
            }

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
        assert result["status"]["gcd"]["status"] == "found"
        assert result["status"]["gcd"]["reason"] == "source_mapping"
        assert result["status"]["aa"]["status"] == "found"
        assert result["status"]["aa"]["reason"] == "match_found"
        assert {event["platform"] for event in result["events"]} == {
            "gcd",
            "locg",
            "aa",
            "ccl",
            "cpg",
            "hip",
        }
        assert searcher._persist_operation_progress.await_count == 6
        initial_snapshot = searcher._persist_operation_progress.await_args_list[0].kwargs[
            "platform_status"
        ]
        assert initial_snapshot["gcd"]["status"] == "found"
        assert initial_snapshot["locg"]["status"] == "searching"
        assert initial_snapshot["aa"]["status"] == "searching"
        initial_events = searcher._persist_operation_progress.await_args_list[0].kwargs[
            "new_events"
        ]
        assert {event["platform"] for event in initial_events} == {
            "gcd",
            "locg",
            "aa",
            "ccl",
            "cpg",
            "hip",
        }

    @pytest.mark.asyncio
    async def test_search_single_platform_skips_false_positive_results(self, searcher):
        """Mismatched search results should not be reported as found."""
        searcher.scrapers = {"hip": MagicMock()}
        fake_result = MagicMock()
        fake_result.listings = [
            MagicMock(
                title="X-Men (1991) 2-A FN",
                url="https://www.hipcomic.com/listing/x-men-1991-2-a-fn/14132846",
            )
        ]
        fake_result.url = None
        fake_result.has_results = True

        with patch.object(searcher, "_execute_strategy", AsyncMock(return_value=fake_result)):
            result = await searcher._search_single_platform_with_strategies(
                platform="hip",
                issue_id=TEST_ISSUE_ID,
                series_title="X-Men",
                issue_number="-1",
                year=1991,
                publisher="Marvel",
                operation_id=TEST_OPERATION_ID,
            )

        assert result["status"] == "not_found"
        assert result["reason"] in {"no_match", "no_match_after_errors"}

    @pytest.mark.asyncio
    async def test_fuzzy_search_does_not_downgrade_negative_issue_to_positive_one(
        self, searcher
    ):
        """Fuzzy title search must keep issue matching deterministic."""
        scraper = MagicMock()
        broad_result = MagicMock()
        broad_result.listings = [
            MagicMock(
                title="The Uncanny X-Men (1981) #1",
                url="https://www.hipcomic.com/price-guide/us/marvel/comic/the-uncanny-x-men-1981/1/",
            )
        ]

        with patch.object(searcher, "_call_scraper", AsyncMock(return_value=broad_result)):
            result = await searcher._fuzzy_search(
                scraper=scraper,
                title="X-Men",
                issue="-1",
                year=1997,
                publisher="Marvel",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_run_platform_search_with_timeout_returns_reason(self, searcher):
        """Hard timeouts should become informative not_found results."""
        fake_settings = MagicMock(platform_search_timeout=0.01)

        with patch(
            "comic_identity_engine.services.platform_searcher.get_adapter_settings",
            return_value=fake_settings,
        ), patch.object(
            searcher,
            "_search_single_platform_with_strategies",
            new=AsyncMock(side_effect=asyncio.TimeoutError()),
        ):
            result = await searcher._run_platform_search_with_timeout(
                platform="locg",
                issue_id=TEST_ISSUE_ID,
                series_title="Test",
                issue_number="1",
                year=1991,
                publisher="Marvel",
                operation_id=TEST_OPERATION_ID,
            )

        assert result["status"] == "not_found"
        assert result["reason"] == "timeout"
        assert "platform timeout" in result["detail"]

    @pytest.mark.asyncio
    async def test_run_platform_search_without_configured_timeout_does_not_wrap(self, searcher):
        """Default behavior should not impose a hidden platform hard timeout."""
        fake_settings = MagicMock(platform_search_timeout=None)
        expected = {"status": "found", "url": "https://example.invalid"}

        with patch(
            "comic_identity_engine.services.platform_searcher.get_adapter_settings",
            return_value=fake_settings,
        ), patch.object(
            searcher,
            "_search_single_platform_with_strategies",
            new=AsyncMock(return_value=expected),
        ) as mock_search:
            result = await searcher._run_platform_search_with_timeout(
                platform="locg",
                issue_id=TEST_ISSUE_ID,
                series_title="Test",
                issue_number="1",
                year=1991,
                publisher="Marvel",
                operation_id=TEST_OPERATION_ID,
            )

        assert result == expected
        mock_search.assert_awaited_once()
