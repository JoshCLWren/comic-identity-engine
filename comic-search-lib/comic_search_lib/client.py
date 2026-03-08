"""
Unified comic search client.

This module provides a unified interface to search across multiple comic marketplaces.
"""

import asyncio
import logging
from typing import Any, Dict, List, Union

from comic_search_lib.exceptions import SearchError
from comic_search_lib.models.comic import Comic, SearchResult
from comic_search_lib.scrapers.atomic_avenue import AtomicAvenueScraper
from comic_search_lib.scrapers.hip import HipScraper
from comic_search_lib.scrapers.ccl import CCLScraper
from comic_search_lib.scrapers.locg import LoCGScraper


logger = logging.getLogger(__name__)


class ComicSearchClient:
    """
    Unified client for searching across multiple comic marketplaces.

    This client provides a simple interface to search for comics across
    Atomic Avenue, HipComic, Comic Collector Live, and League of Comic Geeks simultaneously.
    """

    def __init__(self, timeout: int = 30):
        """
        Initialize the ComicSearchClient.

        Args:
            timeout (int): Default timeout in seconds for operations
        """
        self.timeout = timeout
        self._aa_scraper = None
        self._hip_scraper = None
        self._ccl_scraper = None
        self._locg_scraper = None

    async def _get_scrapers(self):
        """Get or create scraper instances."""
        if self._aa_scraper is None:
            self._aa_scraper = AtomicAvenueScraper(timeout=self.timeout)
        if self._hip_scraper is None:
            self._hip_scraper = HipScraper(timeout=self.timeout)
        if self._ccl_scraper is None:
            self._ccl_scraper = CCLScraper(timeout=self.timeout)
        if self._locg_scraper is None:
            self._locg_scraper = LoCGScraper(timeout=self.timeout)
        return {
            "atomic_avenue": self._aa_scraper,
            "hip": self._hip_scraper,
            "ccl": self._ccl_scraper,
            "locg": self._locg_scraper,
        }

    async def search_all(
        self, comic: Union[Comic, Dict[str, Any]]
    ) -> Dict[str, SearchResult]:
        """
        Search for a comic across all platforms.

        Args:
            comic: The comic to search for, either as a Comic object or a dictionary

        Returns:
            Dict[str, SearchResult]: Dictionary mapping platform names to search results
                Platforms: "atomic_avenue", "hip", "ccl", "locg"
                Each result contains listings and prices found on that platform
        """
        scrapers = await self._get_scrapers()

        tasks = {}
        for platform, scraper in scrapers.items():
            if platform == "atomic_avenue":
                if isinstance(comic, dict):
                    tasks[platform] = scraper.search_comic(
                        title=comic.get("title", ""),
                        issue=comic.get("issue", ""),
                        year=comic.get("year"),
                        publisher=comic.get("publisher"),
                    )
                else:
                    tasks[platform] = scraper.search_comic(
                        title=comic.title,
                        issue=comic.issue,
                        year=comic.year,
                        publisher=comic.publisher,
                    )
            else:
                tasks[platform] = scraper.search_comic(comic)

        results = {}
        for platform, task in tasks.items():
            try:
                result = await task
                results[platform] = result
                logger.info(
                    f"{platform}: Found {len(result.listings)} listings for "
                    f"{result.comic.title} #{result.comic.issue}"
                )
            except SearchError as e:
                logger.warning(f"{platform} search failed: {e}")
                results[platform] = SearchResult(
                    comic=comic
                    if isinstance(comic, Comic)
                    else Comic(
                        id=f"{comic.get('title', '')}-{comic.get('issue', '')}",
                        title=comic.get("title", ""),
                        issue=comic.get("issue", ""),
                    ),
                    metadata={"error": str(e), "error_type": type(e).__name__},
                )
            except Exception as e:
                logger.error(f"{platform} search failed with unexpected error: {e}")
                results[platform] = SearchResult(
                    comic=comic
                    if isinstance(comic, Comic)
                    else Comic(
                        id=f"{comic.get('title', '')}-{comic.get('issue', '')}",
                        title=comic.get("title", ""),
                        issue=comic.get("issue", ""),
                    ),
                    metadata={"error": str(e), "error_type": type(e).__name__},
                )

        return results

    async def search_atomic_avenue(
        self, comic: Union[Comic, Dict[str, Any]]
    ) -> SearchResult:
        """
        Search for a comic on Atomic Avenue only.

        Args:
            comic: The comic to search for

        Returns:
            SearchResult: Search result from Atomic Avenue
        """
        if self._aa_scraper is None:
            self._aa_scraper = AtomicAvenueScraper(timeout=self.timeout)

        if isinstance(comic, dict):
            return await self._aa_scraper.search_comic(
                title=comic.get("title", ""),
                issue=comic.get("issue", ""),
                year=comic.get("year"),
                publisher=comic.get("publisher"),
            )
        else:
            return await self._aa_scraper.search_comic(
                title=comic.title,
                issue=comic.issue,
                year=comic.year,
                publisher=comic.publisher,
            )

    async def search_hip(self, comic: Union[Comic, Dict[str, Any]]) -> SearchResult:
        """
        Search for a comic on HipComic only.

        Args:
            comic: The comic to search for

        Returns:
            SearchResult: Search result from HipComic
        """
        if self._hip_scraper is None:
            self._hip_scraper = HipScraper(timeout=self.timeout)
        return await self._hip_scraper.search_comic(comic)

    async def search_ccl(self, comic: Union[Comic, Dict[str, Any]]) -> SearchResult:
        """
        Search for a comic on Comic Collector Live only.

        Args:
            comic: The comic to search for

        Returns:
            SearchResult: Search result from Comic Collector Live
        """
        if self._ccl_scraper is None:
            self._ccl_scraper = CCLScraper(timeout=self.timeout)
        return await self._ccl_scraper.search_comic(comic)

    async def search_locg(self, comic: Union[Comic, Dict[str, Any]]) -> SearchResult:
        """
        Search for a comic on League of Comic Geeks only.

        Args:
            comic: The comic to search for

        Returns:
            SearchResult: Search result from League of Comic Geeks
        """
        if self._locg_scraper is None:
            self._locg_scraper = LoCGScraper(timeout=self.timeout)
        return await self._locg_scraper.search_comic(comic)

    async def close(self) -> None:
        """Close all scrapers and cleanup resources."""
        logger.debug("Closing ComicSearchClient")

        if self._aa_scraper:
            self._aa_scraper = None

        if self._hip_scraper:
            await self._hip_scraper.close()
            self._hip_scraper = None

        if self._ccl_scraper:
            await self._ccl_scraper.close()
            self._ccl_scraper = None

        if self._locg_scraper:
            await self._locg_scraper.close()
            self._locg_scraper = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def get_summary(self, results: Dict[str, SearchResult]) -> Dict[str, Any]:
        """
        Get a summary of search results across all platforms.

        Args:
            results: Dictionary of search results from search_all()

        Returns:
            Dict containing summary statistics
        """
        summary = {
            "platforms_searched": len(results),
            "platforms_with_results": 0,
            "total_listings": 0,
            "total_prices": 0,
            "platforms": {},
        }

        for platform, result in results.items():
            listings_count = len(result.listings)
            prices_count = len(result.prices)

            summary["platforms"][platform] = {
                "listings": listings_count,
                "prices": prices_count,
                "has_error": "error" in result.metadata,
            }

            if listings_count > 0 or prices_count > 0:
                summary["platforms_with_results"] += 1

            summary["total_listings"] += listings_count
            summary["total_prices"] += prices_count

        return summary
