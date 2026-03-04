"""Quick test script to verify adapters work."""

import asyncio
from comic_identity_engine.core.http_client import HttpClient
from comic_identity_engine.adapters import GCDAdapter


async def test_gcd():
    """Test fetching an issue from GCD."""
    print("Testing GCD Adapter...")
    print("=" * 60)

    async with HttpClient(platform="gcd") as client:
        adapter = GCDAdapter(http_client=client)

        # Fetch X-Men #-1 (1997)
        issue = await adapter.fetch_issue("125295")

        print(f"✅ SUCCESS!")
        print(f"   Series: {issue.series_title}")
        print(f"   Issue #: {issue.issue_number}")
        print(f"   Publisher: {issue.publisher}")
        print(f"   Year: {issue.series_start_year}")
        print(f"   UPC: {issue.upc}")

        return issue


async def main():
    """Run all tests."""
    try:
        await test_gcd()
        print("\n" + "=" * 60)
        print("All tests passed! System is working.")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
