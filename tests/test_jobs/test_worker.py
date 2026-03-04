"""Tests for arq worker configuration."""

from unittest.mock import AsyncMock, Mock, patch
import pytest
from arq.connections import RedisSettings as ArqRedisSettings
from arq.worker import Worker

from comic_identity_engine.jobs.worker import (
    WorkerSettings,
    create_redis_pool,
    create_worker,
    main,
    run_worker,
)


# Test constants
TEST_REDIS_URL = "redis://localhost:6379/0"
TEST_MAX_JOBS = 10
TEST_JOB_TIMEOUT = 300
TEST_KEEP_RESULT = 3600


@pytest.fixture
def mock_settings():
    """Mock settings with arq configuration."""
    settings = Mock()
    settings.arq.queue_url = TEST_REDIS_URL
    settings.arq.arq_max_jobs = TEST_MAX_JOBS
    settings.arq.arq_job_timeout = TEST_JOB_TIMEOUT
    settings.arq.arq_keep_result = TEST_KEEP_RESULT
    return settings


@pytest.fixture
def mock_arq_redis_settings():
    """Mock ArqRedisSettings.from_dsn return value."""
    redis_settings = Mock(spec=ArqRedisSettings)
    redis_settings.host = "localhost"
    redis_settings.port = 6379
    redis_settings.database = 0
    return redis_settings


class TestCreateRedisPool:
    """Tests for create_redis_pool function."""

    @pytest.mark.asyncio
    async def test_create_redis_pool_success(
        self, mock_settings, mock_arq_redis_settings
    ):
        """Test successful Redis pool creation."""
        mock_pool = AsyncMock()

        with patch(
            "comic_identity_engine.jobs.worker.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.worker.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.worker.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.return_value = mock_pool

                    result = await create_redis_pool()

                    assert result == mock_pool
                    mock_get_settings.assert_called_once()
                    mock_from_dsn.assert_called_once_with(TEST_REDIS_URL)
                    mock_create_pool.assert_called_once_with(mock_arq_redis_settings)

    @pytest.mark.asyncio
    async def test_create_redis_pool_connection_error(self, mock_settings):
        """Test Redis pool creation with connection error."""
        with patch(
            "comic_identity_engine.jobs.worker.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.worker.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings
                with patch(
                    "comic_identity_engine.jobs.worker.create_pool"
                ) as mock_create_pool:
                    mock_create_pool.side_effect = ConnectionError("Connection refused")

                    with pytest.raises(ConnectionError, match="Connection refused"):
                        await create_redis_pool()


class TestWorkerSettings:
    """Tests for WorkerSettings class."""

    def test_worker_settings_class_attributes(
        self, mock_settings, mock_arq_redis_settings
    ):
        """Test WorkerSettings class-level attributes."""
        with patch(
            "comic_identity_engine.jobs.worker.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings
            with patch(
                "comic_identity_engine.jobs.worker.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings

                # Access class attributes (will trigger get_settings via class definition)
                # Note: WorkerSettings now uses class-level attributes
                assert WorkerSettings.max_jobs == TEST_MAX_JOBS
                assert WorkerSettings.job_timeout == TEST_JOB_TIMEOUT
                assert WorkerSettings.keep_result == TEST_KEEP_RESULT
                assert isinstance(WorkerSettings.functions, list)
                assert len(WorkerSettings.functions) == 5

    def test_worker_settings_functions_list(self):
        """Test WorkerSettings has correct task functions."""
        # Verify the functions list contains the expected tasks
        from comic_identity_engine.jobs.tasks import (
            bulk_resolve_task,
            export_task,
            import_clz_task,
            reconcile_task,
            resolve_identity_task,
        )

        expected_functions = [
            resolve_identity_task,
            bulk_resolve_task,
            import_clz_task,
            export_task,
            reconcile_task,
        ]
        assert WorkerSettings.functions == expected_functions


class TestCreateWorker:
    """Tests for create_worker function."""

    def test_create_worker_uses_class_settings(self, mock_arq_redis_settings):
        """Test worker creation uses WorkerSettings class attributes."""
        with patch("comic_identity_engine.jobs.worker.Worker") as mock_worker_class:
            mock_worker = Mock(spec=Worker)
            mock_worker_class.return_value = mock_worker

            worker = create_worker()

            assert worker == mock_worker
            mock_worker_class.assert_called_once_with(
                redis_settings=WorkerSettings.redis_settings,
                max_jobs=WorkerSettings.max_jobs,
                job_timeout=WorkerSettings.job_timeout,
                keep_result=WorkerSettings.keep_result,
                functions=WorkerSettings.functions,
            )


class TestRunWorker:
    """Tests for run_worker function."""

    @pytest.mark.asyncio
    async def test_run_worker_success(self, mock_arq_redis_settings):
        """Test successful worker execution."""
        mock_worker = Mock(spec=Worker)
        mock_worker.async_run = AsyncMock()

        with patch(
            "comic_identity_engine.jobs.worker.create_worker",
            return_value=mock_worker,
        ):
            with patch("comic_identity_engine.jobs.worker.logger") as mock_logger:
                await run_worker()

                mock_worker.async_run.assert_called_once()
                mock_logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_worker_keyboard_interrupt(self, mock_arq_redis_settings):
        """Test worker handles keyboard interrupt."""
        mock_worker = Mock(spec=Worker)
        mock_worker.async_run = AsyncMock(side_effect=KeyboardInterrupt())

        with patch(
            "comic_identity_engine.jobs.worker.create_worker",
            return_value=mock_worker,
        ):
            # KeyboardInterrupt should propagate from async_run
            with pytest.raises(KeyboardInterrupt):
                await run_worker()


class TestMain:
    """Tests for main function."""

    def test_main_success(self):
        """Test main function runs successfully."""
        with patch("comic_identity_engine.jobs.worker.asyncio.run") as mock_run:
            with patch("structlog.get_logger") as mock_get_logger:
                mock_logger = Mock()
                mock_get_logger.return_value = mock_logger

                main()

                mock_run.assert_called_once()

    def test_main_keyboard_interrupt(self):
        """Test main handles keyboard interrupt."""
        with patch("comic_identity_engine.jobs.worker.asyncio.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()

            with patch("comic_identity_engine.jobs.worker.logger") as mock_logger:
                main()

                mock_logger.info.assert_called_with("Worker stopped by user")

    def test_main_exception(self):
        """Test main handles unexpected exceptions."""
        error = RuntimeError("Worker failed")

        with patch("comic_identity_engine.jobs.worker.asyncio.run") as mock_run:
            mock_run.side_effect = error

            with patch("comic_identity_engine.jobs.worker.logger") as mock_logger:
                with pytest.raises(RuntimeError, match="Worker failed"):
                    main()

                mock_logger.error.assert_called_once()
