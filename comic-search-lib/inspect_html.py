"""Inspect AA HTML response."""

import asyncio
import httpx


async def main():
    url = "https://www.atomicavenue.com/atomic/SearchIssues.aspx?XT=1&M=1&T=X-Men&I=1&PN=1"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30.0)
        html = response.text

        print(f"Length: {len(html)}")
        print(f"Contains 'titleIssues': {'titleIssues' in html}")
        print(f"Contains 'X-Men': {'X-Men' in html}")
        print(f"Contains 'series': {'series' in html.lower()}")

        # Look for patterns
        if "<ul" in html:
            idx = html.find("<ul")
            print(f"\nFirst <ul> tag:\n{html[idx : idx + 200]}")

        # Find all ul class attributes
        import re

        ul_classes = re.findall(r'<ul[^>]*class="([^"]*)"', html)
        print(f"\nFound <ul> classes: {ul_classes[:5]}")

        # Save to file
        with open("/mnt/extra/josh/code/comic-search-lib/aa_response.html", "w") as f:
            f.write(html)
        print("\nSaved to aa_response.html")


if __name__ == "__main__":
    asyncio.run(main())
