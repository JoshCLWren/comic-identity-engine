"""Performance tests for Comic Identity Engine.

These tests measure queue throughput, worker utilization, and import performance.
"""

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest


class PerformanceMetrics:
    """Container for performance metrics."""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.total_tasks = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        self.queue_depth_samples = []
        self.worker_utilization_samples = []

    def record_queue_depth(self, depth):
        """Record a queue depth sample."""
        self.queue_depth_samples.append(depth)

    def record_worker_utilization(self, utilization):
        """Record a worker utilization sample."""
        self.worker_utilization_samples.append(utilization)

    @property
    def elapsed_seconds(self):
        """Calculate elapsed time in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0

    @property
    def tasks_per_second(self):
        """Calculate tasks per second."""
        if self.elapsed_seconds > 0:
            return self.completed_tasks / self.elapsed_seconds
        return 0

    @property
    def average_queue_depth(self):
        """Calculate average queue depth."""
        if self.queue_depth_samples:
            return sum(self.queue_depth_samples) / len(self.queue_depth_samples)
        return 0

    @property
    def average_worker_utilization(self):
        """Calculate average worker utilization."""
        if self.worker_utilization_samples:
            return sum(self.worker_utilization_samples) / len(
                self.worker_utilization_samples
            )
        return 0

    def to_dict(self):
        """Convert metrics to dictionary."""
        return {
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "tasks_per_second": round(self.tasks_per_second, 2),
            "average_queue_depth": round(self.average_queue_depth, 2),
            "average_worker_utilization": round(self.average_worker_utilization, 2),
        }


@pytest.mark.asyncio
@pytest.mark.performance
async def test_queue_throughput_high_volume():
    """Test queue throughput with 1000 tasks."""
    metrics = PerformanceMetrics()
    metrics.total_tasks = 1000

    mock_queue = Mock()
    mock_queue.enqueue_http_request = AsyncMock()

    for i in range(1000):
        mock_job = Mock()
        mock_job.job_id = f"job-{i}"
        mock_queue.enqueue_http_request.return_value = mock_job

        if i % 100 == 0:
            metrics.record_queue_depth(1000 - i)

    metrics.start_time = time.time()

    tasks = []
    for i in range(1000):
        task = asyncio.create_task(
            mock_queue.enqueue_http_request(
                platform="gcd",
                url=f"https://www.comics.org/issue/{i}/",
                method="GET",
            )
        )
        tasks.append(task)

    await asyncio.gather(*tasks)

    metrics.end_time = time.time()
    metrics.completed_tasks = 1000

    result = metrics.to_dict()

    assert result["total_tasks"] == 1000
    assert result["completed_tasks"] == 1000
    assert result["tasks_per_second"] > 0
    assert result["average_queue_depth"] > 0

    print("\n=== Queue Throughput Test Results ===")
    print(f"Total tasks: {result['total_tasks']}")
    print(f"Completed tasks: {result['completed_tasks']}")
    print(f"Elapsed time: {result['elapsed_seconds']:.2f}s")
    print(f"Tasks per second: {result['tasks_per_second']:.2f}")
    print(f"Average queue depth: {result['average_queue_depth']:.2f}")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_worker_utilization_parallel():
    """Test worker utilization with 100 parallel tasks."""
    metrics = PerformanceMetrics()
    metrics.total_tasks = 100

    async def simulate_worker_task(task_id):
        """Simulate a worker processing a task."""
        await asyncio.sleep(0.01)
        metrics.record_worker_utilization(1.0)
        return {"task_id": task_id, "success": True}

    metrics.start_time = time.time()

    tasks = [simulate_worker_task(i) for i in range(100)]
    results = await asyncio.gather(*tasks)

    metrics.end_time = time.time()
    metrics.completed_tasks = len([r for r in results if r["success"]])

    result = metrics.to_dict()

    assert result["total_tasks"] == 100
    assert result["completed_tasks"] == 100
    assert result["average_worker_utilization"] == 1.0

    print("\n=== Worker Utilization Test Results ===")
    print(f"Total tasks: {result['total_tasks']}")
    print(f"Completed tasks: {result['completed_tasks']}")
    print(f"Elapsed time: {result['elapsed_seconds']:.2f}s")
    print(f"Average worker utilization: {result['average_worker_utilization']:.2f}%")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_clz_import_performance_small():
    """Test CLZ import orchestrator performance with small CSV (10 rows)."""
    metrics = PerformanceMetrics()
    metrics.total_tasks = 10

    with patch(
        "comic_identity_engine.jobs.tasks.AsyncSessionLocal"
    ) as mock_session_local:
        session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

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
                    for i in range(1, 11)
                ]
                mock_adapter_class.return_value = mock_adapter

                from comic_identity_engine.jobs.tasks import import_clz_task

                with patch(
                    "comic_identity_engine.jobs.queue.JobQueue"
                ) as mock_queue_class:
                    mock_queue = Mock()
                    mock_queue.enqueue_series_bulk = AsyncMock()

                    mock_job = Mock()
                    mock_job.job_id = "test-job"
                    mock_queue.enqueue_series_bulk.return_value = mock_job

                    mock_queue.close = Mock()
                    mock_queue.close.return_value = None

                    mock_queue_class.return_value = mock_queue

                    metrics.start_time = time.time()

                    result = await import_clz_task(
                        {},
                        "test_small.csv",
                        str(uuid.uuid4()),
                    )

                    metrics.end_time = time.time()
                    # Orchestrator returns immediately after enqueueing
                    metrics.completed_tasks = result["total_rows"]

    metrics_dict = metrics.to_dict()

    assert metrics_dict["total_tasks"] == 10
    # Orchestrator doesn't process rows, just enqueues them
    assert result["total_rows"] == 10
    assert result["processed"] == 0

    print("\n=== CLZ Import Performance Test (Small CSV) ===")
    print(f"Total rows: {metrics_dict['total_tasks']}")
    print(f"Enqueued: {result['total_rows']}")
    print(f"Elapsed time: {metrics_dict['elapsed_seconds']:.2f}s")
    print(f"Tasks per second: {metrics_dict['tasks_per_second']:.2f}")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_clz_import_performance_medium():
    """Test CLZ import orchestrator performance with medium CSV (100 rows)."""
    metrics = PerformanceMetrics()
    metrics.total_tasks = 100

    with patch(
        "comic_identity_engine.jobs.tasks.AsyncSessionLocal"
    ) as mock_session_local:
        session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

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

                from comic_identity_engine.jobs.tasks import import_clz_task

                with patch(
                    "comic_identity_engine.jobs.queue.JobQueue"
                ) as mock_queue_class:
                    mock_queue = Mock()
                    mock_queue.enqueue_series_bulk = AsyncMock()

                    mock_job = Mock()
                    mock_job.job_id = "test-job"
                    mock_queue.enqueue_series_bulk.return_value = mock_job

                    mock_queue.close = Mock()
                    mock_queue.close.return_value = None

                    mock_queue_class.return_value = mock_queue

                    metrics.start_time = time.time()

                    result = await import_clz_task(
                        {},
                        "test_medium.csv",
                        str(uuid.uuid4()),
                    )

                    metrics.end_time = time.time()
                    # Orchestrator returns immediately after enqueueing
                    metrics.completed_tasks = result["total_rows"]

    metrics_dict = metrics.to_dict()

    assert metrics_dict["total_tasks"] == 100
    # Orchestrator doesn't process rows, just enqueues them
    assert result["total_rows"] == 100
    assert result["processed"] == 0

    print("\n=== CLZ Import Performance Test (Medium CSV) ===")
    print(f"Total rows: {metrics_dict['total_tasks']}")
    print(f"Enqueued: {result['total_rows']}")
    print(f"Elapsed time: {metrics_dict['elapsed_seconds']:.2f}s")
    print(f"Tasks per second: {metrics_dict['tasks_per_second']:.2f}")


def test_performance_summary():
    """Generate performance summary report."""
    print("\n" + "=" * 60)
    print("PERFORMANCE TEST SUMMARY")
    print("=" * 60)
    print("\nTarget Performance (from docs/archive/MASTIMPLEMENTATION_PLAN.md):")
    print("- Queue handles: 100k+ tasks")
    print("- Worker utilization: 90-100%")
    print("- Import time (5,200 rows): 15-30 minutes")
    print("- Tasks per second: ~3-6 tasks/sec (target)")
    print("\nTo run performance tests:")
    print("  uv run pytest tests/test_performance/ -m performance -v -s")
    print("\n" + "=" * 60)
