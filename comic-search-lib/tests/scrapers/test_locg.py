"""Tests for the League of Comic Geeks scraper."""

from comic_search_lib.models.comic import Comic
from comic_search_lib.scrapers.locg import LoCGScraper


def test_locg_scraper_initialization():
    """The scraper should keep the configured timeout."""
    scraper = LoCGScraper(timeout=30)
    assert scraper.timeout == 30


def test_build_series_queries_prefers_series_start_year():
    """Series search should start with the series year, not the cover year."""
    scraper = LoCGScraper()
    comic = Comic(
        id="x-men--1",
        title="X-Men",
        issue="-1",
        year=1997,
        series_start_year=1991,
        publisher="Marvel",
    )

    assert scraper._build_series_queries(comic) == ["X-Men 1991", "X-Men 1997", "X-Men"]


def test_select_best_series_match_uses_title_and_year():
    """The correct LoCG series should beat similarly named series."""
    scraper = LoCGScraper()
    comic = Comic(
        id="x-men--1",
        title="X-Men",
        issue="-1",
        year=1997,
        series_start_year=1991,
        publisher="Marvel",
    )
    series_results = [
        {
            "url": "https://leagueofcomicgeeks.com/comics/series/108378/the-x-men",
            "title": "The X-Men",
            "card_text": "Marvel Comics · 1963 - 1981",
        },
        {
            "url": "https://leagueofcomicgeeks.com/comics/series/111275/x-men",
            "title": "X-Men",
            "card_text": "Marvel Comics · 1991 - 2001",
        },
    ]

    best_match = scraper._select_best_series_match(series_results, comic)

    assert best_match is not None
    assert best_match["url"] == "https://leagueofcomicgeeks.com/comics/series/111275/x-men"
    assert best_match["series_year"] == 1991


def test_select_best_series_match_prefers_publisher_and_issue_capacity():
    """Publisher and issue-count fit should beat foreign runs with too few issues."""
    scraper = LoCGScraper()
    comic = Comic(
        id="batman-158",
        title="Batman",
        issue="158",
        year=1954,
        publisher="DC",
    )
    series_results = [
        {
            "url": "https://leagueofcomicgeeks.com/comics/series/169805/batman",
            "title": "Batman",
            "card_text": "91\nInterpresse · 1972 - 1980\nBatman",
        },
        {
            "url": "https://leagueofcomicgeeks.com/comics/series/100001/batman",
            "title": "Batman",
            "card_text": "1670\nDC Comics · 1940 - 2011\nBatman",
        },
    ]

    best_match = scraper._select_best_series_match(series_results, comic)

    assert best_match is not None
    assert best_match["url"] == "https://leagueofcomicgeeks.com/comics/series/100001/batman"
    assert best_match["publisher"] == "DC Comics"
    assert best_match["issue_count"] == 1670


def test_select_issue_match_finds_negative_issue_and_skips_variants():
    """The base issue link should win over variant links for the same issue."""
    scraper = LoCGScraper()
    issue_links = [
        {
            "url": "https://leagueofcomicgeeks.com/comic/1169529/x-men-1?variant=6930677",
            "title": "X-Men #-1 Carlos Pacheco Variant",
        },
        {
            "url": "https://leagueofcomicgeeks.com/comic/1169529/x-men-1",
            "title": "X-Men #-1",
        },
    ]

    match = scraper._select_issue_match(issue_links, "-1")

    assert match == {
        "url": "https://leagueofcomicgeeks.com/comic/1169529/x-men-1",
        "title": "X-Men #-1",
    }


def test_extract_issue_from_title_handles_negative_issue_numbers():
    """LoCG titles include special numbering like #-1."""
    scraper = LoCGScraper()

    assert scraper._extract_issue_from_title("X-Men #-1") == "-1"
    assert scraper._extract_issue_from_title("X-Men #100") == "100"


def test_extract_issue_count_and_publisher_from_card_text():
    """LoCG result cards encode issue count and publisher on separate lines."""
    scraper = LoCGScraper()
    card_text = "1670\nDC Comics · 1940 - 2011\nBatman"

    assert scraper._extract_issue_count(card_text) == 1670
    assert scraper._extract_publisher(card_text) == "DC Comics"
