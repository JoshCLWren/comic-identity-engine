#!/usr/bin/env python
"""Test script to verify URLs are actually stored in database."""

import asyncio
import uuid

from comic_identity_engine.database.connection import AsyncSessionLocal
from comic_identity_engine.database.repositories import (
    ExternalMappingRepository,
    IssueRepository,
    SeriesRunRepository,
)


async def test_url_storage():
    """Test that source_url is stored in database."""
    print("=" * 60)
    print("DATABASE URL STORAGE TEST")
    print("=" * 60)

    async with AsyncSessionLocal() as session:
        series_repo = SeriesRunRepository(session)
        issue_repo = IssueRepository(session)
        mapping_repo = ExternalMappingRepository(session)

        # Step 1: Create a series
        print("\n1. Creating test series...")
        series = await series_repo.create(
            title="X-Men",
            start_year=1991,
            publisher="Marvel Comics",
        )
        print(f"   ✓ Created series: {series.id}")

        # Step 2: Create an issue
        print("\n2. Creating test issue...")
        issue = await issue_repo.create(
            series_run_id=series.id,
            issue_number="-1",
        )
        print(f"   ✓ Created issue: {issue.id}")

        # Step 3: Create mapping with source_url
        print("\n3. Creating external mapping with source_url...")
        test_url = "https://www.comics.org/issue/125295/"
        print(f"   source_url: {test_url}")

        mapping = await mapping_repo.create_mapping(
            issue_id=issue.id,
            source="gcd",
            source_issue_id="125295",
            source_series_id="4254",
            source_url=test_url,
        )
        print(f"   ✓ Created mapping: {mapping.id}")

        # Step 4: Query back from database to verify
        print("\n4. Querying database to verify source_url was saved...")
        retrieved = await mapping_repo.find_by_source("gcd", "125295")

        if not retrieved:
            print("   ✗ FAILED: Mapping not found in database!")
            return False

        print(f"   ✓ Mapping retrieved: {retrieved.id}")
        print(f"   ✓ source_issue_id: {retrieved.source_issue_id}")
        print(f"   ✓ source_url: {retrieved.source_url}")

        # Step 5: Verify URLs match
        if retrieved.source_url != test_url:
            print(f"   ✗ FAILED: URL mismatch!")
            print(f"      Expected: {test_url}")
            print(f"      Got: {retrieved.source_url}")
            return False

        print(f"   ✓ source_url MATCHES expected value")

        # Step 6: Check via raw SQL
        print("\n5. Verifying with raw SQL query...")
        from sqlalchemy import select, text

        result = await session.execute(
            text(
                "SELECT source, source_issue_id, source_url FROM external_mappings WHERE id = :mapping_id"
            ),
            {"mapping_id": retrieved.id},
        )
        row = result.fetchone()

        print(f"   Database row: {row}")
        if row[2] != test_url:
            print(f"   ✗ FAILED: Raw SQL shows different value!")
            return False

        print(f"   ✓ Raw SQL confirms source_url is stored")

        # Cleanup
        print("\n6. Cleaning up test data...")
        await session.delete(mapping)
        await session.delete(issue)
        await session.delete(series)
        await session.commit()
        print(f"   ✓ Test data cleaned up")

    return True


async def main():
    """Run the test."""
    try:
        success = await test_url_storage()

        print("\n" + "=" * 60)
        if success:
            print("✓ TEST PASSED - URLs ARE being stored in database!")
            print("=" * 60)
            return 0
        else:
            print("✗ TEST FAILED - URLs NOT being stored")
            print("=" * 60)
            return 1
    except Exception as e:
        print(f"\n✗ TEST FAILED with exception: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
