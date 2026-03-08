"""Tests for the Comic Collector Live scraper."""

from comic_search_lib.models.comic import Comic
from comic_search_lib.scrapers.ccl import CCLScraper


SEARCH_HTML = """
<html><body>
  <a id="84ac79ed-2a10-4a38-9b4c-6df3e0db37de">
    X-Men Comic Book Marvel 1991 - 2001 113 Issues , 14 Variants 0 Owned 0 Gaps 1 Listed
  </a>
  <a id="11111111-1111-1111-1111-111111111111">
    X-Men Comic Book Marvel 2010 - 2011 20 Issues , 0 Variants 0 Owned 0 Gaps 0 Listed
  </a>
</body></html>
"""

SERIES_HTML = """
<div class="card-issue" id="div_issuecard_98ab98c9-a87a-4cd2-b49a-ee5232abc0ad">
  <table class="text-center" style="width: 100%;">
    <tr>
      <td colspan="2">
        <a href="https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991/-1/98ab98c9-a87a-4cd2-b49a-ee5232abc0ad"
           id="ctl00_T_IssueCardRepeater_ctl00_cIssueCard_imgLink">
          <img class="img-responsive" src="https://images.example/xmen-1.jpg" />
        </a>
      </td>
    </tr>
    <tr>
      <td colspan="2">
        <div class="text-center small">
          <b>X-Men (1991)</b>
          <br/>
          <b>-1</b> A
        </div>
      </td>
    </tr>
  </table>
</div>
"""

DETAIL_HTML = """
<div class="main-box clearfix profile-box-contact">
  <div class="main-box-body clearfix">
    <div class="profile-box-header tile-bg-gray clearfix">
      <a class="txt-white" href="/LiveData/Seller.aspx?id=seller-1">Edgewood Comics</a>
      <div class="job-position">DGarman</div>
    </div>
    <div class="profile-box-footer clearfix">
      <div class="col-xs-5">
        <select class="form-control">
          <option value="listing-1">$0.99 - FN- </option>
        </select>
      </div>
    </div>
  </div>
</div>
"""


def test_ccl_scraper_initialization():
    """The scraper starts in HTTP mode with no owned client."""
    scraper = CCLScraper(timeout=30)
    assert scraper.timeout == 30
    assert scraper._client is None


def test_parse_search_results_picks_best_series_for_year():
    """Series selection should favor the matching series year."""
    scraper = CCLScraper()
    comic = Comic(
        id="xmen-1",
        title="X-Men",
        issue="-1",
        year=1991,
        publisher="Marvel",
    )

    result = scraper._parse_search_results_html(SEARCH_HTML, comic)

    assert result.metadata["selected_series_id"] == "84ac79ed-2a10-4a38-9b4c-6df3e0db37de"
    assert len(result.metadata["series_ids"]) == 2


def test_select_best_series_id_rejects_embedded_title_matches():
    """A title containing X-Men should not beat the actual X-Men series."""
    scraper = CCLScraper()
    comic = Comic(
        id="xmen-1",
        title="X-Men",
        issue="-1",
        year=1991,
        publisher="Marvel",
    )

    selected = scraper._select_best_series_id(
        [
            {
                "series_id": "wrong",
                "title_text": (
                    "Amazing Spider-Man and the X-Men in Arcade's Revenge "
                    "Comic Book Marvel UK 1992 1 Issues"
                ),
                "year": 1992,
            },
            {
                "series_id": "right",
                "title_text": (
                    "X-Men (1991) Comic Book Marvel 1991 - 2001 166 Issues"
                ),
                "year": 1991,
            },
        ],
        comic,
    )

    assert selected == "right"


def test_build_search_queries_prefers_normalized_title_plus_year():
    """CCL search works better with condensed title tokens plus the series year."""
    scraper = CCLScraper()
    comic = Comic(
        id="xmen-1",
        title="X-Men",
        issue="-1",
        year=1991,
        publisher="Marvel",
    )

    assert scraper._build_search_queries(comic) == [
        "xmen 1991",
        "xmen",
        "x men 1991",
        "x men",
    ]


def test_parse_issue_detail_page_extracts_vendor_listing():
    """Vendor listing parsing should preserve the direct issue URL."""
    scraper = CCLScraper()
    comic = Comic(
        id="xmen-1",
        title="X-Men",
        issue="-1",
        year=1991,
        publisher="Marvel",
    )

    listings = scraper._parse_issue_detail_page(
        html=DETAIL_HTML,
        comic=comic,
        detail_url="https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991/-1/98ab98c9-a87a-4cd2-b49a-ee5232abc0ad",
        image_url="https://images.example/xmen-1.jpg",
    )

    assert len(listings) == 1
    assert listings[0].store == "Edgewood Comics"
    assert listings[0].title == "X-Men #-1"
    assert listings[0].price == "$0.99"
    assert listings[0].grade == "FN-"
    assert listings[0].url.endswith("/-1/98ab98c9-a87a-4cd2-b49a-ee5232abc0ad")


def test_extract_issue_text_from_series_card():
    """Series card parsing should read the issue token from the current markup."""
    scraper = CCLScraper()
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(SERIES_HTML, "html.parser")
    card = soup.find("div", class_="card-issue")

    assert card is not None
    assert scraper._extract_issue_text(card) == "-1"


def test_should_scan_unfiltered_series_for_negative_issue():
    """Negative issue numbers need the unfiltered-series fallback on CCL."""
    scraper = CCLScraper()

    assert scraper._should_scan_unfiltered_series("-1") is True
    assert scraper._should_scan_unfiltered_series("1/2") is True
    assert scraper._should_scan_unfiltered_series("25") is False
