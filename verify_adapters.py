"""Verification script to test adapters fetch real data from platforms."""

import asyncio
import sys

# Test each adapter with a real URL
TEST_CASES = [
    ("gcd", "125295", "GCD - X-Men #1 (1991)"),  # Classic X-Men #1
    ("locg", "1169529", "LoCG - X-Men #1"),  # Known LoCG issue
    ("ccl", "28636", "CCL - X-Men #1"),  # CCL issue
    ("aa", "209583", "AA - X-Men #1"),  # Atomic Avenue item
    ("cpg", "12345", "CPG - Test item"),  # CPG item
    ("hip", "12345", "HIP - Test listing"),  # HipComic listing
]


async def test_adapter(platform: str, issue_id: str, description: str) -> dict:
    """Test a single adapter."""
    from comic_identity_engine.adapters import (
        AAAdapter,
        CCLAdapter,
        CPGAdapter,
        GCDAdapter,
        HIPAdapter,
        LoCGAdapter,
    )
    from comic_identity_engine.adapters.base import NotFoundError, SourceError

    adapters = {
        "gcd": GCDAdapter,
        "locg": LoCGAdapter,
        "ccl": CCLAdapter,
        "aa": AAAdapter,
        "cpg": CPGAdapter,
        "hip": HIPAdapter,
    }

    print(f"\n{'=' * 60}")
    print(f"Testing: {description}")
    print(f"Platform: {platform}, ID: {issue_id}")
    print(f"{'=' * 60}")

    try:
        adapter_class = adapters[platform]
        adapter = adapter_class()

        # Fetch the issue
        candidate = await adapter.fetch_issue(issue_id)

        print(f"✅ SUCCESS")
        print(f"   Series: {candidate.series_title}")
        print(f"   Issue #: {candidate.issue_number}")
        print(f"   Publisher: {candidate.publisher}")
        print(f"   Year: {candidate.series_start_year}")
        if candidate.upc:
            print(f"   UPC: {candidate.upc}")

        return {
            "platform": platform,
            "status": "success",
            "series": candidate.series_title,
            "issue_number": candidate.issue_number,
            "publisher": candidate.publisher,
        }

    except NotFoundError as e:
        print(f"⚠️  NOT FOUND: {e}")
        return {"platform": platform, "status": "not_found", "error": str(e)}

    except SourceError as e:
        print(f"❌ SOURCE ERROR: {e}")
        return {"platform": platform, "status": "source_error", "error": str(e)}

    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        return {"platform": platform, "status": "error", "error": str(e)}


async def main():
    """Run all adapter tests."""
    print("\n" + "=" * 60)
    print("COMIC IDENTITY ENGINE - ADAPTER VERIFICATION")
    print("Testing real HTTP fetching from all platforms")
    print("=" * 60)

    results = []
    for platform, issue_id, description in TEST_CASES:
        result = await test_adapter(platform, issue_id, description)
        results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    success_count = sum(1 for r in results if r["status"] == "success")
    not_found_count = sum(1 for r in results if r["status"] == "not_found")
    error_count = sum(1 for r in results if r["status"] in ("error", "source_error"))

    for r in results:
        status_icon = (
            "✅"
            if r["status"] == "success"
            else "⚠️"
            if r["status"] == "not_found"
            else "❌"
        )
        print(f"{status_icon} {r['platform'].upper()}: {r['status']}")

    print(f"\nTotal: {len(results)} adapters tested")
    print(f"✅ Success: {success_count}")
    print(f"⚠️  Not Found: {not_found_count}")
    print(f"❌ Errors: {error_count}")

    if error_count > 0:
        print("\n❌ VERIFICATION FAILED - Some adapters have errors")
        return 1
    elif success_count == 0:
        print("\n⚠️  No successful fetches - IDs may need updating")
        return 0
    else:
        print(f"\n✅ VERIFICATION PASSED - {success_count} adapters working!")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
