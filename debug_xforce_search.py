#!/usr/bin/env python3
"""Debug script to search for X-Force #47 across all platforms.

This script will print detailed debug information about:
1. The exact search parameters being passed to each platform
2. The URLs being constructed
3. The results returned from each platform
"""

import asyncio
import uuid
from comic_identity_engine.database.connection import AsyncSessionLocal
from comic_identity_engine.services.platform_searcher import PlatformSearcher
from comic_identity_engine.services.operations import OperationsManager


async def main():
    """Run platform search for X-Force #47."""
    print("\n" + "=" * 80)
    print("🎯 TESTING: X-Force #47 (CLZ ID: 103600)")
    print("=" * 80 + "\n")

    # Create a database session
    async with AsyncSessionLocal() as session:
        # Create an operation for tracking
        ops_manager = OperationsManager(session)
        operation = await ops_manager.create_operation(
            operation_type="resolve",
            input_data={
                "source": "test_script",
                "series_title": "X-Force",
                "issue_number": "47",
            },
        )
        await session.commit()
        operation_id = operation.id

        # Create platform searcher
        searcher = PlatformSearcher(session)

        # Search for X-Force #47 (we know it has CLZ ID 103600)
        print("\n🚀 Starting cross-platform search...\n")

        result = await searcher.search_all_platforms(
            issue_id=uuid.uuid4(),
            series_title="X-Force",
            issue_number="47",
            year=1992,  # X-Force started in 1991, issue #47 would be around 1995
            publisher="Marvel",
            operation_id=operation_id,
            source_platform="clz",  # We're starting from CLZ
            operations_manager=ops_manager,
        )

        # Print summary results
        print("\n" + "=" * 80)
        print("📋 FINAL RESULTS SUMMARY")
        print("=" * 80)
        print(f"\nPlatforms searched: {len(result['status'])}")
        print(f"URLs found: {len(result['urls'])}")
        print(f"\n{'Platform':<15} {'Status':<20} {'URL'}")
        print("-" * 80)

        for platform in sorted(result["status"].keys()):
            status_info = result["status"][platform]
            if isinstance(status_info, dict):
                status = status_info.get("status", "unknown")
            else:
                status = str(status_info)

            url = result["urls"].get(platform, "N/A")
            print(f"{platform:<15} {status:<20} {url}")

        print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
