"""Integration tests for CLZ import with various CSV sizes.

These tests verify CLZ import works correctly with small and medium CSV files
using the new task-based parallel processing architecture.
"""

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

from comic_identity_engine.jobs.tasks import import_clz_task, resolve_clz_row_task


TEST_OPERATION_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def mock_async_session_local():
    """Mock AsyncSessionLocal context manager."""
    session = AsyncMock()
    with patch("comic_identity_engine.jobs.tasks.AsyncSessionLocal") as mock:
        mock.return_value.__aenter__ = AsyncMock(return_value=session)
        mock.return_value.__aexit__ = AsyncMock(return_value=False)
        yield session


@pytest.mark.asyncio
class TestClzImportSmall:
    """Integration tests for small CSV import (10 rows) using task-based processing."""

    async def test_import_small_csv_enqueues_tasks(
        self, mock_async_session_local, tmp_path
    ):
        """Test that import_clz_task enqueues series bulk tasks."""
        csv_file = tmp_path / "test_small.csv"
        csv_content = """Series,Issue,Publisher,Year,Core ComicID,Cover Date,Barcode
X-Men,1,Marvel,1991,clz-001,July 1991,123456789012
X-Men,2,Marvel,1991,clz-002,August 1991,234567890123
X-Men,3,Marvel,1991,clz-003,September 1991,345678901234
X-Men,4,Marvel,1991,clz-004,October 1991,456789012345
X-Men,5,Marvel,1991,clz-005,November 1991,567890123456
X-Men,6,Marvel,1991,clz-006,December 1991,678901234567
X-Men,7,Marvel,1992,clz-007,January 1992,789012345678
X-Men,8,Marvel,1992,clz-008,February 1992,890123456789
X-Men,9,Marvel,1992,clz-009,March 1992,901234567890
X-Men,10,Marvel,1992,clz-010,April 1992,012345678901"""
        csv_file.write_text(csv_content)

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.update_operation = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.load_csv_from_file.return_value = [
                    {
                        "Series": "X-Men",
                        "Issue": str(i),
                        "Publisher": "Marvel",
                        "Year": "1991" if i <= 6 else "1992",
                        "Core ComicID": f"clz-{i:03d}",
                        "Cover Date": f"{['July', 'August', 'September', 'October', 'November', 'December', 'January', 'February', 'March', 'April'][i - 1]} {1991 if i <= 6 else 1992}",
                        "Barcode": f"{str(123456789012 + i - 1)[-12:]}",
                    }
                    for i in range(1, 11)
                ]
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.queue.JobQueue"
                ) as mock_queue_class:
                    mock_queue = Mock()
                    mock_job = Mock()
                    mock_job.job_id = "test-job"
                    mock_queue.enqueue_series_bulk = AsyncMock(return_value=mock_job)

                    mock_queue.close = Mock()
                    mock_queue.close.return_value = None

                    mock_queue_class.return_value = mock_queue

                    result = await import_clz_task(
                        {},
                        str(csv_file),
                        str(TEST_OPERATION_ID),
                    )

        assert result["total_rows"] == 10
        assert result["processed"] == 0
        assert "summary" in result
        assert (
            "Enqueued 10 CLZ rows across 2 series for bulk processing"
            in result["summary"]
        )
        assert (
            mock_queue.enqueue_series_bulk.call_count == 2
        )  # 2 series groups (1991 and 1992)
        mock_ops_manager.update_operation.assert_called_once()


@pytest.mark.asyncio
class TestResolveClzRow:
    """Integration tests for single CLZ row resolution task."""

    async def test_resolve_clz_row_success(self, mock_async_session_local):
        """Test successful resolution of a single CLZ row."""
        row_data = {
            "Series": "X-Men",
            "Issue": "1",
            "Publisher": "Marvel",
            "Year": "1991",
            "Core ComicID": "clz-001",
            "Cover Date": "July 1991",
            "Barcode": "123456789012",
        }

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.update_operation = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_candidate = Mock()
                mock_candidate.series_title = "X-Men"
                mock_candidate.series_start_year = 1991
                mock_candidate.publisher = "Marvel"
                mock_candidate.issue_number = "1"
                mock_candidate.variant_suffix = None
                mock_candidate.cover_date = None
                mock_candidate.upc = "123456789012"
                mock_candidate.source_issue_id = "clz-001"
                mock_candidate.source_series_id = "X-Men"
                mock_adapter.fetch_issue_from_csv_row.return_value = mock_candidate
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
                ) as mock_mapping_repo_class:
                    mock_mapping_repo = Mock()
                    mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
                    mock_mapping_repo.find_by_issue = AsyncMock(return_value=[])
                    mock_mapping_repo.create_mapping = AsyncMock()
                    mock_mapping_repo_class.return_value = mock_mapping_repo

                    with patch(
                        "comic_identity_engine.jobs.tasks.IdentityResolver"
                    ) as mock_resolver_class:
                        mock_resolver = Mock()
                        mock_result = Mock()
                        mock_result.issue_id = uuid.uuid4()
                        mock_result.explanation = "Match found"
                        mock_resolver.resolve_issue = AsyncMock(
                            return_value=mock_result
                        )
                        mock_resolver_class.return_value = mock_resolver

                        with patch(
                            "comic_identity_engine.jobs.tasks._ensure_source_mapping",
                            new_callable=AsyncMock,
                            return_value="created",
                        ):
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

                                result = await resolve_clz_row_task(
                                    {},
                                    row_data,
                                    1,
                                    str(TEST_OPERATION_ID),
                                )

        assert result["resolved"] is False  # CLZ only, no cross-platform mappings
        assert result["completion_stage"] == "clz_only"
        assert result["row_index"] == 1
        assert result["source_issue_id"] == "clz-001"
        assert "issue_id" in result
        assert result["existing_mapping"] is False

    async def test_resolve_clz_row_existing_mapping(self, mock_async_session_local):
        """Test row resolution with existing CLZ mapping."""
        row_data = {
            "Series": "X-Men",
            "Issue": "1",
            "Publisher": "Marvel",
            "Year": "1991",
            "Core ComicID": "clz-001",
        }

        existing_issue_id = uuid.uuid4()

        with patch(
            "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
        ) as mock_mapping_repo_class:
            mock_mapping_repo = Mock()
            mock_existing_mapping = Mock()
            mock_existing_mapping.issue_id = existing_issue_id
            mock_mapping_repo.find_by_source = AsyncMock(
                return_value=mock_existing_mapping
            )
            mock_mapping_repo.find_by_issue = AsyncMock(return_value=[])
            mock_mapping_repo_class.return_value = mock_mapping_repo

            result = await resolve_clz_row_task(
                {},
                row_data,
                1,
                str(TEST_OPERATION_ID),
            )

        assert result["resolved"] is False  # CLZ only, no cross-platform mappings
        assert result["completion_stage"] == "clz_only"
        assert result["platform_coverage"] == 0
        assert result["row_index"] == 1
        assert result["source_issue_id"] == "clz-001"
        assert result["issue_id"] == str(existing_issue_id)
        assert result["existing_mapping"] is True

    async def test_resolve_clz_row_platforms_only_phase(self, mock_async_session_local):
        """Test platforms_only phase refreshes missing platform mappings."""
        row_data = {
            "Series": "X-Men",
            "Issue": "1",
            "Publisher": "Marvel",
            "Year": "1991",
            "Core ComicID": "clz-001",
        }

        existing_issue_id = uuid.uuid4()

        with patch(
            "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
        ) as mock_mapping_repo_class:
            mock_mapping_repo = Mock()

            mock_existing_mapping = Mock()
            mock_existing_mapping.issue_id = existing_issue_id
            mock_mapping_repo.find_by_source = AsyncMock(
                return_value=mock_existing_mapping
            )

            existing_gcd_mapping = Mock()
            existing_gcd_mapping.source = "gcd"
            existing_gcd_mapping.source_issue_id = "12345"
            existing_gcd_mapping.source_series_id = "x-men"
            mock_mapping_repo.find_by_issue = AsyncMock(
                return_value=[mock_existing_mapping, existing_gcd_mapping]
            )

            mock_mapping_repo.create_mapping = AsyncMock()
            mock_mapping_repo_class.return_value = mock_mapping_repo

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_candidate = Mock()
                mock_candidate.series_title = "X-Men"
                mock_candidate.series_start_year = 1991
                mock_candidate.publisher = "Marvel"
                mock_candidate.issue_number = "1"
                mock_candidate.source_issue_id = "clz-001"
                mock_adapter.fetch_issue_from_csv_row.return_value = mock_candidate
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.services.platform_searcher.PlatformSearcher"
                ) as mock_searcher_class:
                    mock_searcher = Mock()
                    mock_searcher.search_all_platforms = AsyncMock(
                        return_value={
                            "urls": {
                                "locg": "https://www.comicbookregistry.com/issues/99999/"
                            },
                            "status": {"locg": "found"},
                            "events": [],
                        }
                    )
                    mock_searcher_class.return_value = mock_searcher

                    with patch(
                        "comic_identity_engine.jobs.tasks._ensure_source_mapping",
                        new_callable=AsyncMock,
                        return_value="created",
                    ):
                        with patch(
                            "comic_identity_engine.services.url_parser.parse_url"
                        ) as mock_parse_url:
                            mock_parsed = Mock()
                            mock_parsed.source_issue_id = "99999"
                            mock_parse_url.return_value = mock_parsed

                            with patch(
                                "comic_identity_engine.jobs.tasks._record_clz_row_result",
                                new_callable=AsyncMock,
                            ):
                                result = await resolve_clz_row_task(
                                    {},
                                    row_data,
                                    1,
                                    str(TEST_OPERATION_ID),
                                    phase="platforms_only",
                                )

        assert result["resolved"] is True
        assert result["row_index"] == 1
        assert result["source_issue_id"] == "clz-001"
        assert result["issue_id"] == str(existing_issue_id)
        assert result["existing_mapping"] is True
        assert result["refreshed"] is True
        assert "Refreshed missing platform mappings" in result["match_explanation"]

    async def test_resolve_clz_row_platforms_only_all_mapped(
        self, mock_async_session_local
    ):
        """Test platforms_only phase skips when all platforms already mapped."""
        row_data = {
            "Series": "X-Men",
            "Issue": "1",
            "Publisher": "Marvel",
            "Year": "1991",
            "Core ComicID": "clz-001",
        }

        existing_issue_id = uuid.uuid4()

        with patch(
            "comic_identity_engine.jobs.tasks.ExternalMappingRepository"
        ) as mock_mapping_repo_class:
            mock_mapping_repo = Mock()

            mock_existing_mapping = Mock()
            mock_existing_mapping.issue_id = existing_issue_id
            mock_existing_mapping.source = "clz"
            mock_mapping_repo.find_by_source = AsyncMock(
                return_value=mock_existing_mapping
            )

            all_platform_mappings = [mock_existing_mapping]
            for platform, ext_id in [
                ("gcd", "12345"),
                ("locg", "99999"),
                ("ccl", "aaa"),
                ("aa", "bbb"),
                ("cpg", "ccc"),
                ("hip", "ddd"),
            ]:
                m = Mock()
                m.source = platform
                m.source_issue_id = ext_id
                m.source_series_id = f"{platform}-series"
                all_platform_mappings.append(m)

            mock_mapping_repo.find_by_issue = AsyncMock(
                return_value=all_platform_mappings
            )
            mock_mapping_repo_class.return_value = mock_mapping_repo

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_candidate = Mock()
                mock_candidate.series_title = "X-Men"
                mock_candidate.series_start_year = 1991
                mock_candidate.publisher = "Marvel"
                mock_candidate.issue_number = "1"
                mock_candidate.source_issue_id = "clz-001"
                mock_adapter.fetch_issue_from_csv_row.return_value = mock_candidate
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.tasks._record_clz_row_result",
                    new_callable=AsyncMock,
                ):
                    result = await resolve_clz_row_task(
                        {},
                        row_data,
                        1,
                        str(TEST_OPERATION_ID),
                        phase="platforms_only",
                    )

        assert result["resolved"] is True
        assert result["skipped"] is True
        assert result["reason"] == "all_platforms_mapped"
        assert result["cross_platform_found"] == 6


@pytest.mark.asyncio
class TestClzImportMedium:
    """Integration tests for medium CSV import (100 rows)."""

    async def test_import_medium_csv_enqueues_tasks(
        self, mock_async_session_local, tmp_path
    ):
        """Test that medium CSV import enqueues series bulk tasks."""
        csv_file = tmp_path / "test_medium.csv"

        rows = ["Series,Issue,Publisher,Year,Core ComicID"]
        for i in range(1, 101):
            rows.append(f"X-Men,{i},Marvel,1991,clz-{i:03d}")
        csv_content = "\n".join(rows)
        csv_file.write_text(csv_content)

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=None)
            mock_ops_manager.mark_running = AsyncMock()
            mock_ops_manager.update_operation = AsyncMock()
            mock_ops_manager_class.return_value = mock_ops_manager

            with patch(
                "comic_identity_engine.jobs.tasks.CLZAdapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.load_csv_from_file.return_value = [
                    {
                        "Series": "X-Men",
                        "Issue": str(i),
                        "Publisher": "Marvel",
                        "Year": "1991",
                        "Core ComicID": f"clz-{i:03d}",
                    }
                    for i in range(1, 101)
                ]
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.queue.JobQueue"
                ) as mock_queue_class:
                    mock_queue = Mock()
                    mock_job = Mock()
                    mock_job.job_id = "test-job"
                    mock_queue.enqueue_series_bulk = AsyncMock(return_value=mock_job)

                    mock_queue.close = Mock()
                    mock_queue.close.return_value = None

                    mock_queue_class.return_value = mock_queue

                    result = await import_clz_task(
                        {},
                        str(csv_file),
                        str(TEST_OPERATION_ID),
                    )

        assert result["total_rows"] == 100
        assert result["processed"] == 0
        assert (
            "Enqueued 100 CLZ rows across 1 series for bulk processing"
            in result["summary"]
        )
        assert mock_queue.enqueue_series_bulk.call_count == 1  # All rows same series
        mock_ops_manager.update_operation.assert_called_once()

    async def test_import_retry_failed_only_enqueues_only_missing_rows(
        self, mock_async_session_local, tmp_path
    ):
        """Retry-failed-only state should preserve resolved rows and requeue only missing work."""
        csv_file = tmp_path / "test_retry.csv"
        csv_content = """Series,Issue,Publisher,Year,Core ComicID
X-Men,1,Marvel,1991,clz-001
X-Men,2,Marvel,1991,clz-002
X-Men,3,Marvel,1991,clz-003"""
        csv_file.write_text(csv_content)

        existing_operation = Mock()
        existing_operation.result = {
            "total_rows": 3,
            "row_manifest": [
                {
                    "row_index": 1,
                    "source_issue_id": "clz-001",
                    "row_key": "clz-001:1",
                },
                {
                    "row_index": 2,
                    "source_issue_id": "clz-002",
                    "row_key": "clz-002:2",
                },
                {
                    "row_index": 3,
                    "source_issue_id": "clz-003",
                    "row_key": "clz-003:3",
                },
            ],
            "row_results": {
                "clz-001:1": {
                    "row_index": 1,
                    "row_key": "clz-001:1",
                    "source_issue_id": "clz-001",
                    "resolved": True,
                }
            },
            "processed": 1,
            "resolved": 1,
            "failed": 0,
            "errors": [],
            "progress": 1 / 3,
        }

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=existing_operation)
            mock_ops_manager.mark_running = AsyncMock()
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
                    {
                        "Series": "X-Men",
                        "Issue": "3",
                        "Publisher": "Marvel",
                        "Year": "1991",
                        "Core ComicID": "clz-003",
                    },
                ]
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.queue.JobQueue"
                ) as mock_queue_class:
                    mock_queue = Mock()
                    mock_job = Mock()
                    mock_job.job_id = "test-job"
                    mock_queue.enqueue_series_bulk = AsyncMock(return_value=mock_job)

                    mock_queue.close = Mock()
                    mock_queue.close.return_value = None

                    mock_queue_class.return_value = mock_queue

                    result = await import_clz_task(
                        {},
                        str(csv_file),
                        str(TEST_OPERATION_ID),
                    )

        # Row 1 is already processed, so only rows 2-3 should be enqueued
        assert result["processed"] == 1
        assert result["resolved"] == 1
        assert result["active_row_count"] == 0
        assert result["pending_row_count"] == 2
        assert (
            "Enqueued 2 CLZ rows across 1 series for bulk processing"
            in result["summary"]
        )
        assert (
            mock_queue.enqueue_series_bulk.await_count == 1
        )  # 1 series group for remaining rows

    async def test_import_resume_clears_stale_active_rows_and_requeues_remaining_rows(
        self, mock_async_session_local, tmp_path
    ):
        """Resuming a failed import should clear stale active-row state before requeueing."""
        csv_file = tmp_path / "test_resume.csv"
        csv_content = """Series,Issue,Publisher,Year,Core ComicID
X-Men,1,Marvel,1991,clz-001
X-Men,2,Marvel,1991,clz-002
X-Men,3,Marvel,1991,clz-003"""
        csv_file.write_text(csv_content)

        existing_operation = Mock()
        existing_operation.result = {
            "total_rows": 3,
            "row_manifest": [
                {
                    "row_index": 1,
                    "source_issue_id": "clz-001",
                    "row_key": "clz-001:1",
                },
                {
                    "row_index": 2,
                    "source_issue_id": "clz-002",
                    "row_key": "clz-002:2",
                },
                {
                    "row_index": 3,
                    "source_issue_id": "clz-003",
                    "row_key": "clz-003:3",
                },
            ],
            "row_results": {
                "clz-001:1": {
                    "row_index": 1,
                    "row_key": "clz-001:1",
                    "source_issue_id": "clz-001",
                    "resolved": True,
                }
            },
            "processed": 1,
            "resolved": 1,
            "failed": 0,
            "errors": [],
            "progress": 1 / 3,
            "resume_count": 1,
            "retry_failed_count": 0,
            "active_row_keys": ["clz-002:2"],
            "active_row_count": 1,
            "pending_row_count": 1,
        }

        with patch(
            "comic_identity_engine.jobs.tasks.OperationsManager"
        ) as mock_ops_manager_class:
            mock_ops_manager = Mock()
            mock_ops_manager.get_operation = AsyncMock(return_value=existing_operation)
            mock_ops_manager.mark_running = AsyncMock()
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
                    {
                        "Series": "X-Men",
                        "Issue": "3",
                        "Publisher": "Marvel",
                        "Year": "1991",
                        "Core ComicID": "clz-003",
                    },
                ]
                mock_adapter_class.return_value = mock_adapter

                with patch(
                    "comic_identity_engine.jobs.queue.JobQueue"
                ) as mock_queue_class:
                    mock_queue = Mock()
                    mock_job = Mock()
                    mock_job.job_id = "test-job"
                    mock_queue.enqueue_series_bulk = AsyncMock(return_value=mock_job)

                    mock_queue.close = Mock()
                    mock_queue.close.return_value = None

                    mock_queue_class.return_value = mock_queue

                    result = await import_clz_task(
                        {},
                        str(csv_file),
                        str(TEST_OPERATION_ID),
                    )

        # Row 1 already processed, rows 2-3 need to be re-enqueued
        assert result["processed"] == 1
        assert result["resolved"] == 1
        assert result["active_row_count"] == 0
        assert result["pending_row_count"] == 2
        assert (
            "Enqueued 2 CLZ rows across 1 series for bulk processing"
            in result["summary"]
        )
        assert (
            mock_queue.enqueue_series_bulk.await_count == 1
        )  # 1 series group for remaining rows

        persisted_result = mock_ops_manager.update_operation.await_args.kwargs["result"]
        assert persisted_result["active_row_count"] == 0
        assert persisted_result["pending_row_count"] == 2
