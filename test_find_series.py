#!/usr/bin/env python3
"""Test the new find_series() method in GCDScraper."""

import asyncio
import sys

sys.path.insert(0, "/mnt/extra/josh/code/longbox-scrapers")
sys.path.insert(0, "/mnt/extra/josh/code/longbox-commons")

from longbox_scrapers.adapters.gcd import GCDScraper


async def test_find_series():
    """Test find_series with year disambiguation."""
    scraper = GCDScraper()

    # Test 1: Majestic with year 2004 (should pick 2004-2005 series)
    print("Test 1: 'Majestic' with year=2004")
    result = await scraper.find_series("Majestic", year=2004)
    if result:
        print(
            f"  Found: {result.title} (ID: {result.series_id}, years: {result.start_year}-{result.end_year})"
        )
        assert result.series_id == "17798", f"Expected ID 17798, got {result.series_id}"
        assert result.start_year == 2004, (
            f"Expected start_year 2004, got {result.start_year}"
        )
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL: Not found")
        return False

    # Test 2: Majestic without year (should pick oldest: 1993)
    print("\nTest 2: 'Majestic' without year")
    result = await scraper.find_series("Majestic")
    if result:
        print(
            f"  Found: {result.title} (ID: {result.series_id}, years: {result.start_year}-{result.end_year})"
        )
        assert result.series_id == "26720", f"Expected ID 26720, got {result.series_id}"
        assert result.start_year == 1993, (
            f"Expected start_year 1993, got {result.start_year}"
        )
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL: Not found")
        return False

    # Test 3: Non-existent series
    print("\nTest 3: 'NonExistentSeries123'")
    result = await scraper.find_series("NonExistentSeries123")
    if result is None:
        print("  Correctly returned None")
        print("  ✓ PASS")
    else:
        print(f"  ✗ FAIL: Expected None, got {result}")
        return False

    # Test 4: The X-Men with year 1963 (should pick the original 1963 series)
    print("\nTest 4: 'The X-Men' with year=1963")
    result = await scraper.find_series("The X-Men", year=1963)
    if result:
        print(
            f"  Found: {result.title} (ID: {result.series_id}, years: {result.start_year}-{result.end_year})"
        )
        assert result.series_id == "1576", f"Expected ID 1576, got {result.series_id}"
        assert result.start_year == 1963, (
            f"Expected start_year 1963, got {result.start_year}"
        )
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL: Not found")
        return False

    # Test 5: Case-insensitive search
    print("\nTest 5: 'the x-men' (lowercase) with year=1963")
    result = await scraper.find_series("the x-men", year=1963)
    if result:
        print(
            f"  Found: {result.title} (ID: {result.series_id}, years: {result.start_year}-{result.end_year})"
        )
        assert result.series_id == "1576", f"Expected ID 1576, got {result.series_id}"
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL: Not found")
        return False

    print("\n" + "=" * 50)
    print("All tests passed!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_find_series())
    sys.exit(0 if success else 1)
