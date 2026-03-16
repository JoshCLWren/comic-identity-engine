"""Tests for arq worker configuration."""

import logging
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from arq.connections import RedisSettings as ArqRedisSettings
from arq.worker import Worker

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/test_db")

from comic_identity_engine.jobs.worker import (  # noqa: E402
    WorkerSettings,
    _configure_logging,
    _on_worker_shutdown,
    _on_worker_startup,
    cap_worker_max_jobs,
    create_redis_pool,
    create_worker,
    main,
    run_worker,
)


TEST_REDIS_URL = "redis://localhost:6379/0"
TEST_QUEUE_NAME = "cie:test:queue"
TEST_MAX_JOBS = 10
TEST_JOB_TIMEOUT = 300
TEST_KEEP_RESULT = 3600


@pytest.fixture
def mock_settings():
    """Mock settings with arq configuration."""
    settings = Mock()
    settings.arq.queue_url = TEST_REDIS_URL
    settings.arq.arq_queue_name = TEST_QUEUE_NAME
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


class TestWorkerConcurrencyCap:
    """Tests for worker concurrency capping."""

    def test_cap_worker_max_jobs_caps_to_db_pool_capacity(self):
        """Configured concurrency should not exceed DB pool capacity."""
        assert cap_worker_max_jobs(configured_max_jobs=100, db_pool_capacity=30) == 30

    def test_cap_worker_max_jobs_respects_lower_worker_limit(self):
        """Configured concurrency below the cap should be preserved."""
        assert cap_worker_max_jobs(configured_max_jobs=12, db_pool_capacity=30) == 12


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
                    mock_create_pool.assert_called_once_with(
                        mock_arq_redis_settings,
                        default_queue_name=TEST_QUEUE_NAME,
                    )

    @pytest.mark.asyncio
    async def test_create_redis_pool_connection_error(
        self, mock_settings, mock_arq_redis_settings
    ):
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

    def test_worker_settings_class_attributes(self):
        """Test WorkerSettings exposes the expected class-level attributes."""
        assert isinstance(WorkerSettings.queue_name, str)
        assert WorkerSettings.queue_name
        assert isinstance(WorkerSettings.configured_max_jobs, int)
        assert isinstance(WorkerSettings.db_pool_capacity, int)
        assert isinstance(WorkerSettings.max_jobs, int)
        assert WorkerSettings.max_jobs == cap_worker_max_jobs(
            WorkerSettings.configured_max_jobs,
            WorkerSettings.db_pool_capacity,
        )
        assert WorkerSettings.max_jobs <= WorkerSettings.db_pool_capacity
        assert isinstance(WorkerSettings.job_timeout, int)
        assert isinstance(WorkerSettings.keep_result, int)
        assert isinstance(WorkerSettings.functions, list)
        assert len(WorkerSettings.functions) == 8

    def test_worker_settings_functions_list(self):
        """Test WorkerSettings has correct task functions."""
        from comic_identity_engine.jobs.tasks import (
            _process_series_bulk_task,
            bulk_resolve_task,
            export_task,
            http_request_task,
            import_clz_task,
            reconcile_task,
            resolve_clz_row_task,
            resolve_identity_task,
        )

        expected_functions = [
            resolve_identity_task,
            bulk_resolve_task,
            import_clz_task,
            _process_series_bulk_task,
            resolve_clz_row_task,
            export_task,
            reconcile_task,
            http_request_task,
        ]
        assert WorkerSettings.functions == expected_functions


class TestCreateWorker:
    """Tests for create_worker function."""

    def test_create_worker_uses_class_settings(self):
        """Test worker creation uses WorkerSettings class attributes."""
        with patch("comic_identity_engine.jobs.worker.Worker") as mock_worker_class:
            mock_worker = Mock(spec=Worker)
            mock_worker_class.return_value = mock_worker

            worker = create_worker()

            assert worker == mock_worker
            mock_worker_class.assert_called_once_with(
                queue_name=WorkerSettings.queue_name,
                redis_settings=WorkerSettings.redis_settings,
                max_jobs=WorkerSettings.max_jobs,
                job_timeout=WorkerSettings.job_timeout,
                keep_result=WorkerSettings.keep_result,
                functions=WorkerSettings.functions,
                on_startup=_on_worker_startup,
                on_shutdown=_on_worker_shutdown,
            )

    @pytest.mark.asyncio
    async def test_worker_startup_logs_success(self):
        """The startup hook should emit the effective concurrency cap."""
        with patch("comic_identity_engine.jobs.worker.logger") as mock_logger:
            await _on_worker_startup({})

            mock_logger.info.assert_called_once_with(
                "Worker started successfully",
                queue_name=WorkerSettings.queue_name,
                max_jobs=WorkerSettings.max_jobs,
                configured_max_jobs=WorkerSettings.configured_max_jobs,
                db_pool_capacity=WorkerSettings.db_pool_capacity,
                job_timeout=WorkerSettings.job_timeout,
                functions_count=len(WorkerSettings.functions),
                redis_host=WorkerSettings.redis_settings.host,
            )


class TestRunWorker:
    """Tests for run_worker function."""

    def test_run_worker_success(self):
        """Test successful worker execution."""
        mock_worker = Mock(spec=Worker)
        mock_worker.run = Mock()

        with patch(
            "comic_identity_engine.jobs.worker.create_worker",
            return_value=mock_worker,
        ):
            with patch("comic_identity_engine.jobs.worker.logger") as mock_logger:
                run_worker()

                mock_worker.run.assert_called_once()
                mock_logger.info.assert_any_call(
                    "Starting arq worker",
                    redis_url=WorkerSettings.redis_settings.host,
                    queue_name=WorkerSettings.queue_name,
                    max_jobs=WorkerSettings.max_jobs,
                    configured_max_jobs=WorkerSettings.configured_max_jobs,
                    db_pool_capacity=WorkerSettings.db_pool_capacity,
                    job_timeout=WorkerSettings.job_timeout,
                    functions_count=len(WorkerSettings.functions),
                )

    def test_run_worker_keyboard_interrupt(self):
        """Test worker handles keyboard interrupt."""
        mock_worker = Mock(spec=Worker)
        mock_worker.run = Mock(side_effect=KeyboardInterrupt())

        with patch(
            "comic_identity_engine.jobs.worker.create_worker",
            return_value=mock_worker,
        ):
            with pytest.raises(KeyboardInterrupt):
                run_worker()


class TestMain:
    """Tests for main function."""

    def test_main_success(self):
        """Test main function runs successfully."""
        with patch("comic_identity_engine.jobs.worker.run_worker") as mock_run_worker:
            main()
            mock_run_worker.assert_called_once()

    def test_main_keyboard_interrupt(self):
        """Test main handles keyboard interrupt."""
        with patch("comic_identity_engine.jobs.worker.run_worker") as mock_run_worker:
            mock_run_worker.side_effect = KeyboardInterrupt()

            with patch("comic_identity_engine.jobs.worker.logger") as mock_logger:
                main()

                mock_logger.info.assert_called_with("Worker stopped by user")

    def test_main_exception(self):
        """Test main handles unexpected exceptions."""
        error = RuntimeError("Worker failed")

        with patch("comic_identity_engine.jobs.worker.run_worker") as mock_run_worker:
            mock_run_worker.side_effect = error

            with patch("comic_identity_engine.jobs.worker.logger") as mock_logger:
                with pytest.raises(RuntimeError, match="Worker failed"):
                    main()

                mock_logger.error.assert_called_once_with(
                    "Worker failed",
                    error=str(error),
                )


class TestLoggingConfiguration:
    """Tests for worker logging bootstrap."""

    def test_configure_logging_initializes_stdlib_handler(self):
        """Worker logs should be visible on stdout at info level."""
        with patch(
            "comic_identity_engine.jobs.worker.logging.basicConfig"
        ) as mock_basic:
            _configure_logging()

            mock_basic.assert_called_once_with(level=logging.INFO, format="%(message)s")
