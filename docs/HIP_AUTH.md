# Authenticated HIP Adapter Usage

The `AuthenticatedHIPAdapter` provides authenticated access to HipComics.com price guide data, enabling:

- Access to member-only pricing data
- Higher rate limits
- More reliable scraping

## Setup

### 1. Install Dependencies

Playwright browsers must be installed:

```bash
uv sync
uv run playwright install chromium
```

### 2. Configure Credentials

Set environment variables:

```bash
export HIP_USERNAME=your_email@example.com
export HIP_PASSWORD=your_password
```

Or add to `.envrc` / `.env`:

```bash
HIP_USERNAME=your_email@example.com
HIP_PASSWORD=your_password
```

## Usage

### Basic Usage

```python
import asyncio
from comic_identity_engine.adapters.hip_auth import create_authenticated_hip_adapter

async def fetch_authenticated_price():
    # Create adapter (auto-authenticates and caches cookies)
    adapter = await create_authenticated_hip_adapter()

    # Fetch issue with authenticated session
    url = "https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/"
    issue = await adapter.fetch_issue("1-1", full_url=url)

    print(f"Issue: {issue.series_title} #{issue.issue_number}")
    print(f"Price: {issue.price}")

asyncio.run(fetch_authenticated_price())
```

### Context Manager Usage

```python
from comic_identity_engine.adapters.hip_auth import AuthenticatedHIPAdapter

async def fetch_multiple_issues():
    async with AuthenticatedHIPAdapter() as adapter:
        # Adapter is authenticated and cookies are set

        issue1 = await adapter.fetch_issue("1-1", full_url="...")
        issue2 = await adapter.fetch_issue("1-2", full_url="...")
```

### Custom Configuration

```python
from pathlib import Path
from comic_identity_engine.adapters.hip_auth import AuthenticatedHIPAdapter

async def custom_config():
    adapter = AuthenticatedHIPAdapter(
        username="custom@example.com",
        password="custom_password",
        cookie_file=Path("/tmp/custom_cookies.json"),
        headless=False,  # Show browser for debugging
    )

    async with adapter:
        issue = await adapter.fetch_issue("1-1", full_url="...")
```

## Cookie Caching

The adapter automatically caches authentication cookies to avoid repeated logins:

- Cookies are stored in `hip_cookies.json` by default
- Expired cookies are automatically refreshed
- Cookie file location is customizable

### Cookie Management

```python
from comic_identity_engine.adapters.hip_auth import AuthenticatedHIPAdapter

async def cookie_management():
    adapter = AuthenticatedHIPAdapter(
        cookie_file=Path("/tmp/my_cookies.json")
    )

    # First run: Performs login and saves cookies
    async with adapter as a:
        issue1 = await a.fetch_issue("1-1", full_url="...")

    # Subsequent runs: Reuses cached cookies (no login needed)
    async with adapter as a:
        issue2 = await a.fetch_issue("1-2", full_url="...")
```

## Integration with Comic Identity Engine

### Using with Identity Resolver

```python
from comic_identity_engine.adapters.hip_auth import create_authenticated_hip_adapter
from comic_identity_engine.services.identity_resolver import IdentityResolver
from comic_identity_engine.database import get_db

async def authenticated_search():
    # Get authenticated adapter
    hip_adapter = await create_authenticated_hip_adapter()

    async for db in get_db():
        resolver = IdentityResolver(db)

        # Search using authenticated HIP adapter
        result = await resolver.find_by_url(
            "https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/",
            adapters={"hip": hip_adapter}  # Use authenticated adapter
        )

        if result.matches:
            for match in result.matches:
                print(f"Found: {match.series_title} #{match.issue_number}")
```

## Benefits of Authentication

1. **Access to Member-Only Data**: Some pricing data is only available to logged-in users
2. **Higher Rate Limits**: Authenticated requests have more lenient rate limits
3. **Better Reliability**: Authenticated sessions are less likely to be blocked
4. **Cart Management**: Can add items to cart for purchase workflows

## Troubleshooting

### Login Fails

```bash
# Check credentials are set
echo $HIP_USERNAME
echo $HIP_PASSWORD

# Test login with visible browser (debugging)
headless=False
```

### Cookie Issues

```bash
# Clear stale cookies
rm hip_cookies.json

# Next run will perform fresh login
```

### Browser Not Installed

```bash
# Install Playwright browsers
uv run playwright install chromium
```

## Performance Tips

1. **Reuse Adapter Instances**: Create one adapter and reuse for multiple requests
2. **Cookie Caching**: Cookies are automatically cached, minimize logins
3. **Context Managers**: Use `async with` for proper resource cleanup

## Security Notes

- Never commit credentials to version control
- Use environment variables or secure credential management
- Cookie files contain session tokens - keep them private
- Cookies expire automatically, forcing re-authentication
