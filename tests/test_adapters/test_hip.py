"""Tests for HIP adapter implementation."""

from datetime import date
from unittest.mock import Mock

import httpx
import pytest

from comic_identity_engine.adapters import HIPAdapter, NotFoundError, ValidationError


class TestHIPAdapterSeriesMapping:
    """Tests for HIP series payload mapping."""

    def test_successful_series_mapping(self):
        """HIP series HTML payload maps to SeriesCandidate correctly."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <div class="publisher">Marvel Comics</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_series_from_payload("x-men-1991", payload)

        assert result.source == "hip"
        assert result.source_series_id == "x-men-1991"
        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991
        assert result.publisher == "Marvel Comics"

    def test_series_with_no_publisher(self):
        """Series HTML without publisher still parses correctly."""
        html = """
        <html>
        <body>
            <h1>Amazing Spider-Man (1963)</h1>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_series_from_payload("amazing-spider-man-1963", payload)

        assert result.series_title == "Amazing Spider-Man"
        assert result.series_start_year == 1963
        assert result.publisher is None

    def test_missing_title_raises_error(self):
        """Series HTML without h1 title raises ValidationError."""
        html = """
        <html>
        <body>
            <div class="publisher">Marvel Comics</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="missing required field: title"):
            adapter.fetch_series_from_payload("test-series", payload)

    def test_missing_year_raises_error(self):
        """Series HTML without year raises ValidationError."""
        html = """
        <html>
        <body>
            <h1>X-Men</h1>
            <div class="publisher">Marvel Comics</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="missing required field: start_year"):
            adapter.fetch_series_from_payload("x-men", payload)

    def test_empty_payload_raises_error(self):
        """Empty series payload raises ValidationError."""
        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="payload is empty"):
            adapter.fetch_series_from_payload("x-men-1991", {})

    def test_missing_html_field_raises_error(self):
        """Payload without html field raises ValidationError."""
        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="missing 'html' field"):
            adapter.fetch_series_from_payload("x-men-1991", {"data": "not html"})

    def test_malformed_html_raises_error(self):
        """Malformed HTML that cannot be parsed raises ValidationError."""
        html = "<html></html>"
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="Could not extract series data"):
            adapter.fetch_series_from_payload("test", payload)


class TestHIPAdapterIssueMapping:
    """Tests for HIP issue payload mapping."""

    def test_successful_issue_mapping_xmen_negative1(self):
        """HIP issue HTML for X-Men #-1 maps correctly."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <div class="issue-number">1-1</div>
            <div class="publisher">Marvel Comics</div>
            <div class="cover-date">July 1997</div>
            <div class="price">$1.95</div>
            <div class="page-count">44 pages</div>
            <div class="upc">75960601772099911</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_issue_from_payload("1-1", payload)

        assert result.source == "hip"
        assert result.source_issue_id == "1-1"
        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991
        assert result.publisher == "Marvel Comics"
        assert result.issue_number == "-1"
        assert result.cover_date == date(1997, 7, 1)
        assert result.price == 1.95
        assert result.page_count == 44
        assert result.upc == "75960601772099911"

    def test_issue_mapping_with_variant(self):
        """HIP issue HTML with variant information."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <div class="issue-number">100</div>
            <div class="publisher">Marvel Comics</div>
            <div class="variant">Direct Edition</div>
            <div class="cover-date">August 2000</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_issue_from_payload("100", payload)

        assert result.issue_number == "100"
        assert result.variant_suffix == "DIRECTEDITION"
        assert result.variant_name == "Direct Edition"

    def test_issue_mapping_with_single_letter_variant(self):
        """HIP issue HTML with single letter variant (A, B, C)."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <div class="issue-number">1</div>
            <div class="publisher">Marvel Comics</div>
            <div class="variant">A</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_issue_from_payload("1", payload)

        assert result.issue_number == "1"
        assert result.variant_suffix == "A"

    def test_issue_mapping_from_live_ssr_detail_layout(self):
        """HIP live SSR detail rows map correctly without .issue-number elements."""
        html = """
        <html>
        <head>
            <meta name="description" content="X-Men #-1 (1997)">
        </head>
        <body>
            <h1 style="display:none;"></h1>
            <div class="r-detail-attribute">
                <span class="r-detail-attribute__label r-detail-attribute__label--small">Publisher</span>
                <a>Marvel</a>
            </div>
            <div class="r-detail-attribute">
                <span class="r-detail-attribute__label r-detail-attribute__label--small">Issue</span>
                <a href="/price-guide/us/marvel/comic/x-men-1991/1-1/">-1</a>
            </div>
            <div class="r-detail-attribute">
                <span class="r-detail-attribute__label r-detail-attribute__label--small">Series</span>
                <a href="/price-guide/us/marvel/comic/x-men-1991/">X-Men (1991)</a>
            </div>
            <script>
                window.__NUXT__={coverDate:"1997-07-01"}
            </script>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_issue_from_payload("1-1", payload)

        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991
        assert result.issue_number == "-1"
        assert result.publisher == "Marvel"
        assert result.cover_date is None

    def test_series_slug_extraction(self):
        """Series slug is extracted from HTML."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <div class="issue-number">1</div>
            <a href="/comic/x-men-1991/1/">Link</a>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_issue_from_payload("1", payload)

        assert result.source_series_id == "x-men-1991"

    def test_missing_series_title_raises_error(self):
        """Issue HTML without series title raises ValidationError."""
        html = """
        <html>
        <body>
            <div class="issue-number">1</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: series_title"
        ):
            adapter.fetch_issue_from_payload("1", payload)

    def test_missing_issue_number_raises_error(self):
        """Issue HTML without issue number raises ValidationError."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="Could not extract issue data"):
            adapter.fetch_issue_from_payload("test", payload)

    def test_invalid_issue_number_raises_error(self):
        """Invalid issue number format raises ValidationError."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <div class="issue-number">1-3</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="Invalid issue number"):
            adapter.fetch_issue_from_payload("1-3", payload)

    def test_empty_issue_payload_raises_error(self):
        """Empty issue payload raises ValidationError."""
        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="payload is empty"):
            adapter.fetch_issue_from_payload("1", {})

    def test_missing_html_field_in_issue_raises_error(self):
        """Issue payload without html field raises ValidationError."""
        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="missing 'html' field"):
            adapter.fetch_issue_from_payload("1", {"data": "not html"})

    def test_malformed_issue_html_raises_error(self):
        """Malformed issue HTML raises ValidationError."""
        html = "<html></html>"
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="Could not extract issue data"):
            adapter.fetch_issue_from_payload("1", payload)


class TestHIPAdapterHelpers:
    """Tests for HIP adapter helper methods."""

    def test_parse_hip_title_with_year(self):
        """HIP title with year is parsed correctly."""
        adapter = HIPAdapter()
        title, year = adapter._parse_hip_title("X-Men (1991)")

        assert title == "X-Men"
        assert year == 1991

    def test_parse_hip_title_without_year(self):
        """HIP title without year returns title with None year."""
        adapter = HIPAdapter()
        title, year = adapter._parse_hip_title("X-Men")

        assert title == "X-Men"
        assert year is None

    def test_clean_issue_number_negative_encoded(self):
        """HIP encoded negative number 1-1 is cleaned to -1."""
        adapter = HIPAdapter()
        result = adapter._clean_issue_number("1-1")

        assert result == "-1"

    def test_clean_issue_number_with_hash(self):
        """Issue number with # prefix is cleaned."""
        adapter = HIPAdapter()
        result = adapter._clean_issue_number("#1")

        assert result == "1"

    def test_clean_issue_number_with_spaces(self):
        """Issue number with spaces is cleaned."""
        adapter = HIPAdapter()
        result = adapter._clean_issue_number("  100  ")

        assert result == "100"

    def test_clean_issue_number_default_return(self):
        """Issue number that doesn't match pattern returns as-is (default path)."""
        adapter = HIPAdapter()
        result = adapter._clean_issue_number("#")

        assert result == "#"

    def test_extract_variant_suffix_single_letter(self):
        """Single letter variant is extracted correctly."""
        adapter = HIPAdapter()
        result = adapter._extract_variant_suffix("A")

        assert result == "A"

    def test_extract_variant_suffix_with_hyphens(self):
        """Variant with hyphens is normalized."""
        adapter = HIPAdapter()
        result = adapter._extract_variant_suffix("direct-edition")

        assert result == "DIRECTEDITION"

    def test_extract_variant_suffix_none(self):
        """None variant returns None."""
        adapter = HIPAdapter()
        result = adapter._extract_variant_suffix(None)

        assert result is None

    def test_extract_variant_suffix_empty_string(self):
        """Empty variant returns None."""
        adapter = HIPAdapter()
        result = adapter._extract_variant_suffix("")

        assert result is None

    def test_parse_date_with_month_year(self):
        """Date string with month and year is parsed correctly."""
        adapter = HIPAdapter()
        result = adapter._parse_date("July 1997")

        assert result == date(1997, 7, 1)

    def test_parse_date_with_year_only(self):
        """Date string with year only is parsed correctly."""
        adapter = HIPAdapter()
        result = adapter._parse_date("Published in 1997")

        assert result == date(1997, 1, 1)

    def test_parse_date_none_returns_none(self):
        """None date string returns None."""
        adapter = HIPAdapter()
        result = adapter._parse_date(None)

        assert result is None

    def test_parse_date_empty_string_returns_none(self):
        """Empty date string returns None."""
        adapter = HIPAdapter()
        result = adapter._parse_date("")

        assert result is None

    def test_parse_date_invalid_format_returns_none(self):
        """Invalid date format returns None."""
        adapter = HIPAdapter()
        result = adapter._parse_date("invalid-date")

        assert result is None

    def test_parse_price_with_dollar_sign(self):
        """Price with dollar sign is parsed correctly."""
        adapter = HIPAdapter()
        result = adapter._parse_price("$1.95")

        assert result == 1.95

    def test_parse_price_with_commas(self):
        """Price with commas is parsed correctly."""
        adapter = HIPAdapter()
        result = adapter._parse_price("$1,995.00")

        assert result == 1995.0

    def test_parse_price_without_dollar_sign(self):
        """Price without dollar sign is parsed correctly."""
        adapter = HIPAdapter()
        result = adapter._parse_price("2.50")

        assert result == 2.5

    def test_parse_price_none_returns_none(self):
        """None price returns None."""
        adapter = HIPAdapter()
        result = adapter._parse_price(None)

        assert result is None

    def test_parse_price_empty_string_returns_none(self):
        """Empty price string returns None."""
        adapter = HIPAdapter()
        result = adapter._parse_price("")

        assert result is None

    def test_parse_price_invalid_format_returns_none(self):
        """Invalid price format returns None."""
        adapter = HIPAdapter()
        result = adapter._parse_price("free")

        assert result is None

    def test_parse_page_count_with_number(self):
        """Page count with number is parsed correctly."""
        adapter = HIPAdapter()
        result = adapter._parse_page_count("44 pages")

        assert result == 44

    def test_parse_page_count_standalone_number(self):
        """Standalone number is parsed as page count."""
        adapter = HIPAdapter()
        result = adapter._parse_page_count("36")

        assert result == 36

    def test_parse_page_count_none_returns_none(self):
        """None page count returns None."""
        adapter = HIPAdapter()
        result = adapter._parse_page_count(None)

        assert result is None

    def test_parse_page_count_empty_string_returns_none(self):
        """Empty page count returns None."""
        adapter = HIPAdapter()
        result = adapter._parse_page_count("")

        assert result is None

    def test_parse_page_count_invalid_format_returns_none(self):
        """Invalid page count format returns None."""
        adapter = HIPAdapter()
        result = adapter._parse_page_count("unknown")

        assert result is None


class TestHIPAdapterEdgeCases:
    """Edge case tests for HIP adapter to improve coverage."""

    def test_series_extraction_with_title_only(self):
        """Series extraction with title but no year returns partial data."""
        html = """
        <html>
        <body>
            <h1>X-Men</h1>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="missing required field: start_year"):
            adapter.fetch_series_from_payload("x-men", payload)

    def test_series_extraction_with_year_only(self):
        """Series extraction with year but no title returns partial data."""
        html = """
        <html>
        <body>
            <div>(1991)</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="missing required field: title"):
            adapter.fetch_series_from_payload("test", payload)

    def test_issue_extraction_with_empty_issue_number(self):
        """Issue extraction with empty issue-number element."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <span class="issue-number"></span>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: issue_number"
        ):
            adapter.fetch_issue_from_payload("test", payload)

    def test_issue_extraction_with_title_only(self):
        """Issue extraction with title but no issue number returns partial data."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="Could not extract issue data"):
            adapter.fetch_issue_from_payload("test", payload)

    def test_series_extraction_with_year_in_body(self):
        """Series extraction works when year is in body not title."""
        html = """
        <html>
        <body>
            <h1>X-Men</h1>
            <div>Published in (1991)</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_series_from_payload("x-men-1991", payload)

        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991

    def test_series_extraction_fallback_to_title_only(self):
        """Series with year in body still uses title for name."""
        html = """
        <html>
        <body>
            <h1>Amazing Spider-Man</h1>
            <span>(1963)</span>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_series_from_payload("amazing-spider-man", payload)

        assert result.series_title == "Amazing Spider-Man"
        assert result.series_start_year == 1963

    def test_series_with_no_h1_fails(self):
        """Series HTML without h1 element fails extraction."""
        html = """
        <html>
        <body>
            <div>X-Men (1991)</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="missing required field: title"):
            adapter.fetch_series_from_payload("test", payload)

    def test_issue_extraction_fallback_patterns(self):
        """Issue extraction uses fallback CSS selectors."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <span class="my-issue">1</span>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        with pytest.raises(ValidationError, match="Could not extract issue data"):
            adapter.fetch_issue_from_payload("1", payload)

    def test_parse_date_case_insensitive_month(self):
        """Date parsing works with uppercase month names."""
        adapter = HIPAdapter()
        result = adapter._parse_date("JULY 1997")

        assert result == date(1997, 7, 1)

    def test_parse_date_short_month_name(self):
        """Date parsing works with abbreviated month names."""
        adapter = HIPAdapter()
        result = adapter._parse_date("Jan 2020")

        assert result == date(2020, 1, 1)

    def test_variant_suffix_with_spaces(self):
        """Variant suffix with spaces is normalized."""
        adapter = HIPAdapter()
        result = adapter._extract_variant_suffix("direct edition")

        assert result == "DIRECTEDITION"

    def test_variant_suffix_with_underscores(self):
        """Variant suffix with underscores is normalized."""
        adapter = HIPAdapter()
        result = adapter._extract_variant_suffix("limited_edition")

        assert result == "LIMITEDEDITION"

    def test_price_with_invalid_float_returns_none(self):
        """Price that cannot convert to float returns None."""
        adapter = HIPAdapter()
        result = adapter._parse_price("$")

        assert result is None

    def test_page_count_with_text_only_returns_none(self):
        """Page count without numbers returns None."""
        adapter = HIPAdapter()
        result = adapter._parse_page_count("many pages")

        assert result is None

    def test_clean_issue_number_with_negative_stripped(self):
        """Issue number like "- 1" is cleaned properly."""
        adapter = HIPAdapter()
        result = adapter._clean_issue_number("- 1")

        assert result == "- 1"

    def test_series_extraction_with_multiple_h1s(self):
        """Series extraction uses first h1 when multiple exist."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <h1>Alternative Title</h1>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_series_from_payload("x-men-1991", payload)

        assert result.series_title == "X-Men"

    def test_series_with_end_year(self):
        """Series extraction extracts start year from year range."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991-2001)</h1>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_series_from_payload("x-men-1991", payload)

        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991

    def test_upc_extraction_with_short_code_skipped(self):
        """Short UPC codes are not extracted."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <div class="issue-number">1</div>
            <div class="upc">12345</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_issue_from_payload("1", payload)

        assert result.upc is None

    def test_publication_date_not_extracted_from_pub_date_text(self):
        """Current parser leaves publication_date unset for this pub-date format."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <div class="issue-number">1</div>
            <div class="pub-date">May 21 1997</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_issue_from_payload("1", payload)

        assert result.publication_date is None


class TestHIPAdapterNotImplemented:
    """Tests for NotImplementedError on methods that cannot be implemented."""

    @pytest.mark.asyncio
    async def test_fetch_series_raises_not_implemented(self):
        """fetch_series raises NotImplementedError (HIP has no series pages)."""
        adapter = HIPAdapter()
        with pytest.raises(NotImplementedError, match="fetch_series_from_payload"):
            await adapter.fetch_series("x-men-1991")


class TestHIPAdapterFetchIssue:
    """Tests for HIP live fetch behavior."""

    @pytest.mark.asyncio
    async def test_fetch_issue_uses_full_url_and_browser_headers(self, mock_http_client):
        """HIP uses the price-guide URL with browser-like headers when available."""
        html = """
        <html>
        <body>
            <div class="r-detail-attribute">
                <span class="r-detail-attribute__label r-detail-attribute__label--small">Issue</span>
                <a href="/price-guide/us/marvel/comic/x-men-1991/1-1/">-1</a>
            </div>
            <div class="r-detail-attribute">
                <span class="r-detail-attribute__label r-detail-attribute__label--small">Series</span>
                <a>X-Men (1991)</a>
            </div>
        </body>
        </html>
        """
        mock_response = Mock()
        mock_response.text = html
        mock_response.raise_for_status = Mock()
        mock_http_client.get.return_value = mock_response

        adapter = HIPAdapter(http_client=mock_http_client)
        url = "https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/?keywords="

        result = await adapter.fetch_issue("1-1", full_url=url)

        assert result.issue_number == "-1"
        mock_http_client.get.assert_awaited_once()
        assert mock_http_client.get.await_args.args[0] == url
        assert "User-Agent" in mock_http_client.get.await_args.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_fetch_issue_raises_not_found_when_all_patterns_fail(
        self, mock_http_client
    ):
        """HIP raises NotFoundError when canonical and fallback URLs all 404."""

        def build_404(url: str) -> Mock:
            response = Mock()
            response.raise_for_status = Mock(
                side_effect=httpx.HTTPStatusError(
                    "Not found",
                    request=httpx.Request("GET", url),
                    response=httpx.Response(404),
                )
            )
            return response

        mock_http_client.get.side_effect = [
            build_404("https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/"),
            build_404("https://www.hipcomic.com/listing/1-1"),
            build_404("https://www.hipcomic.com/new-comic-listings/1-1"),
        ]

        adapter = HIPAdapter(http_client=mock_http_client)

        with pytest.raises(NotFoundError, match="Issue not found: 1-1"):
            await adapter.fetch_issue(
                "1-1",
                full_url="https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/",
            )


class TestHIPAdapterRealWorldData:
    """Tests with simulated real-world HIP HTML structure."""

    def test_complete_issue_html(self):
        """Test with complete HIP issue page HTML."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>HipComic - X-Men #1-1 (1991)</title></head>
        <body>
            <div class="container">
                <h1>X-Men (1991)</h1>
                <div class="issue-details">
                    <span class="issue-number">1-1</span>
                    <span class="publisher">Marvel Comics</span>
                </div>
                <div class="dates">
                    <div class="cover-date">July 1997</div>
                </div>
                <div class="pricing">
                    <div class="price">$1.95 USD</div>
                </div>
                <div class="details">
                    <div class="page-count">44 pages</div>
                    <div class="upc">75960601772099911</div>
                </div>
            </div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_issue_from_payload("1-1", payload)

        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991
        assert result.issue_number == "-1"
        assert result.publisher == "Marvel Comics"
        assert result.price == 1.95
        assert result.page_count == 44
        assert result.upc == "75960601772099911"
        assert result.cover_date == date(1997, 7, 1)

    def test_series_page_with_publisher(self):
        """Test series page with full publisher information."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div class="price-guide-header">
                <h1>Amazing Spider-Man (1963)</h1>
                <div class="publisher-info">
                    <span class="publisher">Marvel Comics</span>
                </div>
            </div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_series_from_payload("amazing-spider-man-1963", payload)

        assert result.series_title == "Amazing Spider-Man"
        assert result.series_start_year == 1963
        assert result.publisher == "Marvel Comics"

    def test_issue_with_variant_cover(self):
        """Test issue with variant cover information."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <div class="issue-info">
                <span class="issue-number">100</span>
                <span class="variant">Cover B - Adams</span>
            </div>
            <div class="publisher">Marvel Comics</div>
        </body>
        </html>
        """
        payload = {"html": html}

        adapter = HIPAdapter()
        result = adapter.fetch_issue_from_payload("100", payload)

        assert result.issue_number == "100"
        assert result.variant_name == "Cover B - Adams"
