#!/usr/bin/env python
"""Test script to verify series page extraction and URL storage."""

import asyncio
import uuid

from comic_identity_engine.database.connection import AsyncSessionLocal
from comic_identity_engine.database.repositories import ExternalMappingRepository
from comic_identity_engine.services import SeriesPageExtractor


async def test_series_page_extractor():
    """Test that series page extractor returns full URLs."""
    print("Testing SeriesPageExtractor...")

    extractor = SeriesPageExtractor()

    # Test GCD (best API)
    issue_url = "https://www.comics.org/issue/125295/"  # X-Men #-1
    print(f"\n1. Testing GCD series URL extraction from: {issue_url}")

    try:
        series_url = await extractor.extract_series_url(issue_url, "gcd")
        print(f"   ✓ Series URL: {series_url}")

        issue_urls = await extractor.scrape_all_issues(series_url, "gcd")
        print(f"   ✓ Found {len(issue_urls)} issues")
        print(f"   ✓ First 3 issues: {issue_urls[:3]}")

        # Verify they're full URLs
        for url in issue_urls[:3]:
            assert url.startswith("https://"), f"Not a full URL: {url}"
        print("   ✓ All URLs are full URLs (not just IDs)")

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False

    return True


async def test_url_storage():
    """Test that URLs are actually stored in database."""
    print("\n2. Testing database URL storage...")

    async with AsyncSessionLocal() as session:
        repo = ExternalMappingRepository(session)

        # Create a test mapping with source_url
        issue_id = uuid.uuid4()
        test_url = "https://www.comics.org/issue/125295/"

        print(f"   Creating mapping with source_url: {test_url}")
        mapping = await repo.create_mapping(
            issue_id=issue_id,
            source="gcd",
            source_issue_id="125295",
            source_series_id="4254",
            source_url=test_url,
        )

        print(f"   ✓ Mapping created: {mapping.id}")

        # Verify it was actually saved
        retrieved = await repo.find_by_source("gcd", "125295")
        if not retrieved:
            print("   ✗ FAILED: Mapping not found in database")
            return False

        if retrieved.source_url != test_url:
            print("   ✗ FAILED: source_url not stored correctly")
            print(f"      Expected: {test_url}")
            print(f"      Got: {retrieved.source_url}")
            return False

        print(f"   ✓ source_url stored in database: {retrieved.source_url}")

        # Cleanup
        await session.delete(mapping)
        await session.commit()
        print("   ✓ Test mapping cleaned up")

    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("SERIES PAGE EXTRACTION & URL STORAGE TEST")
    print("=" * 60)

    # Test 1: Series page extractor
    extractor_ok = await test_series_page_extractor()

    # Test 2: Database storage
    storage_ok = await test_url_storage()

    print("\n" + "=" * 60)
    print("RESULTS:")
    print(f"  Series Page Extractor: {'✓ PASS' if extractor_ok else '✗ FAIL'}")
    print(f"  Database URL Storage:  {'✓ PASS' if storage_ok else '✗ FAIL'}")
    print("=" * 60)

    if extractor_ok and storage_ok:
        print("\n✓ ALL TESTS PASSED - URLs are being stored!")
        return 0
    else:
        print("\n✗ TESTS FAILED - URLs NOT being stored correctly")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
