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

    def test_worker_settings_initialization(self, mock_settings):
        """Test WorkerSettings initialization with mocked settings."""
        with patch(
            "comic_identity_engine.jobs.worker.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings

            with patch(
                "comic_identity_engine.jobs.worker.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings

                # Patch task imports to avoid circular dependency issues
                with patch.object(
                    WorkerSettings, "_get_task_functions", return_value=[]
                ):
                    settings = WorkerSettings()

                    assert settings.redis_settings == mock_arq_redis_settings
                    assert settings.max_jobs == TEST_MAX_JOBS
                    assert settings.job_timeout == TEST_JOB_TIMEOUT
                    assert settings.keep_result == TEST_KEEP_RESULT
                    assert settings.functions == []

    def test_worker_settings_default_functions(self, mock_settings):
        """Test WorkerSettings with actual task function imports."""
        with patch(
            "comic_identity_engine.jobs.worker.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings

            with patch(
                "comic_identity_engine.jobs.worker.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings

                # Patch in the tasks module where the imports actually happen
                with patch(
                    "comic_identity_engine.jobs.tasks.resolve_identity_task"
                ) as mock_resolve:
                    with patch(
                        "comic_identity_engine.jobs.tasks.bulk_resolve_task"
                    ) as mock_bulk:
                        with patch(
                            "comic_identity_engine.jobs.tasks.import_clz_task"
                        ) as mock_import:
                            with patch(
                                "comic_identity_engine.jobs.tasks.export_task"
                            ) as mock_export:
                                with patch(
                                    "comic_identity_engine.jobs.tasks.reconcile_task"
                                ) as mock_reconcile:
                                    settings = WorkerSettings()

                                    expected_functions = [
                                        mock_resolve,
                                        mock_bulk,
                                        mock_import,
                                        mock_export,
                                        mock_reconcile,
                                    ]
                                    assert settings.functions == expected_functions


class TestCreateWorker:
    """Tests for create_worker function."""

    def test_create_worker_with_default_settings(self):
        """Test worker creation with default settings."""
        mock_settings_obj = Mock(spec=WorkerSettings)
        mock_settings_obj.redis_settings = mock_arq_redis_settings
        mock_settings_obj.max_jobs = TEST_MAX_JOBS
        mock_settings_obj.job_timeout = TEST_JOB_TIMEOUT
        mock_settings_obj.keep_result = TEST_KEEP_RESULT
        mock_settings_obj.functions = []

        with patch(
            "comic_identity_engine.jobs.worker.WorkerSettings",
            return_value=mock_settings_obj,
        ):
            with patch("comic_identity_engine.jobs.worker.Worker") as mock_worker_class:
                mock_worker = Mock(spec=Worker)
                mock_worker_class.return_value = mock_worker

                worker = create_worker()

                assert worker == mock_worker
                mock_worker_class.assert_called_once_with(
                    redis_settings=mock_arq_redis_settings,
                    max_jobs=TEST_MAX_JOBS,
                    job_timeout=TEST_JOB_TIMEOUT,
                    keep_result=TEST_KEEP_RESULT,
                    functions=[],
                )

    def test_create_worker_with_custom_settings(self):
        """Test worker creation with custom settings."""
        custom_settings = Mock(spec=WorkerSettings)
        custom_settings.redis_settings = mock_arq_redis_settings
        custom_settings.max_jobs = 20
        custom_settings.job_timeout = 600
        custom_settings.keep_result = 7200
        custom_settings.functions = [Mock()]

        with patch("comic_identity_engine.jobs.worker.Worker") as mock_worker_class:
            mock_worker = Mock(spec=Worker)
            mock_worker_class.return_value = mock_worker

            worker = create_worker(custom_settings)

            assert worker == mock_worker
            mock_worker_class.assert_called_once_with(
                redis_settings=mock_arq_redis_settings,
                max_jobs=20,
                job_timeout=600,
                keep_result=7200,
                functions=custom_settings.functions,
            )


class TestRunWorker:
    """Tests for run_worker function."""

    @pytest.mark.asyncio
    async def test_run_worker_success(self, mock_arq_redis_settings):
        """Test successful worker execution."""
        mock_settings_obj = Mock(spec=WorkerSettings)
        mock_settings_obj.redis_settings = mock_arq_redis_settings
        mock_settings_obj.max_jobs = TEST_MAX_JOBS
        mock_settings_obj.job_timeout = TEST_JOB_TIMEOUT
        mock_settings_obj.functions = []

        mock_worker = Mock(spec=Worker)
        mock_worker.async_run = AsyncMock()

        with patch(
            "comic_identity_engine.jobs.worker.WorkerSettings",
            return_value=mock_settings_obj,
        ):
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
        mock_settings_obj = Mock(spec=WorkerSettings)
        mock_settings_obj.redis_settings = mock_arq_redis_settings
        mock_settings_obj.max_jobs = TEST_MAX_JOBS
        mock_settings_obj.job_timeout = TEST_JOB_TIMEOUT
        mock_settings_obj.functions = []

        mock_worker = Mock(spec=Worker)
        mock_worker.async_run = AsyncMock(side_effect=KeyboardInterrupt())

        with patch(
            "comic_identity_engine.jobs.worker.WorkerSettings",
            return_value=mock_settings_obj,
        ):
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


class TestWorkerSettingsGetTaskFunctions:
    """Tests for WorkerSettings._get_task_functions method."""

    def test_get_task_functions_success(self, mock_settings):
        """Test successful retrieval of task functions."""
        with patch(
            "comic_identity_engine.jobs.worker.get_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = mock_settings

            with patch(
                "comic_identity_engine.jobs.worker.ArqRedisSettings.from_dsn"
            ) as mock_from_dsn:
                mock_from_dsn.return_value = mock_arq_redis_settings

                settings = WorkerSettings()
                functions = settings._get_task_functions()

                # Should return list of 5 task functions
                assert isinstance(functions, list)
                assert len(functions) == 5
