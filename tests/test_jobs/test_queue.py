"""Tests for job queue management."""

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest
from arq.jobs import Job

from comic_identity_engine.jobs.queue import JobQueue


# Test constants
TEST_REDIS_URL = "redis://localhost:6379/0"
TEST_OPERATION_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
TEST_ISSUE_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440001")


@pytest.fixture
def mock_settings():
    """Mock settings with arq configuration."""
    settings = Mock()
    settings.arq.queue_url = TEST_REDIS_URL
    return settings


@pytest.fixture
def mock_redis_pool():
    """Mock Redis pool for testing."""
    pool = AsyncMock()
    mock_job = Mock(spec=Job)
    mock_job.job_id = "job-123"
    pool.enqueue_job = AsyncMock(return_value=mock_job)
    pool.close = AsyncMock()
    return pool


@pytest.fixture
def mock_arq_redis_settings():
    """Mock ArqRedisSettings."""
    settings = Mock()
    settings.host = "localhost"
    settings.port = 6379
    settings.database = 0
    return settings


class TestJobQueueInitialization:
    """Tests for JobQueue initialization."""

    def test_job_queue_initialization(self, mock_settings, mock_arq_redis_settings):
        """Test JobQueue initializes correctly."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings

                queue = JobQueue()

                assert queue._redis_pool is None
                assert queue._redis_settings == mock_arq_redis_settings


class TestJobQueueGetPool:
    """Tests for JobQueue._get_pool method."""

    @pytest.mark.asyncio
    async def test_get_pool_creates_new_pool(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test _get_pool creates pool on first call."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    pool = await queue._get_pool()

                    assert pool == mock_redis_pool
                    mock_create_pool.assert_called_once_with(mock_arq_redis_settings)
                    assert queue._redis_pool == mock_redis_pool

    @pytest.mark.asyncio
    async def test_get_pool_reuses_existing_pool(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test _get_pool reuses existing pool."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    # First call creates pool
                    pool1 = await queue._get_pool()
                    # Second call should reuse
                    pool2 = await queue._get_pool()

                    assert pool1 == pool2
                    mock_create_pool.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pool_connection_error(
        self, mock_settings, mock_arq_redis_settings
    ):
        """Test _get_pool raises ConnectionError on failure."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.side_effect = Exception("Connection refused")

                    queue = JobQueue()

                    with pytest.raises(
                        ConnectionError, match="Failed to connect to Redis"
                    ):
                        await queue._get_pool()


class TestEnqueueResolve:
    """Tests for enqueue_resolve method."""

    @pytest.mark.asyncio
    async def test_enqueue_resolve_success(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test successful enqueue_resolve."""
        test_url = "https://www.comics.org/issue/123/"

        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    job = await queue.enqueue_resolve(test_url, TEST_OPERATION_ID)

                    assert job.job_id == "job-123"
                    mock_redis_pool.enqueue_job.assert_called_once_with(
                        "resolve_identity_task",
                        url=test_url,
                        operation_id=str(TEST_OPERATION_ID),
                    )

    @pytest.mark.asyncio
    async def test_enqueue_resolve_connection_error(
        self, mock_settings, mock_arq_redis_settings
    ):
        """Test enqueue_resolve handles connection error."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.side_effect = ConnectionError("Connection refused")

                    queue = JobQueue()

                    with pytest.raises(ConnectionError):
                        await queue.enqueue_resolve(
                            "https://www.comics.org/issue/123/", TEST_OPERATION_ID
                        )


class TestEnqueueBulkResolve:
    """Tests for enqueue_bulk_resolve method."""

    @pytest.mark.asyncio
    async def test_enqueue_bulk_resolve_success(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test successful enqueue_bulk_resolve."""
        test_urls = [
            "https://www.comics.org/issue/123/",
            "https://www.comics.org/issue/124/",
        ]

        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    job = await queue.enqueue_bulk_resolve(test_urls, TEST_OPERATION_ID)

                    assert job.job_id == "job-123"
                    mock_redis_pool.enqueue_job.assert_called_once_with(
                        "bulk_resolve_task",
                        urls=test_urls,
                        operation_id=str(TEST_OPERATION_ID),
                    )

    @pytest.mark.asyncio
    async def test_enqueue_bulk_resolve_empty_list(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test enqueue_bulk_resolve with empty URL list."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    job = await queue.enqueue_bulk_resolve([], TEST_OPERATION_ID)

                    assert job.job_id == "job-123"
                    mock_redis_pool.enqueue_job.assert_called_once_with(
                        "bulk_resolve_task",
                        urls=[],
                        operation_id=str(TEST_OPERATION_ID),
                    )


class TestEnqueueImportClz:
    """Tests for enqueue_import_clz method."""

    @pytest.mark.asyncio
    async def test_enqueue_import_clz_success(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test successful enqueue_import_clz."""
        test_csv_path = "/path/to/collection.csv"

        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    job = await queue.enqueue_import_clz(
                        test_csv_path, TEST_OPERATION_ID
                    )

                    assert job.job_id == "job-123"
                    mock_redis_pool.enqueue_job.assert_called_once_with(
                        "import_clz_task",
                        csv_path=test_csv_path,
                        operation_id=str(TEST_OPERATION_ID),
                    )


class TestEnqueueExport:
    """Tests for enqueue_export method."""

    @pytest.mark.asyncio
    async def test_enqueue_export_success(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test successful enqueue_export with JSON format."""
        issue_ids = [TEST_ISSUE_ID, uuid.UUID("550e8400-e29b-41d4-a716-446655440002")]

        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    job = await queue.enqueue_export(
                        issue_ids, "json", TEST_OPERATION_ID
                    )

                    assert job.job_id == "job-123"
                    mock_redis_pool.enqueue_job.assert_called_once_with(
                        "export_task",
                        issue_ids=[str(issue_ids[0]), str(issue_ids[1])],
                        format="json",
                        operation_id=str(TEST_OPERATION_ID),
                    )

    @pytest.mark.asyncio
    async def test_enqueue_export_csv_format(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test enqueue_export with CSV format."""
        issue_ids = [TEST_ISSUE_ID]

        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    job = await queue.enqueue_export(
                        issue_ids, "csv", TEST_OPERATION_ID
                    )

                    assert job.job_id == "job-123"
                    mock_redis_pool.enqueue_job.assert_called_once_with(
                        "export_task",
                        issue_ids=[str(TEST_ISSUE_ID)],
                        format="csv",
                        operation_id=str(TEST_OPERATION_ID),
                    )

    @pytest.mark.asyncio
    async def test_enqueue_export_empty_list(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test enqueue_export with empty issue list."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    job = await queue.enqueue_export([], "json", TEST_OPERATION_ID)

                    assert job.job_id == "job-123"
                    mock_redis_pool.enqueue_job.assert_called_once_with(
                        "export_task",
                        issue_ids=[],
                        format="json",
                        operation_id=str(TEST_OPERATION_ID),
                    )


class TestEnqueueReconcile:
    """Tests for enqueue_reconcile method."""

    @pytest.mark.asyncio
    async def test_enqueue_reconcile_success(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test successful enqueue_reconcile."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    job = await queue.enqueue_reconcile(
                        TEST_ISSUE_ID, TEST_OPERATION_ID
                    )

                    assert job.job_id == "job-123"
                    mock_redis_pool.enqueue_job.assert_called_once_with(
                        "reconcile_task",
                        issue_id=str(TEST_ISSUE_ID),
                        operation_id=str(TEST_OPERATION_ID),
                    )


class TestJobQueueClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_close_with_open_pool(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test close with open pool."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    # Create pool first
                    await queue._get_pool()
                    # Now close
                    await queue.close()

                    mock_redis_pool.close.assert_called_once()
                    assert queue._redis_pool is None

    @pytest.mark.asyncio
    async def test_close_with_no_pool(self, mock_settings, mock_arq_redis_settings):
        """Test close with no pool (no-op)."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings

                queue = JobQueue()
                # Should not raise
                await queue.close()

                assert queue._redis_pool is None


class TestJobQueueContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_success(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test async context manager properly closes pool."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    async with JobQueue() as queue:
                        assert isinstance(queue, JobQueue)
                        # Create pool
                        await queue._get_pool()

                    # After exiting context, pool should be closed
                    mock_redis_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_exception(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Test context manager closes pool even on exception."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    with pytest.raises(ValueError, match="Test error"):
                        async with JobQueue() as queue:
                            await queue._get_pool()
                            raise ValueError("Test error")

                    mock_redis_pool.close.assert_called_once()


class TestTaskNames:
    """Tests to verify correct task names are used."""

    @pytest.mark.asyncio
    async def test_resolve_identity_task_name(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Verify correct task name for resolve_identity."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    await queue.enqueue_resolve("https://test.com", TEST_OPERATION_ID)

                    call_args = mock_redis_pool.enqueue_job.call_args
                    assert call_args[0][0] == "resolve_identity_task"

    @pytest.mark.asyncio
    async def test_bulk_resolve_task_name(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Verify correct task name for bulk_resolve."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    await queue.enqueue_bulk_resolve(
                        ["https://test.com"], TEST_OPERATION_ID
                    )

                    call_args = mock_redis_pool.enqueue_job.call_args
                    assert call_args[0][0] == "bulk_resolve_task"

    @pytest.mark.asyncio
    async def test_import_clz_task_name(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Verify correct task name for import_clz."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    await queue.enqueue_import_clz(
                        "/path/to/file.csv", TEST_OPERATION_ID
                    )

                    call_args = mock_redis_pool.enqueue_job.call_args
                    assert call_args[0][0] == "import_clz_task"

    @pytest.mark.asyncio
    async def test_export_task_name(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Verify correct task name for export."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    await queue.enqueue_export(
                        [TEST_ISSUE_ID], "json", TEST_OPERATION_ID
                    )

                    call_args = mock_redis_pool.enqueue_job.call_args
                    assert call_args[0][0] == "export_task"

    @pytest.mark.asyncio
    async def test_reconcile_task_name(
        self, mock_settings, mock_redis_pool, mock_arq_redis_settings
    ):
        """Verify correct task name for reconcile."""
        with patch(
            "comic_identity_engine.jobs.queue.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.queue.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.queue.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_redis_pool

                    queue = JobQueue()
                    await queue.enqueue_reconcile(TEST_ISSUE_ID, TEST_OPERATION_ID)

                    call_args = mock_redis_pool.enqueue_job.call_args
                    assert call_args[0][0] == "reconcile_task"
