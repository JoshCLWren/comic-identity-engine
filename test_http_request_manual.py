#!/usr/bin/env python
"""Manual test script for http_request_task.

This script tests the HTTP request task infrastructure by:
1. Enqueueing a simple HTTP request
2. Polling for completion
3. Displaying the result

USAGE:
    uv run python test_http_request_manual.py
"""

import asyncio
import uuid

from comic_identity_engine.jobs.queue import JobQueue
from comic_identity_engine.database.connection import AsyncSessionLocal
from comic_identity_engine.services import OperationsManager


async def test_http_request_task():
    """Test the http_request_task with a simple HTTP GET request."""
    print("Testing http_request_task...")
    print("-" * 80)

    # Create a test operation ID
    operation_id = uuid.uuid4()
    print(f"Operation ID: {operation_id}")
    print()

    # Initialize the queue
    queue = JobQueue()

    try:
        # Enqueue a simple HTTP request to example.com
        print("Enqueueing HTTP request to https://www.comics.org/...")
        job = await queue.enqueue_http_request(
            url="https://www.comics.org/",
            method="GET",
            operation_id=operation_id,
            platform="gcd",
            verify_ssl=True,
        )
        print(f"Job enqueued with ID: {job.job_id}")
        print()

        # Poll for completion
        print("Polling for operation completion...")
        async with AsyncSessionLocal() as session:
            operations_manager = OperationsManager(session)

            max_attempts = 30  # Wait up to 30 seconds
            for attempt in range(max_attempts):
                await asyncio.sleep(1)

                operation = await operations_manager.get_operation(operation_id)

                if operation is None:
                    print(
                        f"Attempt {attempt + 1}/{max_attempts}: Operation not found yet..."
                    )
                    continue

                status = operation.status
                print(f"Attempt {attempt + 1}/{max_attempts}: Status = {status}")

                if status == "completed":
                    print()
                    print("✓ HTTP Request completed successfully!")
                    print("-" * 80)

                    result = operation.result or {}
                    print(f"Success: {result.get('success')}")
                    print(f"Status Code: {result.get('status_code')}")
                    print(f"Elapsed Time: {result.get('elapsed_ms')} ms")
                    print(f"Content Length: {len(result.get('content', ''))} bytes")
                    print(f"Operation ID: {result.get('operation_id')}")

                    if result.get("error"):
                        print(f"Error: {result.get('error')}")

                    print("-" * 80)
                    return True

                elif status == "failed":
                    print()
                    print("✗ HTTP Request failed!")
                    print("-" * 80)

                    error = operation.error or {}
                    print(f"Error: {error}")
                    print("-" * 80)
                    return False

            print()
            print("✗ Timed out waiting for operation to complete")
            return False

    except Exception as e:
        print(f"✗ Error during test: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        await queue.close()
        print()
        print("Test completed.")


if __name__ == "__main__":
    success = asyncio.run(test_http_request_task())
    exit(0 if success else 1)
