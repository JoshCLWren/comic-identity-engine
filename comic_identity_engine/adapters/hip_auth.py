"""HipComic (HIP) adapter with authentication support.

This adapter extends the base HIP adapter to support authenticated requests
using Playwright for login and cookie management.

Authentication provides:
- Access to member-only pricing data
- Higher rate limits
- More reliable scraping
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, BrowserContext

from comic_identity_engine.adapters.hip import HIPAdapter
from comic_identity_engine.core.http_client import HttpClient
from longbox_commons.models import IssueCandidate, SeriesCandidate


logger = logging.getLogger(__name__)


class AuthenticatedHIPAdapter(HIPAdapter):
    """Authenticated HIP adapter with Playwright login support.

    This adapter handles login to HipComic.com using Playwright browser
    automation and stores cookies for authenticated HTTP requests.

    Usage:
        async with AuthenticatedHIPAdapter() as adapter:
            issue = await adapter.fetch_issue("1-1", full_url="...")
    """

    # Cookie storage file
    COOKIE_FILE = Path("hip_cookies.json")

    # Credential environment variables
    HIP_USERNAME_ENV = "HIP_USERNAME"
    HIP_PASSWORD_ENV = "HIP_PASSWORD"

    def __init__(
        self,
        http_client: HttpClient | None = None,
        timeout: float = 30.0,
        username: str | None = None,
        password: str | None = None,
        cookie_file: Path | None = None,
        headless: bool = True,
    ) -> None:
        """Initialize authenticated HIP adapter.

        Args:
            http_client: Optional HTTP client for making requests
            timeout: HTTP request timeout in seconds
            username: HipComics username (defaults to HIP_USERNAME env var)
            password: HipComics password (defaults to HIP_PASSWORD env var)
            cookie_file: Path to store/load cookies (defaults to hip_cookies.json)
            headless: Whether to run browser in headless mode
        """
        super().__init__(http_client, timeout)

        self.username = username or os.getenv(self.HIP_USERNAME_ENV)
        self.password = password or os.getenv(self.HIP_PASSWORD_ENV)
        self.cookie_file = cookie_file or self.COOKIE_FILE
        self.headless = headless

        self._playwright = None
        self._browser_context: BrowserContext | None = None
        self._authenticated_cookies: list[dict[str, Any]] | None = None

        if not self.username or not self.password:
            logger.warning(
                f"{self.HIP_USERNAME_ENV} or {self.HIP_PASSWORD_ENV} not set. "
                "Authentication will not work."
            )

    async def _load_cookies(self) -> list[dict[str, Any]] | None:
        """Load cookies from file if available.

        Returns:
            List of cookie dicts or None if file doesn't exist
        """
        if not self.cookie_file.exists():
            return None

        try:
            with open(self.cookie_file, "r") as f:
                cookies = json.load(f)

            # Check if cookies are still valid (not expired)
            import time

            current_time = int(time.time())
            valid_cookies = [
                c for c in cookies if c.get("expires", current_time + 1) > current_time
            ]

            if valid_cookies:
                logger.info(
                    f"Loaded {len(valid_cookies)} valid cookies from {self.cookie_file}"
                )
                return valid_cookies
            else:
                logger.info("Stored cookies have expired")
                return None

        except Exception as e:
            logger.warning(f"Failed to load cookies: {e}")
            return None

    async def _save_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Save cookies to file.

        Args:
            cookies: List of cookie dicts from Playwright
        """
        try:
            with open(self.cookie_file, "w") as f:
                json.dump(cookies, f, indent=2)
            logger.info(f"Saved {len(cookies)} cookies to {self.cookie_file}")
        except Exception as e:
            logger.warning(f"Failed to save cookies: {e}")

    async def _close_promo_iframe(self, page) -> None:
        """Close promotional iframe if it appears.

        Args:
            page: Playwright page object
        """
        try:
            # Look for close button in any frame
            frames = page.frames
            for frame in frames:
                try:
                    close_btn = frame.locator(
                        'button[aria-label*="close"], button[class*="close"], .close'
                    ).first
                    if await close_btn.count() > 0:
                        await close_btn.click()
                        await asyncio.sleep(0.5)
                except:
                    pass
        except:
            pass

    async def _login_with_playwright(self) -> list[dict[str, Any]]:
        """Perform login using Playwright and return cookies.

        Returns:
            List of cookie dicts from authenticated session

        Raises:
            Exception: If login fails
        """
        if not self.username or not self.password:
            raise Exception(
                f"Cannot login: {self.HIP_USERNAME_ENV} and {self.HIP_PASSWORD_ENV} "
                "must be set"
            )

        logger.info(f"Starting HIP login for {self.username}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/133.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
            )

            page = await context.new_page()

            try:
                # Navigate to cart page
                await page.goto("https://www.hipcomic.com/cart", timeout=30000)

                # Check if already logged in
                try:
                    my_account = page.locator("text=My Account")
                    if await my_account.is_visible(timeout=2000):
                        logger.info("Already logged in")
                        cookies = await context.cookies()
                        return cookies
                except:
                    pass

                # Click Sign In button
                sign_in_btn = page.get_by_role("button", name="Sign In")
                if not await sign_in_btn.is_visible(timeout=5000):
                    logger.info("No login required")
                    cookies = await context.cookies()
                    return cookies

                await sign_in_btn.click()
                await asyncio.sleep(1)

                # Close promo iframe
                await self._close_promo_iframe(page)

                # Enter email
                email_field = page.get_by_role("textbox", name="Email")
                await email_field.fill(self.username)

                continue_btn = page.get_by_role("button", name="continue", exact=True)
                await continue_btn.click()
                await asyncio.sleep(1)

                # Enter password
                password_field = page.get_by_role("dialog").get_by_role(
                    "textbox", name="Password"
                )
                await password_field.fill(self.password)

                sign_in_dialog = page.get_by_role("dialog").get_by_role(
                    "button", name="Sign In"
                )
                await sign_in_dialog.click()

                # Wait for login to complete
                await asyncio.sleep(3)

                # Verify login success
                my_account = page.locator("text=My Account")
                if await my_account.is_visible(timeout=5000):
                    logger.info("Login successful")
                    cookies = await context.cookies()
                    return cookies
                else:
                    raise Exception("Login verification failed")

            finally:
                await browser.close()

    async def _authenticate(self) -> None:
        """Perform authentication and store cookies.

        This method loads existing cookies if valid, otherwise performs
        a fresh login and saves new cookies.
        """
        # Try loading existing cookies first
        cookies = await self._load_cookies()
        if cookies:
            self._authenticated_cookies = cookies
            logger.info("Using cached authentication cookies")
            return

        # Perform fresh login
        logger.info("No valid cached cookies, performing login...")
        cookies = await self._login_with_playwright()
        self._authenticated_cookies = cookies

        # Save for future use
        await self._save_cookies(cookies)

    async def __aenter__(self):
        """Enter async context manager.

        Performs authentication and initializes HTTP client with cookies.
        """
        await self._authenticate()

        # Update headers with authentication cookies
        if self._authenticated_cookies:
            # Convert Playwright cookies to httpx cookie format
            cookie_header = "; ".join(
                [f"{c['name']}={c['value']}" for c in self._authenticated_cookies]
            )
            self.headers["Cookie"] = cookie_header

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager.

        Cleanup resources.
        """
        # Cookies are already saved, just cleanup
        self._authenticated_cookies = None

    async def fetch_issue(
        self, source_issue_id: str, full_url: str | None = None
    ) -> IssueCandidate:
        """Fetch issue from HIP with authentication.

        Overrides parent method to ensure authenticated requests.

        Args:
            source_issue_id: HIP listing ID or encoded issue identifier
            full_url: Optional canonical HipComic price-guide URL

        Returns:
            IssueCandidate with validated metadata

        Raises:
            SourceError: If authentication fails or HTTP error occurs
        """
        if not self._authenticated_cookies:
            logger.warning("No authentication cookies, attempting to authenticate...")
            await self._authenticate()

            if self._authenticated_cookies and self.http_client:
                cookie_header = "; ".join(
                    [f"{c['name']}={c['value']}" for c in self._authenticated_cookies]
                )
                self.headers["Cookie"] = cookie_header

        # Call parent implementation with authenticated headers
        return await super().fetch_issue(source_issue_id, full_url)

    def fetch_series_from_payload(
        self, source_series_id: str, payload: dict[str, Any]
    ) -> SeriesCandidate:
        """Fetch series from pre-fetched payload.

        This method doesn't require authentication as it uses pre-fetched data.

        Args:
            source_series_id: HIP series slug
            payload: Dict containing 'html' key with raw HIP page HTML

        Returns:
            SeriesCandidate with validated metadata
        """
        return super().fetch_series_from_payload(source_series_id, payload)

    def fetch_issue_from_payload(
        self, source_issue_id: str, payload: dict[str, Any]
    ) -> IssueCandidate:
        """Fetch issue from pre-fetched payload.

        This method doesn't require authentication as it uses pre-fetched data.

        Args:
            source_issue_id: HIP issue ID
            payload: Dict containing 'html' key with raw HIP page HTML

        Returns:
            IssueCandidate with validated metadata
        """
        return super().fetch_issue_from_payload(source_issue_id, payload)


async def create_authenticated_hip_adapter(
    username: str | None = None,
    password: str | None = None,
    cookie_file: Path | None = None,
    headless: bool = True,
) -> AuthenticatedHIPAdapter:
    """Factory function to create and initialize an authenticated HIP adapter.

    Args:
        username: HipComics username (defaults to HIP_USERNAME env var)
        password: HipComics password (defaults to HIP_PASSWORD env var)
        cookie_file: Path to store/load cookies (defaults to hip_cookies.json)
        headless: Whether to run browser in headless mode

    Returns:
        Initialized AuthenticatedHIPAdapter ready for use

    Example:
        adapter = await create_authenticated_hip_adapter()
        issue = await adapter.fetch_issue("1-1", full_url="...")
    """
    adapter = AuthenticatedHIPAdapter(
        username=username,
        password=password,
        cookie_file=cookie_file,
        headless=headless,
    )
    await adapter._authenticate()
    return adapter
