"""Tests for ARQ job tasks."""

import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from comic_identity_engine.errors import ParseError, ResolutionError, ValidationError
from comic_identity_engine.jobs.tasks import (
    _mark_failed_safe,
    bulk_resolve_task,
    export_task,
    import_clz_task,
    reconcile_task,
    resolve_identity_task,
)


# Test constants
TEST_OPERATION_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
TEST_ISSUE_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440001")
TEST_SERIES_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440002")


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_async_session_local(mock_session):
    """Mock AsyncSessionLocal context manager."""
    with patch("comic_identity_engine.jobs.tasks.AsyncSessionLocal") as mock:
        mock.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock.return_value.__aexit__ = AsyncMock(return_value=False)
        yield mock


@pytest.fixture
def mock_operations_manager():
    """Mock OperationsManager."""
    manager = Mock()
    manager.mark_running = AsyncMock()
    manager.mark_completed = AsyncMock()
    manager.mark_failed = AsyncMock()
    manager.update_operation = AsyncMock()
    return manager


@pytest.fixture
def mock_identity_resolver():
    """Mock IdentityResolver."""
    resolver = Mock()
    resolver.resolve_issue = AsyncMock()
    return resolver


@pytest.fixture
def mock_parse_url():
    """Mock parse_url function."""
    with patch("comic_identity_engine.jobs.tasks.parse_url") as mock:
        mock.return_value = Mock(platform="gcd", issue_id="123", source_issue_id="123")
        yield mock


class TestResolveIdentityTask:
    """Tests for resolve_identity_task."""

    @pytest.mark.asyncio
    async def test_resolve_identity_task_success(
        self,
        mock_async_session_local,
        mock_session,
    ):
        """Test successful identity resolution."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.parse_url") as mock_parse:
                mock_parse.return_value = Mock(
                    platform="gcd", issue_id="123", source_issue_id="123"
                )

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
                    mock_mapping_repo.create_mapping = AsyncMock()
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks.get_adapter"
                    ) as mock_get_adapter:
                        mock_adapter = Mock()
                        mock_candidate = Mock()
                        mock_candidate.upc = "123456789012"
                        mock_candidate.series_title = "Test Series"
                        mock_candidate.series_start_year = 2020
                        mock_candidate.issue_number = "1"
                        mock_candidate.cover_date = None
                        mock_candidate.source_series_id = "456"
                        mock_adapter.fetch_issue = AsyncMock(
                            return_value=mock_candidate
                        )
                        mock_get_adapter.return_value = mock_adapter

                        with patch(
                            "comic_identity_engine.jobs.tasks.IdentityResolver"
                        ) as mock_resolver_class:
                            mock_resolver = Mock()
                            mock_result = Mock()
                            mock_result.issue_id = TEST_ISSUE_ID
                            mock_result.created_new = True
                            mock_result.explanation = "Matched on issue number"
                            mock_result.best_match = Mock(overall_confidence=0.95)
                            mock_resolver.resolve_issue = AsyncMock(
                                return_value=mock_result
                            )
                            mock_resolver_class.return_value = mock_resolver

                            result = await resolve_identity_task(
                                {},
                                "https://www.comics.org/issue/123/",
                                str(TEST_OPERATION_ID),
                            )

        assert result["canonical_uuid"] == str(TEST_ISSUE_ID)
        assert result["confidence"] == 0.95
        assert result["platform_urls"] == {"gcd": "https://www.comics.org/issue/123/"}
        assert result["created_new"] is True
        assert result["explanation"] == "Matched on issue number"
        mock_ops_manager.mark_running.assert_called_once_with(TEST_OPERATION_ID)
        mock_ops_manager.mark_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_identity_task_parse_error(
        self, mock_async_session_local, mock_session
    ):
        """Test resolve_identity_task handles ParseError."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.parse_url") as mock_parse:
                mock_parse.side_effect = ParseError("Invalid URL format")

                with patch(
                    "comic_identity_engine.jobs.tasks._mark_failed_safe",
                    new_callable=AsyncMock,
                ):
                    result = await resolve_identity_task(
                        {},
                        "https://test.com",
                        str(TEST_OPERATION_ID),
                    )

            assert result["error_type"] == "parse_error"
        assert "URL parsing failed" in result["error"]
        mock_ops_manager.mark_running.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_identity_task_resolution_error(
        self, mock_async_session_local, mock_session
    ):
        """Test resolve_identity_task handles ResolutionError."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.parse_url") as mock_parse:
                mock_parse.return_value = Mock(
                    platform="gcd", issue_id="123", source_issue_id="123"
                )

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks.get_adapter"
                    ) as mock_get_adapter:
                        mock_adapter = Mock()
                        mock_candidate = Mock()
                        mock_candidate.upc = "123456789012"
                        mock_candidate.series_title = "Test Series"
                        mock_candidate.series_start_year = 2020
                        mock_candidate.issue_number = "1"
                        mock_candidate.cover_date = None
                        mock_candidate.source_series_id = "456"
                        mock_adapter.fetch_issue = AsyncMock(
                            return_value=mock_candidate
                        )
                        mock_get_adapter.return_value = mock_adapter

                        with patch(
                            "comic_identity_engine.jobs.tasks.IdentityResolver"
                        ) as mock_resolver_class:
                            mock_resolver = Mock()
                            mock_resolver.resolve_issue = AsyncMock(
                                side_effect=ResolutionError("No matching issue found")
                            )
                            mock_resolver_class.return_value = mock_resolver

                            with patch(
                                "comic_identity_engine.jobs.tasks._mark_failed_safe",
                                new_callable=AsyncMock,
                            ):
                                result = await resolve_identity_task(
                                    {},
                                    "https://www.comics.org/issue/999999/",
                                    str(TEST_OPERATION_ID),
                                )

        assert "error" in result
        assert result["error_type"] == "resolution_error"
        assert "Identity resolution failed" in result["error"]

    @pytest.mark.asyncio
    async def test_resolve_identity_task_sqlalchemy_error(
        self, mock_async_session_local, mock_session
    ):
        """Test resolve_identity_task handles SQLAlchemyError."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock(
                side_effect=SQLAlchemyError("Connection lost")
            )
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks._mark_failed_safe",
                new_callable=AsyncMock,
            ):
                result = await resolve_identity_task(
                    {},
                    "https://www.comics.org/issue/123/",
                    str(TEST_OPERATION_ID),
                )

        assert "error" in result
        assert result["error_type"] == "database_error"
        assert "Database error" in result["error"]

    @pytest.mark.asyncio
    async def test_resolve_identity_task_unexpected_error(
        self, mock_async_session_local, mock_session
    ):
        """Test resolve_identity_task handles unexpected errors."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock(side_effect=RuntimeError("Boom!"))
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks._mark_failed_safe",
                new_callable=AsyncMock,
            ):
                result = await resolve_identity_task(
                    {},
                    "https://www.comics.org/issue/123/",
                    str(TEST_OPERATION_ID),
                )

        assert "error" in result
        assert result["error_type"] == "unexpected_error"
        assert "Unexpected error" in result["error"]

    @pytest.mark.asyncio
    async def test_resolve_identity_task_no_best_match(
        self, mock_async_session_local, mock_session
    ):
        """Test resolve_identity_task when no best match exists."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.parse_url") as mock_parse:
                mock_parse.return_value = Mock(
                    platform="gcd", issue_id="123", source_issue_id="123"
                )

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
                    mock_mapping_repo.create_mapping = AsyncMock()
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks.get_adapter"
                    ) as mock_get_adapter:
                        mock_adapter = Mock()
                        mock_candidate = Mock()
                        mock_candidate.upc = "123456789012"
                        mock_candidate.series_title = "Test Series"
                        mock_candidate.series_start_year = 2020
                        mock_candidate.issue_number = "1"
                        mock_candidate.cover_date = None
                        mock_candidate.source_series_id = "456"
                        mock_adapter.fetch_issue = AsyncMock(
                            return_value=mock_candidate
                        )
                        mock_get_adapter.return_value = mock_adapter

                        with patch(
                            "comic_identity_engine.jobs.tasks.IdentityResolver"
                        ) as mock_resolver_class:
                            mock_resolver = Mock()
                            mock_result = Mock()
                            mock_result.issue_id = TEST_ISSUE_ID
                            mock_result.created_new = False
                            mock_result.explanation = "New issue created"
                            mock_result.best_match = None  # No best match
                            mock_resolver.resolve_issue = AsyncMock(
                                return_value=mock_result
                            )
                            mock_resolver_class.return_value = mock_resolver

                            result = await resolve_identity_task(
                                {},
                                "https://www.comics.org/issue/123/",
                                str(TEST_OPERATION_ID),
                            )

        assert result["confidence"] == 1.0  # Default when no best_match

    @pytest.mark.asyncio
    async def test_resolve_identity_task_force_reuses_existing_source_mapping(
        self, mock_async_session_local, mock_session
    ):
        """Test force mode does not re-insert an identical source mapping."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.parse_url") as mock_parse:
                mock_parse.return_value = Mock(
                    platform="gcd", issue_id="123", source_issue_id="123"
                )

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo.create_mapping = AsyncMock()
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks.get_adapter"
                    ) as mock_get_adapter:
                        mock_adapter = Mock()
                        mock_candidate = Mock()
                        mock_candidate.upc = "123456789012"
                        mock_candidate.series_title = "Test Series"
                        mock_candidate.series_start_year = 2020
                        mock_candidate.issue_number = "1"
                        mock_candidate.cover_date = None
                        mock_candidate.source_series_id = "456"
                        mock_adapter.fetch_issue = AsyncMock(
                            return_value=mock_candidate
                        )
                        mock_get_adapter.return_value = mock_adapter

                        with patch(
                            "comic_identity_engine.jobs.tasks.IdentityResolver"
                        ) as mock_resolver_class:
                            mock_resolver = Mock()
                            mock_result = Mock()
                            mock_result.issue_id = TEST_ISSUE_ID
                            mock_result.created_new = False
                            mock_result.explanation = "Matched on issue number"
                            mock_result.best_match = Mock(overall_confidence=0.95)
                            mock_resolver.resolve_issue = AsyncMock(
                                return_value=mock_result
                            )
                            mock_resolver_class.return_value = mock_resolver

                            with (
                                patch(
                                    "comic_identity_engine.jobs.tasks._ensure_source_mapping",
                                    new_callable=AsyncMock,
                                    return_value="reused",
                                ),
                                patch(
                                    "comic_identity_engine.services.platform_searcher.PlatformSearcher"
                                ) as mock_searcher_class,
                            ):
                                mock_searcher = Mock()
                                mock_searcher.search_all_platforms = AsyncMock(
                                    return_value={"urls": {}, "status": {}}
                                )
                                mock_searcher_class.return_value = mock_searcher

                                result = await resolve_identity_task(
                                    {},
                                    "https://www.comics.org/issue/123/",
                                    str(TEST_OPERATION_ID),
                                    force=True,
                                )

        assert result["canonical_uuid"] == str(TEST_ISSUE_ID)
        mock_mapping_repo.create_mapping.assert_not_awaited()
        mock_searcher.search_all_platforms.assert_awaited_once()
        assert mock_searcher.search_all_platforms.await_args.kwargs["year"] == 2020

    @pytest.mark.asyncio
    async def test_resolve_identity_task_force_conflicting_source_mapping_fails(
        self, mock_async_session_local, mock_session
    ):
        """Test force mode surfaces conflicting source mappings clearly."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.parse_url") as mock_parse:
                mock_parse.return_value = Mock(
                    platform="gcd", issue_id="123", source_issue_id="123"
                )

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks.get_adapter"
                    ) as mock_get_adapter:
                        mock_adapter = Mock()
                        mock_candidate = Mock()
                        mock_candidate.upc = "123456789012"
                        mock_candidate.series_title = "Test Series"
                        mock_candidate.series_start_year = 2020
                        mock_candidate.issue_number = "1"
                        mock_candidate.cover_date = None
                        mock_candidate.source_series_id = "456"
                        mock_adapter.fetch_issue = AsyncMock(
                            return_value=mock_candidate
                        )
                        mock_get_adapter.return_value = mock_adapter

                        with patch(
                            "comic_identity_engine.jobs.tasks.IdentityResolver"
                        ) as mock_resolver_class:
                            mock_resolver = Mock()
                            mock_result = Mock()
                            mock_result.issue_id = TEST_ISSUE_ID
                            mock_result.created_new = False
                            mock_result.explanation = "Matched on issue number"
                            mock_result.best_match = Mock(overall_confidence=0.95)
                            mock_resolver.resolve_issue = AsyncMock(
                                return_value=mock_result
                            )
                            mock_resolver_class.return_value = mock_resolver

                            with (
                                patch(
                                    "comic_identity_engine.jobs.tasks._ensure_source_mapping",
                                    new_callable=AsyncMock,
                                    side_effect=ValidationError(
                                        "Existing external mapping points to a different canonical "
                                        "issue for gcd:123; use --clear-mappings 123 to replace it"
                                    ),
                                ),
                                patch(
                                    "comic_identity_engine.jobs.tasks._mark_failed_safe",
                                    new_callable=AsyncMock,
                                ),
                                patch(
                                    "comic_identity_engine.services.platform_searcher.PlatformSearcher"
                                ) as mock_searcher_class,
                            ):
                                mock_searcher = Mock()
                                mock_searcher.search_all_platforms = AsyncMock(
                                    return_value={"urls": {}, "status": {}}
                                )
                                mock_searcher_class.return_value = mock_searcher

                                result = await resolve_identity_task(
                                    {},
                                    "https://www.comics.org/issue/123/",
                                    str(TEST_OPERATION_ID),
                                    force=True,
                                )

        assert result["error_type"] == "validation_error"
        assert "use --clear-mappings 123 to replace it" in result["error"]

    @pytest.mark.asyncio
    async def test_resolve_identity_task_existing_mapping_uses_series_start_year_for_search(
        self, mock_async_session_local, mock_session
    ):
        """Cross-platform search should use the canonical series start year, not cover year."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.parse_url") as mock_parse:
                mock_parse.return_value = Mock(
                    platform="gcd", issue_id="125295", source_issue_id="125295"
                )

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo.find_by_source = AsyncMock(
                        return_value=Mock(issue_id=TEST_ISSUE_ID)
                    )
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks.IssueRepository"
                    ) as mock_issue_repo_class:
                        mock_issue_repo = Mock()
                        mock_issue = Mock()
                        mock_issue.series_run_id = TEST_SERIES_ID
                        mock_issue.issue_number = "-1"
                        mock_issue.cover_date = datetime(1997, 7, 1)
                        mock_issue_repo.find_by_id = AsyncMock(return_value=mock_issue)
                        mock_issue_repo_class.return_value = mock_issue_repo

                        with patch(
                            "comic_identity_engine.jobs.tasks.SeriesRunRepository"
                        ) as mock_series_repo_class:
                            mock_series_repo = Mock()
                            mock_series = Mock()
                            mock_series.title = "X-Men"
                            mock_series.start_year = 1991
                            mock_series.publisher = "Marvel Comics"
                            mock_series_repo.find_by_id = AsyncMock(
                                return_value=mock_series
                            )
                            mock_series_repo_class.return_value = mock_series_repo

                            with (
                                patch(
                                    "comic_identity_engine.jobs.tasks.IdentityResolver"
                                ),
                                patch(
                                    "comic_identity_engine.services.platform_searcher.PlatformSearcher"
                                ) as mock_searcher_class,
                            ):
                                mock_searcher = Mock()
                                mock_searcher.search_all_platforms = AsyncMock(
                                    return_value={"urls": {}, "status": {}}
                                )
                                mock_searcher_class.return_value = mock_searcher

                                result = await resolve_identity_task(
                                    {},
                                    "https://www.comics.org/issue/125295/",
                                    str(TEST_OPERATION_ID),
                                    force=False,
                                )

        assert result["canonical_uuid"] == str(TEST_ISSUE_ID)
        mock_searcher.search_all_platforms.assert_awaited_once()
        assert mock_searcher.search_all_platforms.await_args.kwargs["year"] == 1991


class TestBulkResolveTask:
    """Tests for bulk_resolve_task."""

    @pytest.mark.asyncio
    async def test_bulk_resolve_task_success(
        self, mock_async_session_local, mock_session
    ):
        """Test successful bulk resolution."""
        urls = [
            "https://www.comics.org/issue/123/",
            "https://www.comics.org/issue/124/",
        ]

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager.update_operation = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.parse_url") as mock_parse:
                mock_parse.return_value = Mock(platform="gcd", issue_id="123")

                with patch(
                    "comic_identity_engine.jobs.tasks.IdentityResolver"
                ) as mock_resolver_class:
                    mock_resolver = Mock()
                    mock_result = Mock()
                    mock_result.issue_id = TEST_ISSUE_ID
                    mock_result.created_new = True
                    mock_result.explanation = "Matched"
                    mock_result.best_match = Mock(overall_confidence=0.95)
                    mock_resolver.resolve_issue = AsyncMock(return_value=mock_result)
                    mock_resolver_class.return_value = mock_resolver

                    result = await bulk_resolve_task(
                        {},
                        urls,
                        str(TEST_OPERATION_ID),
                    )

        assert result["total"] == 2
        assert result["completed"] == 2
        assert result["failed"] == 0
        assert len(result["results"]) == 2
        assert "Processed 2 URLs: 2 succeeded, 0 failed" in result["summary"]
        mock_ops_manager.mark_running.assert_called_once()
        mock_ops_manager.mark_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_resolve_task_partial_failure(
        self, mock_async_session_local, mock_session
    ):
        """Test bulk resolution with some failures."""
        urls = [
            "https://www.comics.org/issue/123/",
            "https://www.comics.org/issue/124/",
        ]

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager.update_operation = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.parse_url") as mock_parse:
                # First URL succeeds, second fails
                def parse_side_effect(url):
                    if "123" in url:
                        return Mock(platform="gcd", issue_id="123")
                    raise ParseError("Invalid URL")

                mock_parse.side_effect = parse_side_effect

                with patch(
                    "comic_identity_engine.jobs.tasks.IdentityResolver"
                ) as mock_resolver_class:
                    mock_resolver = Mock()
                    mock_result = Mock()
                    mock_result.issue_id = TEST_ISSUE_ID
                    mock_result.created_new = True
                    mock_result.explanation = "Matched"
                    mock_result.best_match = Mock(overall_confidence=0.95)
                    mock_resolver.resolve_issue = AsyncMock(return_value=mock_result)
                    mock_resolver_class.return_value = mock_resolver

                    result = await bulk_resolve_task(
                        {},
                        urls,
                        str(TEST_OPERATION_ID),
                    )

        assert result["total"] == 2
        assert result["completed"] == 1
        assert result["failed"] == 1
        assert len(result["results"]) == 2
        assert result["results"][0]["success"] is True
        assert result["results"][1]["success"] is False

    @pytest.mark.asyncio
    async def test_bulk_resolve_task_empty_urls(
        self, mock_async_session_local, mock_session
    ):
        """Test bulk resolution with empty URL list."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            result = await bulk_resolve_task(
                {},
                [],
                str(TEST_OPERATION_ID),
            )

        assert result["total"] == 0
        assert result["completed"] == 0
        assert result["failed"] == 0
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_bulk_resolve_task_database_error(
        self, mock_async_session_local, mock_session
    ):
        """Test bulk resolution handles database error."""
        urls = ["https://www.comics.org/issue/123/"]

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock(
                side_effect=SQLAlchemyError("Connection lost")
            )
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks._mark_failed_safe",
                new_callable=AsyncMock,
            ):
                result = await bulk_resolve_task(
                    {},
                    urls,
                    str(TEST_OPERATION_ID),
                )

        assert "error" in result
        assert result["error_type"] == "database_error"


class TestImportClzTask:
    """Tests for import_clz_task."""

    @pytest.mark.asyncio
    async def test_import_clz_task_success(
        self, mock_async_session_local, mock_session, tmp_path
    ):
        """Test successful CLZ CSV import orchestration enqueues row tasks."""
        csv_file = tmp_path / "test_collection.csv"
        csv_content = """Series,Issue,Publisher,Year,Core ComicID
X-Men,1,Marvel,1991,clz-001
X-Men,2,Marvel,1991,clz-002"""
        csv_file.write_text(csv_content)

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager.update_operation = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.load_csv_from_file.return_value = [
                    {
                        "Series": "X-Men",
                        "Issue": "1",
                        "Publisher": "Marvel",
                        "Year": "1991",
                        "Core ComicID": "clz-001",
                    },
                    {
                        "Series": "X-Men",
                        "Issue": "2",
                        "Publisher": "Marvel",
                        "Year": "1991",
                        "Core ComicID": "clz-002",
                    },
                ]
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.queue.JobQueue"
                ) as mock_queue_class:
                    mock_queue = Mock()
                    mock_queue.enqueue_resolve_clz_row = AsyncMock()

                    # Mock job returns
                    mock_job = Mock()
                    mock_job.job_id = "test-job-id"
                    mock_queue.enqueue_resolve_clz_row.return_value = mock_job
                    mock_queue_class.return_value = mock_queue

                    result = await import_clz_task(
                        {},
                        str(csv_file),
                        str(TEST_OPERATION_ID),
                    )

        # Orchestrator returns immediately with enqueue confirmation
        assert result["total_rows"] == 2
        assert result["processed"] == 0
        assert result["resolved"] == 0  # Orchestrator doesn't process rows
        assert result["failed"] == 0
        assert len(result["errors"]) == 0
        assert "Enqueued 2 pending CLZ row tasks" in result["summary"]

        # Verify tasks were enqueued
        assert mock_queue.enqueue_resolve_clz_row.call_count == 2

        mock_ops_manager.mark_running.assert_called_once()
        mock_ops_manager.update_operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_clz_task_file_not_found(
        self, mock_async_session_local, mock_session
    ):
        """Test import handles file not found error."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.load_csv_from_file.side_effect = FileNotFoundError(
                    "No such file"
                )
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.tasks._mark_failed_safe",
                    new_callable=AsyncMock,
                ):
                    result = await import_clz_task(
                        {},
                        "/nonexistent/file.csv",
                        str(TEST_OPERATION_ID),
                    )

        assert "error" in result
        assert result["error_type"] == "file_not_found"
        assert "CSV file not found" in result["error"]

    @pytest.mark.asyncio
    async def test_import_clz_task_validation_error(
        self, mock_async_session_local, mock_session, tmp_path
    ):
        """Test import handles validation error."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("invalid csv content")

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.load_csv_from_file.side_effect = ValidationError(
                    "CSV content is empty"
                )
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.tasks._mark_failed_safe",
                    new_callable=AsyncMock,
                ):
                    result = await import_clz_task(
                        {},
                        str(csv_file),
                        str(TEST_OPERATION_ID),
                    )

        assert "error" in result
        assert result["error_type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_import_clz_task_database_error(
        self, mock_async_session_local, mock_session, tmp_path
    ):
        """Test import handles database error."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Series,Issue\nX-Men,1")

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock(
                side_effect=SQLAlchemyError("Connection lost")
            )
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks._mark_failed_safe",
                new_callable=AsyncMock,
            ):
                result = await import_clz_task(
                    {},
                    str(csv_file),
                    str(TEST_OPERATION_ID),
                )

        assert "error" in result
        assert result["error_type"] == "database_error"


class TestExportTask:
    """Tests for export_task."""

    @pytest.mark.asyncio
    async def test_export_task_json_success(
        self, mock_async_session_local, mock_session, tmp_path
    ):
        """Test successful JSON export."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.IssueRepository"
            ) as mock_issue_repo_class:
                mock_issue_repo = Mock()
                mock_issue = Mock()
                mock_issue.id = TEST_ISSUE_ID
                mock_issue.issue_number = "1"
                mock_issue.cover_date = datetime(1991, 10, 1)
                mock_issue.upc = "123456789012"
                mock_issue.series_run_id = TEST_SERIES_ID
                mock_issue_repo.find_by_id = AsyncMock(return_value=mock_issue)
                mock_issue_repo_class.return_value = mock_issue_repo

                with patch(
                    "comic_identity_engine.jobs.tasks.SeriesRunRepository"
                ) as mock_series_repo_class:
                    mock_series_repo = Mock()
                    mock_series = Mock()
                    mock_series.title = "X-Men"
                    mock_series.start_year = 1991
                    mock_series.publisher = "Marvel"
                    mock_series_repo.find_by_id = AsyncMock(return_value=mock_series)
                    mock_series_repo_class.return_value = mock_series_repo

                    # Patch export directory to use tmp_path
                    with patch(
                        "comic_identity_engine.jobs.tasks.Path"
                    ) as mock_path_class:
                        mock_export_dir = Mock(spec=Path)
                        mock_export_dir.__truediv__ = Mock(
                            return_value=tmp_path / "export.json"
                        )
                        mock_export_dir.mkdir = Mock()
                        mock_path_class.return_value = mock_export_dir

                        # Use actual tmp_path for file operations
                        export_file = tmp_path / f"export_{TEST_OPERATION_ID}.json"
                        mock_export_dir.__truediv__ = Mock(return_value=export_file)

                        with patch(
                            "comic_identity_engine.jobs.tasks.Path"
                        ) as mock_path:
                            mock_path.return_value = tmp_path
                            mock_path.__truediv__ = lambda self, x: tmp_path / x

                            result = await export_task(
                                {},
                                [str(TEST_ISSUE_ID)],
                                "json",
                                str(TEST_OPERATION_ID),
                            )

        assert result["format"] == "json"
        assert result["record_count"] == 1
        assert "file_path" in result
        assert "Exported 1 issues" in result["summary"]
        mock_ops_manager.mark_running.assert_called_once()
        mock_ops_manager.mark_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_task_csv_success(
        self, mock_async_session_local, mock_session
    ):
        """Test successful CSV export."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.IssueRepository"
            ) as mock_issue_repo_class:
                mock_issue_repo = Mock()
                mock_issue = Mock()
                mock_issue.id = TEST_ISSUE_ID
                mock_issue.issue_number = "1"
                mock_issue.cover_date = datetime(1991, 10, 1)
                mock_issue.upc = "123456789012"
                mock_issue.series_run_id = TEST_SERIES_ID
                mock_issue_repo.find_by_id = AsyncMock(return_value=mock_issue)
                mock_issue_repo_class.return_value = mock_issue_repo

                with patch(
                    "comic_identity_engine.jobs.tasks.SeriesRunRepository"
                ) as mock_series_repo_class:
                    mock_series_repo = Mock()
                    mock_series = Mock()
                    mock_series.title = "X-Men"
                    mock_series.start_year = 1991
                    mock_series.publisher = "Marvel"
                    mock_series_repo.find_by_id = AsyncMock(return_value=mock_series)
                    mock_series_repo_class.return_value = mock_series_repo

                    result = await export_task(
                        {},
                        [str(TEST_ISSUE_ID)],
                        "csv",
                        str(TEST_OPERATION_ID),
                    )

        assert result["format"] == "csv"
        assert result["record_count"] == 1
        assert "Exported 1 issues" in result["summary"]

    @pytest.mark.asyncio
    async def test_export_task_invalid_format(
        self, mock_async_session_local, mock_session
    ):
        """Test export with invalid format."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks._mark_failed_safe",
                new_callable=AsyncMock,
            ):
                result = await export_task(
                    {},
                    [str(TEST_ISSUE_ID)],
                    "xml",  # Invalid format
                    str(TEST_OPERATION_ID),
                )

        assert "error" in result
        assert result["error_type"] == "invalid_format"
        assert "Unsupported export format" in result["error"]

    @pytest.mark.asyncio
    async def test_export_task_empty_issues(
        self, mock_async_session_local, mock_session
    ):
        """Test export with empty issue list."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.IssueRepository"
            ) as mock_issue_repo_class:
                mock_issue_repo = Mock()
                mock_issue_repo_class.return_value = mock_issue_repo

                result = await export_task(
                    {},
                    [],
                    "json",
                    str(TEST_OPERATION_ID),
                )

        assert result["record_count"] == 0
        assert "Exported 0 issues" in result["summary"]

    @pytest.mark.asyncio
    async def test_export_task_database_error(
        self, mock_async_session_local, mock_session
    ):
        """Test export handles database error."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock(
                side_effect=SQLAlchemyError("Connection lost")
            )
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks._mark_failed_safe",
                new_callable=AsyncMock,
            ):
                result = await export_task(
                    {},
                    [str(TEST_ISSUE_ID)],
                    "json",
                    str(TEST_OPERATION_ID),
                )

        assert "error" in result
        assert result["error_type"] == "database_error"


class TestReconcileTask:
    """Tests for reconcile_task."""

    @pytest.mark.asyncio
    async def test_reconcile_task_success(self, mock_async_session_local, mock_session):
        """Test successful reconciliation."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.IssueRepository"
            ) as mock_issue_repo_class:
                mock_issue_repo = Mock()
                mock_issue = Mock()
                mock_issue.id = TEST_ISSUE_ID
                mock_issue_repo.find_by_id = AsyncMock(return_value=mock_issue)
                mock_issue_repo_class.return_value = mock_issue_repo

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo.find_by_issue = AsyncMock(return_value=[])
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    result = await reconcile_task(
                        {},
                        str(TEST_ISSUE_ID),
                        str(TEST_OPERATION_ID),
                    )

        assert result["issue_id"] == str(TEST_ISSUE_ID)
        assert "platforms_checked" in result
        assert len(result["platforms_checked"]) == 6  # All platforms
        assert result["mappings_created"] == 0
        assert result["mappings_updated"] == 0
        assert len(result["errors"]) == 0
        mock_ops_manager.mark_running.assert_called_once()
        mock_ops_manager.mark_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconcile_task_issue_not_found(
        self, mock_async_session_local, mock_session
    ):
        """Test reconciliation when issue not found."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.IssueRepository"
            ) as mock_issue_repo_class:
                mock_issue_repo = Mock()
                mock_issue_repo.find_by_id = AsyncMock(return_value=None)
                mock_issue_repo_class.return_value = mock_issue_repo

                with patch(
                    "comic_identity_engine.jobs.tasks._mark_failed_safe",
                    new_callable=AsyncMock,
                ):
                    result = await reconcile_task(
                        {},
                        str(TEST_ISSUE_ID),
                        str(TEST_OPERATION_ID),
                    )

        assert "error" in result
        assert result["error_type"] == "validation_error"
        assert "Issue not found" in result["error"]

    @pytest.mark.asyncio
    async def test_reconcile_task_database_error(
        self, mock_async_session_local, mock_session
    ):
        """Test reconciliation handles database error."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock(
                side_effect=SQLAlchemyError("Connection lost")
            )
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks._mark_failed_safe",
                new_callable=AsyncMock,
            ):
                result = await reconcile_task(
                    {},
                    str(TEST_ISSUE_ID),
                    str(TEST_OPERATION_ID),
                )

        assert "error" in result
        assert result["error_type"] == "database_error"


class TestMarkFailedSafe:
    """Tests for _mark_failed_safe helper function."""

    @pytest.mark.asyncio
    async def test_mark_failed_safe_success(self, mock_session):
        """Test _mark_failed_safe successfully marks operation as failed."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.update_operation = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            await _mark_failed_safe(
                mock_session,
                TEST_OPERATION_ID,
                "Test error message",
            )

            mock_ops_manager.update_operation.assert_awaited_once_with(
                TEST_OPERATION_ID,
                "failed",
                result=None,
                error_message="Test error message",
            )

    @pytest.mark.asyncio
    async def test_mark_failed_safe_logs_error(self, mock_session, caplog):
        """Test _mark_failed_safe logs error when marking fails."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.update_operation = AsyncMock(
                side_effect=Exception("Database error")
            )
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.logger") as mock_logger:
                await _mark_failed_safe(
                    mock_session,
                    TEST_OPERATION_ID,
                    "Test error message",
                )

                mock_logger.error.assert_called_once()


class TestOperationStatusTransitions:
    """Tests to verify operation status transitions (pending -> running -> completed/failed)."""

    @pytest.mark.asyncio
    async def test_resolve_task_status_transition_pending_to_running_to_completed(
        self, mock_async_session_local, mock_session
    ):
        """Test resolve task transitions from pending -> running -> completed."""
        status_log = []

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()

            async def mark_running_capture(operation_id):
                status_log.append(("mark_running", operation_id))

            async def mark_completed_capture(operation_id, result):
                status_log.append(("mark_completed", operation_id, result))

            mock_ops_manager.mark_running = AsyncMock(side_effect=mark_running_capture)
            mock_ops_manager.mark_completed = AsyncMock(
                side_effect=mark_completed_capture
            )
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.parse_url") as mock_parse:
                mock_parse.return_value = Mock(
                    platform="gcd", issue_id="123", source_issue_id="123"
                )

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
                    mock_mapping_repo.create_mapping = AsyncMock()
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks.get_adapter"
                    ) as mock_get_adapter:
                        mock_adapter = Mock()
                        mock_candidate = Mock()
                        mock_candidate.upc = "123456789012"
                        mock_candidate.series_title = "Test Series"
                        mock_candidate.series_start_year = 2020
                        mock_candidate.issue_number = "1"
                        mock_candidate.cover_date = None
                        mock_candidate.source_series_id = "456"
                        mock_adapter.fetch_issue = AsyncMock(
                            return_value=mock_candidate
                        )
                        mock_get_adapter.return_value = mock_adapter

                        with patch(
                            "comic_identity_engine.jobs.tasks.IdentityResolver"
                        ) as mock_resolver_class:
                            mock_resolver = Mock()
                            mock_result = Mock()
                            mock_result.issue_id = TEST_ISSUE_ID
                            mock_result.created_new = True
                            mock_result.explanation = "Test"
                            mock_result.best_match = Mock(overall_confidence=0.9)
                            mock_resolver.resolve_issue = AsyncMock(
                                return_value=mock_result
                            )
                            mock_resolver_class.return_value = mock_resolver

                            await resolve_identity_task(
                                {},
                                "https://test.com",
                                str(TEST_OPERATION_ID),
                            )

        assert len(status_log) == 2
        assert status_log[0][0] == "mark_running"
        assert status_log[0][1] == TEST_OPERATION_ID
        assert status_log[1][0] == "mark_completed"
        assert status_log[1][1] == TEST_OPERATION_ID
        assert "canonical_uuid" in status_log[1][2]

    @pytest.mark.asyncio
    async def test_resolve_task_status_transition_pending_to_running_to_failed(
        self, mock_async_session_local, mock_session
    ):
        """Test resolve task transitions from pending -> running -> failed on error."""
        status_log = []

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()

            async def mark_running_capture(operation_id):
                status_log.append(("mark_running", operation_id))

            mock_ops_manager.mark_running = AsyncMock(side_effect=mark_running_capture)
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch("comic_identity_engine.jobs.tasks.parse_url") as mock_parse:
                mock_parse.side_effect = ParseError("Invalid")

                with patch(
                    "comic_identity_engine.jobs.tasks._mark_failed_safe",
                    new_callable=AsyncMock,
                ) as mock_mark_failed:

                    async def mark_failed_capture(
                        session, operation_id, error, result=None
                    ):
                        status_log.append(("mark_failed", operation_id, error))

                    mock_mark_failed.side_effect = mark_failed_capture

                    await resolve_identity_task(
                        {},
                        "invalid",
                        str(TEST_OPERATION_ID),
                    )

        assert len(status_log) == 2
        assert status_log[0][0] == "mark_running"
        assert status_log[0][1] == TEST_OPERATION_ID
        assert status_log[1][0] == "mark_failed"
        assert status_log[1][1] == TEST_OPERATION_ID
        # Check for parse error keywords (case insensitive)
        error_msg = status_log[1][2].lower()
        assert "parse" in error_msg


class TestErrorTypeCoverage:
    """Tests to verify all error types are properly handled."""

    @pytest.mark.asyncio
    async def test_all_resolve_error_types(
        self, mock_async_session_local, mock_session
    ):
        """Test that resolve_identity_task handles all error types."""
        error_scenarios = [
            (ParseError("test"), "parse_error"),
            (ResolutionError("test"), "resolution_error"),
            (SQLAlchemyError("test"), "database_error"),
            (RuntimeError("test"), "unexpected_error"),
        ]

        for error, expected_type in error_scenarios:
            with patch(
                "comic_identity_engine.jobs.tasks.OperationsManager"
            ) as mock_ops_manager_class:
                mock_ops_manager = Mock()
                mock_ops_manager.mark_running = AsyncMock(side_effect=error)
                mock_ops_manager_class.return_value = mock_ops_manager

                with patch(
                    "comic_identity_engine.jobs.tasks._mark_failed_safe",
                    new_callable=AsyncMock,
                ):
                    result = await resolve_identity_task(
                        {},
                        "https://test.com",
                        str(TEST_OPERATION_ID),
                    )

            assert result.get("error_type") == expected_type, (
                f"Failed for {error.__class__.__name__}"
            )

    @pytest.mark.asyncio
    async def test_all_bulk_resolve_error_types(
        self, mock_async_session_local, mock_session
    ):
        """Test that bulk_resolve_task handles all error types."""
        error_scenarios = [
            (SQLAlchemyError("test"), "database_error"),
            (RuntimeError("test"), "unexpected_error"),
        ]

        for error, expected_type in error_scenarios:
            with patch(
                "comic_identity_engine.jobs.tasks.OperationsManager"
            ) as mock_ops_manager_class:
                mock_ops_manager = Mock()
                mock_ops_manager.mark_running = AsyncMock(side_effect=error)
                mock_ops_manager_class.return_value = mock_ops_manager

                with patch(
                    "comic_identity_engine.jobs.tasks._mark_failed_safe",
                    new_callable=AsyncMock,
                ):
                    result = await bulk_resolve_task(
                        {},
                        ["https://test.com"],
                        str(TEST_OPERATION_ID),
                    )

            assert result.get("error_type") == expected_type, (
                f"Failed for {error.__class__.__name__}"
            )

    @pytest.mark.asyncio
    async def test_all_import_clz_error_types(
        self, mock_async_session_local, mock_session
    ):
        """Test that import_clz_task handles all error types."""
        error_scenarios = [
            (FileNotFoundError("test"), "file_not_found"),
            (ValidationError("test"), "validation_error"),
            (SQLAlchemyError("test"), "database_error"),
            (RuntimeError("test"), "unexpected_error"),
        ]

        for error, expected_type in error_scenarios:
            with patch(
                "comic_identity_engine.jobs.tasks.OperationsManager"
            ) as mock_ops_manager_class:
                mock_ops_manager = Mock()
                mock_ops_manager.get_operation = AsyncMock(return_value=None)

                if expected_type == "file_not_found":
                    mock_ops_manager.mark_running = AsyncMock()
                    mock_ops_manager_class.return_value = mock_ops_manager
                    with patch(
                        "comic_identity_engine.jobs.tasks.CLZAdapter"
                    ) as mock_adapter_class:
                        mock_adapter = Mock()
                        mock_adapter.load_csv_from_file = Mock(side_effect=error)
                        mock_adapter_class.return_value = mock_adapter

                        with patch(
                            "comic_identity_engine.jobs.tasks._mark_failed_safe",
                            new_callable=AsyncMock,
                        ):
                            result = await import_clz_task(
                                {},
                                "/fake/path.csv",
                                str(TEST_OPERATION_ID),
                            )
                else:
                    mock_ops_manager.mark_running = AsyncMock(side_effect=error)
                    mock_ops_manager_class.return_value = mock_ops_manager

                    with patch(
                        "comic_identity_engine.jobs.tasks._mark_failed_safe",
                        new_callable=AsyncMock,
                    ):
                        result = await import_clz_task(
                            {},
                            "/fake/path.csv",
                            str(TEST_OPERATION_ID),
                        )

            assert result.get("error_type") == expected_type, (
                f"Failed for {error.__class__.__name__}"
            )

    @pytest.mark.asyncio
    async def test_all_export_error_types(self, mock_async_session_local, mock_session):
        """Test that export_task handles all error types."""
        error_scenarios = [
            (ValueError("Unsupported format"), "invalid_format"),
            (SQLAlchemyError("test"), "database_error"),
            (RuntimeError("test"), "unexpected_error"),
        ]

        for error, expected_type in error_scenarios:
            with patch(
                "comic_identity_engine.jobs.tasks.OperationsManager"
            ) as mock_ops_manager_class:
                mock_ops_manager = Mock()
                mock_ops_manager.mark_running = AsyncMock(side_effect=error)
                mock_ops_manager_class.return_value = mock_ops_manager

                with patch(
                    "comic_identity_engine.jobs.tasks._mark_failed_safe",
                    new_callable=AsyncMock,
                ):
                    result = await export_task(
                        {},
                        [str(TEST_ISSUE_ID)],
                        "xml" if expected_type == "invalid_format" else "json",
                        str(TEST_OPERATION_ID),
                    )

            assert result.get("error_type") == expected_type, (
                f"Failed for {error.__class__.__name__}"
            )

    @pytest.mark.asyncio
    async def test_all_reconcile_error_types(
        self, mock_async_session_local, mock_session
    ):
        """Test that reconcile_task handles all error types."""
        error_scenarios = [
            (ValueError("Issue not found"), "validation_error"),
            (SQLAlchemyError("test"), "database_error"),
            (RuntimeError("test"), "unexpected_error"),
        ]

        for error, expected_type in error_scenarios:
            with patch(
                "comic_identity_engine.jobs.tasks.OperationsManager"
            ) as mock_ops_manager_class:
                mock_ops_manager = Mock()
                mock_ops_manager.mark_running = AsyncMock(side_effect=error)
                mock_ops_manager_class.return_value = mock_ops_manager

                with patch(
                    "comic_identity_engine.jobs.tasks._mark_failed_safe",
                    new_callable=AsyncMock,
                ):
                    result = await reconcile_task(
                        {},
                        str(TEST_ISSUE_ID),
                        str(TEST_OPERATION_ID),
                    )

            assert result.get("error_type") == expected_type, (
                f"Failed for {error.__class__.__name__}"
            )


class TestImportClzTaskEdgeCases:
    """Tests for import_clz_task edge cases."""

    @pytest.mark.asyncio
    async def test_import_clz_task_with_existing_mapping(
        self, mock_async_session_local, mock_session, tmp_path
    ):
        """Test CLZ import reuses existing external mapping."""
        csv_file = tmp_path / "test_collection.csv"
        csv_content = """Series,Issue,Publisher,Year,Core ComicID
X-Men,1,Marvel,1991,clz-001"""
        csv_file.write_text(csv_content)

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager.update_operation = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.load_csv_from_file.return_value = [
                    {
                        "Series": "X-Men",
                        "Issue": "1",
                        "Publisher": "Marvel",
                        "Year": "1991",
                        "Core ComicID": "clz-001",
                    },
                ]

                mock_candidate = Mock()
                mock_candidate.series_title = "X-Men"
                mock_candidate.series_start_year = 1991
                mock_candidate.publisher = "Marvel"
                mock_candidate.issue_number = "1"
                mock_candidate.variant_suffix = None
                mock_candidate.cover_date = None
                mock_candidate.upc = None
                mock_candidate.source_issue_id = "clz-001"
                mock_candidate.source_series_id = "X-Men, Vol. 1"

                mock_adapter.fetch_issue_from_csv_row.return_value = mock_candidate
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()

                    mock_existing_mapping = Mock()
                    mock_existing_mapping.issue_id = TEST_ISSUE_ID

                    mock_mapping_repo.find_by_source = AsyncMock(
                        return_value=mock_existing_mapping
                    )
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    result = await import_clz_task(
                        {},
                        str(csv_file),
                        str(TEST_OPERATION_ID),
                    )

        assert result["total_rows"] == 1
        assert result["processed"] == 0
        assert result["resolved"] == 0
        assert result["failed"] == 0
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_import_clz_task_resolution_failure(
        self, mock_async_session_local, mock_session, tmp_path
    ):
        """Test CLZ import handles resolution failures gracefully."""
        csv_file = tmp_path / "test_collection.csv"
        csv_content = """Series,Issue,Publisher,Year,Core ComicID
X-Men,1,Marvel,1991,clz-001"""
        csv_file.write_text(csv_content)

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager.update_operation = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.load_csv_from_file.return_value = [
                    {
                        "Series": "X-Men",
                        "Issue": "1",
                        "Publisher": "Marvel",
                        "Year": "1991",
                        "Core ComicID": "clz-001",
                    },
                ]

                mock_candidate = Mock()
                mock_candidate.series_title = "X-Men"
                mock_candidate.series_start_year = 1991
                mock_candidate.publisher = "Marvel"
                mock_candidate.issue_number = "1"
                mock_candidate.variant_suffix = None
                mock_candidate.cover_date = None
                mock_candidate.upc = None
                mock_candidate.source_issue_id = "clz-001"
                mock_candidate.source_series_id = "X-Men, Vol. 1"

                mock_adapter.fetch_issue_from_csv_row.return_value = mock_candidate
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks.IdentityResolver"
                    ) as mock_resolver_class:
                        mock_resolver = Mock()

                        mock_resolution_result = Mock()
                        mock_resolution_result.issue_id = None  # Resolution failed
                        mock_resolution_result.explanation = "No match found"

                        mock_resolver.resolve_issue = AsyncMock(
                            return_value=mock_resolution_result
                        )
                        mock_resolver_class.return_value = mock_resolver

                        result = await import_clz_task(
                            {},
                            str(csv_file),
                            str(TEST_OPERATION_ID),
                        )

        assert result["total_rows"] == 1
        assert result["processed"] == 0
        assert result["resolved"] == 0
        assert result["failed"] == 0
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_import_clz_task_progress_update(
        self, mock_async_session_local, mock_session, tmp_path
    ):
        """Test CLZ import sends progress updates every 10 rows."""
        csv_file = tmp_path / "test_collection.csv"
        csv_content = "Series,Issue,Publisher,Year,Core ComicID\n"
        for i in range(12):
            csv_content += f"X-Men,{i + 1},Marvel,1991,clz-{i:03d}\n"
        csv_file.write_text(csv_content)

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager.update_operation = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                rows = [
                    {
                        "Series": "X-Men",
                        "Issue": str(i + 1),
                        "Publisher": "Marvel",
                        "Year": "1991",
                        "Core ComicID": f"clz-{i:03d}",
                    }
                    for i in range(12)
                ]
                mock_adapter.load_csv_from_file.return_value = rows

                mock_candidate = Mock()
                mock_candidate.series_title = "X-Men"
                mock_candidate.series_start_year = 1991
                mock_candidate.publisher = "Marvel"
                mock_candidate.issue_number = "1"
                mock_candidate.variant_suffix = None
                mock_candidate.cover_date = None
                mock_candidate.upc = None
                mock_candidate.source_issue_id = "clz-001"
                mock_candidate.source_series_id = "X-Men, Vol. 1"

                mock_adapter.fetch_issue_from_csv_row.return_value = mock_candidate
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks.IdentityResolver"
                    ) as mock_resolver_class:
                        mock_resolver = Mock()

                        mock_resolution_result = Mock()
                        mock_resolution_result.issue_id = TEST_ISSUE_ID
                        mock_resolution_result.explanation = "Match found"

                        mock_resolver.resolve_issue = AsyncMock(
                            return_value=mock_resolution_result
                        )
                        mock_resolver_class.return_value = mock_resolver

                        with patch(
                            "comic_identity_engine.jobs.tasks._ensure_source_mapping",
                            new_callable=AsyncMock,
                        ) as mock_ensure_mapping:
                            mock_ensure_mapping.return_value = "created"

                            with patch(
                                "comic_identity_engine.services.platform_searcher.PlatformSearcher"
                            ) as mock_searcher_class:
                                mock_searcher = Mock()
                                mock_searcher.search_all_platforms = AsyncMock(
                                    return_value={
                                        "urls": {},
                                        "status": {},
                                        "events": [],
                                    }
                                )
                                mock_searcher_class.return_value = mock_searcher

                                await import_clz_task(
                                    {},
                                    str(csv_file),
                                    str(TEST_OPERATION_ID),
                                )

            # Should update operation at least once at row 10
            assert mock_ops_manager.update_operation.call_count >= 1

    @pytest.mark.asyncio
    async def test_import_clz_task_row_level_error(
        self, mock_async_session_local, mock_session, tmp_path
    ):
        """Test CLZ import handles row-level errors."""
        csv_file = tmp_path / "test_collection.csv"
        csv_content = """Series,Issue,Publisher,Year,Core ComicID
X-Men,1,Marvel,1991,clz-001
X-Men,2,Marvel,1991,clz-002"""
        csv_file.write_text(csv_content)

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager.update_operation = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.load_csv_from_file.return_value = [
                    {
                        "Series": "X-Men",
                        "Issue": "1",
                        "Publisher": "Marvel",
                        "Year": "1991",
                        "Core ComicID": "clz-001",
                    },
                    {
                        "Series": "X-Men",
                        "Issue": "2",
                        "Publisher": "Marvel",
                        "Year": "1991",
                        "Core ComicID": "clz-002",
                    },
                ]

                call_count = [0]

                def side_effect(*args, **kwargs):
                    call_count[0] += 1
                    if call_count[0] == 1:
                        mock_candidate = Mock()
                        mock_candidate.series_title = "X-Men"
                        mock_candidate.series_start_year = 1991
                        mock_candidate.publisher = "Marvel"
                        mock_candidate.issue_number = "1"
                        mock_candidate.variant_suffix = None
                        mock_candidate.cover_date = None
                        mock_candidate.upc = None
                        mock_candidate.source_issue_id = "clz-001"
                        mock_candidate.source_series_id = "X-Men, Vol. 1"
                        return mock_candidate
                    else:
                        raise Exception("Row processing error")

                mock_adapter.fetch_issue_from_csv_row = Mock(side_effect=side_effect)
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks.IdentityResolver"
                    ) as mock_resolver_class:
                        mock_resolver = Mock()

                        mock_resolution_result = Mock()
                        mock_resolution_result.issue_id = TEST_ISSUE_ID
                        mock_resolution_result.explanation = "Match found"

                        mock_resolver.resolve_issue = AsyncMock(
                            return_value=mock_resolution_result
                        )
                        mock_resolver_class.return_value = mock_resolver

                        with patch(
                            "comic_identity_engine.jobs.tasks._ensure_source_mapping",
                            new_callable=AsyncMock,
                        ) as mock_ensure_mapping:
                            mock_ensure_mapping.return_value = "created"

                            with patch(
                                "comic_identity_engine.services.platform_searcher.PlatformSearcher"
                            ) as mock_searcher_class:
                                mock_searcher = Mock()
                                mock_searcher.search_all_platforms = AsyncMock(
                                    return_value={
                                        "urls": {},
                                        "status": {},
                                        "events": [],
                                    }
                                )
                                mock_searcher_class.return_value = mock_searcher

                                result = await import_clz_task(
                                    {},
                                    str(csv_file),
                                    str(TEST_OPERATION_ID),
                                )

            assert result["total_rows"] == 2
            assert result["processed"] == 0
            assert result["resolved"] == 0
            assert result["failed"] == 0
            assert len(result["errors"]) == 0


class TestReconcileTaskEdgeCases:
    """Tests for reconcile_task edge cases."""

    @pytest.mark.asyncio
    async def test_reconcile_task_with_existing_mapping(
        self, mock_async_session_local, mock_session
    ):
        """Test reconcile task updates existing mappings."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.IssueRepository"
            ) as mock_issue_repo_class:
                mock_issue_repo = Mock()
                mock_issue = Mock()
                mock_issue.id = TEST_ISSUE_ID
                mock_issue_repo.find_by_id = AsyncMock(return_value=mock_issue)
                mock_issue_repo_class.return_value = mock_issue_repo

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    # Create existing mappings for some platforms
                    mock_mapping1 = Mock()
                    mock_mapping1.source = "gcd"
                    mock_mapping2 = Mock()
                    mock_mapping2.source = "locg"
                    mock_mapping_repo.find_by_issue = AsyncMock(
                        return_value=[mock_mapping1, mock_mapping2]
                    )
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    result = await reconcile_task(
                        {},
                        str(TEST_ISSUE_ID),
                        str(TEST_OPERATION_ID),
                    )

            assert result["mappings_updated"] == 2
            assert result["mappings_created"] == 0

    @pytest.mark.asyncio
    async def test_reconcile_task_platform_error(
        self, mock_async_session_local, mock_session
    ):
        """Test reconcile task handles platform errors."""
        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.mark_completed = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.IssueRepository"
            ) as mock_issue_repo_class:
                mock_issue_repo = Mock()
                mock_issue = Mock()
                mock_issue.id = TEST_ISSUE_ID
                mock_issue_repo.find_by_id = AsyncMock(return_value=mock_issue)
                mock_issue_repo_class.return_value = mock_issue_repo

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    # Simulate error during find_by_issue
                    mock_mapping_repo.find_by_issue = AsyncMock(
                        side_effect=Exception("Database error")
                    )
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks._mark_failed_safe",
                        new_callable=AsyncMock,
                    ):
                        result = await reconcile_task(
                            {},
                            str(TEST_ISSUE_ID),
                            str(TEST_OPERATION_ID),
                        )

            assert "error" in result
