# Phase 6 Queue Configuration and Testing
## ⚠️ MANDATORY: Fix Broken Code

**ALL AI AGENTS MUST READ THIS:**

When you encounter broken code, tests, or functionality in this codebase, **you are REQUIRED to fix it**. Do NOT ignore broken code. Do NOT work around it. Do NOT leave it for "later".

**If you find it, you fix it.**

This includes but is not limited to:
- Failing tests
- Syntax errors
- Import errors
- Type errors
- Logic bugs
- LSP warnings that indicate real problems
- Inconsistent behavior

**No exceptions. No excuses.**

---


## Overview

This document describes the queue configuration, testing approach, and performance optimization for the Comic Identity Engine's ARQ-based task queue system.

## Queue Configuration

### Environment Variables

The following environment variables control ARQ queue behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `ARQ_QUEUE_URL` | `redis://localhost:6381/0` | Redis connection URL for the queue |
| `ARQ_QUEUE_NAME` | `cie:local:queue` | Name of the queue |
| `ARQ_QUEUE_SIZE` | `10000` | Maximum tasks in queue (0 = unlimited) |
| `ARQ_MAX_JOBS` | `100` | Maximum concurrent jobs processed per poll cycle |
| `ARQ_POLL_INTERVAL` | `0.1` | Queue polling interval in seconds (100ms = high throughput) |
| `ARQ_JOB_TIMEOUT` | `300` | Default job timeout in seconds (5 minutes) |
| `ARQ_KEEP_RESULT` | `3600` | How long to keep job results in seconds (1 hour) |

### Optimal Settings

For high-throughput CLZ imports (5,200+ rows):

```bash
# .env or .envrc
export ARQ_QUEUE_SIZE=10000  # Supports 100k+ tasks
export ARQ_MAX_JOBS=100  # Process 100 tasks per poll
export ARQ_POLL_INTERVAL=0.1  # Poll every 100ms
export ARQ_JOB_TIMEOUT=300  # 5 minutes per job
export ARQ_KEEP_RESULT=3600  # Keep results for 1 hour
```

**Why these values?**

- **ARQ_QUEUE_SIZE=10000**: Allows queue to buffer 10,000 tasks without blocking. With 5,200 rows × ~6 platform searches each = 31,200 tasks, this prevents backpressure during rapid enqueueing.

- **ARQ_MAX_JOBS=100**: Processes 100 tasks per poll cycle. With 10 workers, this keeps all workers busy continuously.

- **ARQ_POLL_INTERVAL=0.1**: Polls every 100ms for new tasks. This provides low-latency task pickup without excessive Redis CPU usage.

- **ARQ_JOB_TIMEOUT=300**: 5 minutes per job prevents hung tasks from blocking workers indefinitely.

- **ARQ_KEEP_RESULT=3600**: Keeps results for 1 hour for monitoring and debugging, then auto-cleans.

## Monitoring Queue Performance

### Key Metrics

Monitor these metrics during CLZ imports:

1. **Queue Depth**: Number of pending tasks
   - Target: < 5,000 during active import
   - Warning: > 8,000 indicates workers can't keep up

2. **Worker Utilization**: Percentage of workers actively processing
   - Target: 90-100%
   - Warning: < 80% indicates underutilized workers

3. **Task Throughput**: Tasks completed per second
   - Target: 3-6 tasks/second for full import
   - Warning: < 2 tasks/second indicates bottleneck

4. **Error Rate**: Percentage of failed tasks
   - Target: < 5%
   - Warning: > 10% indicates platform issues

### Monitoring Queries

#### Queue Depth (Redis)

```bash
# Check queue length
redis-cli -p 6381 -n 0 LLEN arq:queue

# Check queue length continuously
watch -n 1 'redis-cli -p 6381 -n 0 LLEN arq:queue'
```

#### Worker Utilization (Database)

```sql
-- Active operations in last minute
SELECT
    operation_type,
    status,
    COUNT(*) as count,
    AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_duration_sec
FROM operations
WHERE created_at > NOW() - INTERVAL '1 minute'
GROUP BY operation_type, status
ORDER BY count DESC;
```

#### Task Throughput (Database)

```sql
-- Tasks completed per hour
SELECT
    DATE_TRUNC('hour', completed_at) as hour,
    COUNT(*) as tasks_completed,
    COUNT(*) / 3600.0 as tasks_per_second
FROM operations
WHERE completed_at > NOW() - INTERVAL '24 hours'
    AND status = 'succeeded'
GROUP BY hour
ORDER BY hour DESC;
```

## Performance Testing

### Running Tests

```bash
# Run all performance tests
uv run pytest tests/test_performance/ -m performance -v -s

# Run specific performance test
uv run pytest tests/test_performance/test_queue_performance.py::test_queue_throughput_high_volume -v -s

# Run with coverage
uv run pytest tests/test_performance/ -m performance --cov=comic_identity_engine -v -s
```

### Test Descriptions

1. **test_queue_throughput_high_volume**: Tests queue capacity with 1,000 tasks
   - Measures enqueue rate
   - Verifies queue doesn't overflow
   - Reports tasks per second

2. **test_worker_utilization_parallel**: Tests worker utilization with 100 parallel tasks
   - Verifies all workers stay busy
   - Measures throughput
   - Reports utilization percentage

3. **test_clz_import_performance_small**: Tests CLZ import with 10 rows
   - End-to-end integration test
   - Measures total import time
   - Reports tasks per second

4. **test_clz_import_performance_medium**: Tests CLZ import with 100 rows
   - Scales to medium dataset
   - Identifies bottlenecks
   - Validates parallelism

### Expected Results

| Test | Metric | Target | Minimum Acceptable |
|------|--------|--------|-------------------|
| Queue Throughput | Tasks/sec | > 100 | > 50 |
| Worker Utilization | Utilization % | 95-100% | > 80% |
| CLZ Import (10 rows) | Total time | < 5s | < 10s |
| CLZ Import (100 rows) | Total time | < 30s | < 60s |

## Troubleshooting

### Issue: Queue Overflow

**Symptoms:**
- Tasks failing to enqueue
- "Queue full" errors
- Workers idle but tasks pending

**Solutions:**
1. Increase `ARQ_QUEUE_SIZE`
2. Add more workers
3. Reduce task enqueue rate (batch rows)

**Example:**
```bash
export ARQ_QUEUE_SIZE=20000  # Double queue size
```

### Issue: Low Worker Utilization

**Symptoms:**
- Workers idle frequently
- Queue empty
- Slow import progress

**Solutions:**
1. Increase `ARQ_MAX_JOBS`
2. Decrease `ARQ_POLL_INTERVAL`
3. Check for slow adapters (timeouts)

**Example:**
```bash
export ARQ_MAX_JOBS=200  # Double jobs per poll
export ARQ_POLL_INTERVAL=0.05  # Poll every 50ms
```

### Issue: High Error Rate

**Symptoms:**
- > 10% task failures
- Platform timeouts
- Connection errors

**Solutions:**
1. Check platform rate limits
2. Increase timeouts: `ARQ_JOB_TIMEOUT=600`
3. Verify network connectivity
4. Check Redis memory: `redis-cli INFO memory`

### Issue: Slow Import

**Symptoms:**
- Import takes > 30 minutes for 5,200 rows
- Tasks completing slowly
- Database locks

**Solutions:**
1. Check database connection pool size
2. Add indexes to operations table
3. Increase worker count
4. Profile slow queries

## Performance Comparison

### Before Optimization (Serial Processing)

| Metric | Value |
|--------|-------|
| Architecture | Single worker processes 5,200 rows serially |
| Time for 5,200 rows | 2-4 hours |
| Worker utilization | 10% (1 of 10 workers) |
| Throughput | 0.36-0.72 rows/sec |

### After Optimization (Task Queue)

| Metric | Value |
|--------|-------|
| Architecture | 10 workers process 93,600 HTTP request tasks in parallel |
| Time for 5,200 rows | 15-30 minutes (target) |
| Worker utilization | 90-100% (all workers) |
| Throughput | 3-6 rows/sec |

**Improvement:**
- **4-8x faster** import time
- **10x better** worker utilization
- **8-17x higher** throughput

## Rollback Plan

If issues occur after Phase 6 deployment:

1. **Revert queue settings:**
   ```bash
   export ARQ_QUEUE_SIZE=1000
   export ARQ_MAX_JOBS=10
   export ARQ_POLL_INTERVAL=1.0
   ```

2. **Stop workers:**
   ```bash
   pkill -f cie-worker
   ```

3. **Drain queue:**
   ```bash
   redis-cli -p 6381 -n 0 DEL arq:queue
   ```

4. **Restart with old settings:**
   ```bash
   source .env.hip.local  # Load old settings
   cie-worker
   ```

## Next Steps

1. **Monitor first full import**: Collect metrics on actual 5,200-row CSV
2. **Tune based on results**: Adjust settings based on real performance
3. **Add alerts**: Set up monitoring alerts for queue depth and error rate
4. **Scale if needed**: Add more workers if queue consistently fills

## References

- [MASTIMPLEMENTATION_PLAN.md](docs/archive/MASTIMPLEMENTATION_PLAN.md) - Full implementation plan
- [config.py](../comic_identity_engine/config.py) - Configuration settings
- [.env.example](../.env.example) - Environment variable template
