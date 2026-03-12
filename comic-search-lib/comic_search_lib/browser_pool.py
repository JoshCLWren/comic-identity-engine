"""Browser pool for efficient Playwright resource management.

This module provides a shared browser context pool for scrapers that need
Playwright browser automation. Instead of each scraper creating its own
browser instance, they share a single context with multiple tabs.

This dramatically reduces memory usage when running multiple scrapers
concurrently in the worker.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


logger = logging.getLogger(__name__)


class BrowserPool:
    """Shared browser context pool for Playwright scrapers.

    Manages a single browser instance with multiple contexts/pages
    to reduce memory usage when running scrapers concurrently.

    Example:
        >>> async with BrowserPool() as pool:
        ...     page = await pool.acquire_page()
        ...     await page.goto("https://example.com")
        ...     await pool.release_page(page)
    """

    def __init__(
        self,
        max_pages: int = 20,
        headless: bool = True,
        user_data_dir: Path | None = None,
    ):
        """Initialize the browser pool.

        Args:
            max_pages: Maximum number of pages to maintain
            headless: Whether to run browser in headless mode
            user_data_dir: Optional directory for persistent browser profile
        """
        self.max_pages = max_pages
        self.headless = headless
        self.user_data_dir = user_data_dir

        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._available_pages: asyncio.Queue[Page] = asyncio.Queue()
        self._leased_pages: set[Page] = set()
        self._lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure browser pool is initialized."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            logger.info("Initializing browser pool")
            self._playwright = await async_playwright().start()

            launch_args = {
                "headless": self.headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--force-color-profile=srgb",
                ],
            }

            if self.user_data_dir:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    str(self.user_data_dir),
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    ignore_https_errors=True,
                    viewport={"width": 1280, "height": 800},
                    locale="en-US",
                    timezone_id="America/Chicago",
                    **launch_args,
                )
            else:
                self._browser = await self._playwright.chromium.launch(**launch_args)
                self._context = await self._browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                    ignore_https_errors=True,
                )

            self._context.set_default_timeout(30000)
            self._initialized = True

            logger.info("Browser pool initialized")

    async def acquire_page(self) -> Page:
        """Acquire a page from the pool.

        Creates a new page if none available, up to max_pages limit.

        Returns:
            A Playwright Page instance
        """
        await self._ensure_initialized()

        try:
            page = self._available_pages.get_nowait()
            self._leased_pages.add(page)
            logger.debug(
                f"Acquired existing page {id(page)} ({len(self._leased_pages)} leased)"
            )
            return page
        except asyncio.QueueEmpty:
            async with self._lock:
                if len(self._leased_pages) >= self.max_pages:
                    logger.warning(
                        f"Max pages ({self.max_pages}) reached, waiting for available page"
                    )
                    page = await self._available_pages.get()
                    self._leased_pages.add(page)
                    return page

                if self._context is None:
                    raise RuntimeError("Browser context not initialized")

                page = await self._context.new_page()
                page.set_default_timeout(30000)
                self._leased_pages.add(page)
                logger.debug(
                    f"Created new page {id(page)} ({len(self._leased_pages)} total leased)"
                )
                return page

    async def release_page(self, page: Page) -> None:
        """Release a page back to the pool.

        Args:
            page: The page to release
        """
        if page not in self._leased_pages:
            logger.warning(f"Page {id(page)} not in leased set, ignoring release")
            return

        self._leased_pages.remove(page)

        try:
            await page.close()
            logger.debug(f"Closed page {id(page)}")
        except Exception as e:
            logger.warning(f"Error closing page {id(page)}: {e}")

        await self._ensure_initialized()
        if self._context is None:
            raise RuntimeError("Browser context not initialized")

        new_page = await self._context.new_page()
        new_page.set_default_timeout(30000)
        await self._available_pages.put(new_page)
        logger.debug(
            f"Replaced released page with new page ({self._available_pages.qsize()} available)"
        )

    async def cleanup(self) -> None:
        """Clean up browser resources."""
        async with self._lock:
            if not self._initialized:
                return

            logger.info("Cleaning up browser pool")

            try:
                if self._context:
                    await asyncio.wait_for(self._context.close(), timeout=10.0)
                    logger.debug("Closed browser context")
            except asyncio.TimeoutError:
                logger.warning("Timeout closing browser context")
            except Exception as e:
                logger.warning(f"Error closing browser context: {e}")
            finally:
                self._context = None

            try:
                if self._browser:
                    await asyncio.wait_for(self._browser.close(), timeout=10.0)
                    logger.debug("Closed browser")
            except asyncio.TimeoutError:
                logger.warning("Timeout closing browser")
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            finally:
                self._browser = None

            try:
                if self._playwright:
                    await asyncio.wait_for(self._playwright.stop(), timeout=10.0)
                    logger.debug("Stopped playwright")
            except asyncio.TimeoutError:
                logger.warning("Timeout stopping playwright")
            except Exception as e:
                logger.warning(f"Error stopping playwright: {e}")
            finally:
                self._playwright = None

            self._initialized = False
            self._leased_pages.clear()

            while not self._available_pages.empty():
                try:
                    self._available_pages.get_nowait()
                except asyncio.QueueEmpty:
                    break

    async def __aenter__(self) -> "BrowserPool":
        """Enter context manager."""
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager."""
        await self.cleanup()


_global_pool: BrowserPool | None = None


async def get_global_pool() -> BrowserPool:
    """Get or create the global browser pool.

    Returns:
        The shared BrowserPool instance
    """
    global _global_pool

    if _global_pool is None:
        _global_pool = BrowserPool()
        await _global_pool._ensure_initialized()

    return _global_pool


@asynccontextmanager
async def browser_page():
    """Context manager for acquiring a browser page.

    Example:
        >>> async with browser_page() as page:
        ...     await page.goto("https://example.com")
    """
    pool = await get_global_pool()
    page = await pool.acquire_page()

    try:
        yield page
    finally:
        await pool.release_page(page)
