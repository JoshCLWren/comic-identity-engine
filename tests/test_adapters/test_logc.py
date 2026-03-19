"""Tests for LoCG adapter implementation."""

from datetime import date
from unittest.mock import AsyncMock, Mock, patch

import pytest
import httpx

from comic_identity_engine.adapters import LoCGAdapter, ValidationError, NotFoundError


class TestLoCGAdapterSeriesMapping:
    """Tests for LoCG series HTML mapping."""

    def test_successful_series_mapping_from_html(self):
        """LoCG series HTML maps to SeriesCandidate correctly."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
        <title>X-Men (1991) | League of Comic Geeks</title>
        </head>
        <body>
        <h1 class="title">X-Men</h1>
        <p class="publisher">Marvel Comics</p>
        <span class="year">(1991–2001)</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_series_from_html("111275", html)

        assert result.source == "locg"
        assert result.source_series_id == "111275"
        assert result.series_title == "X-Men (1991)"
        assert result.publisher == "Marvel Comics"
        assert result.series_start_year == 1991

    def test_series_title_extraction_from_h1(self):
        """Series title extracted from h1 element."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test | League of Comic Geeks</title></head>
        <body>
        <h1 class="title">Amazing Spider-Man</h1>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_series_from_html("12345", html)

        assert result.series_title == "Amazing Spider-Man"

    def test_missing_series_title(self):
        """Series HTML without title raises ValidationError."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
        <p>No title here</p>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        with pytest.raises(ValidationError, match="missing required field: title"):
            adapter.fetch_series_from_html("111275", html)

    def test_empty_series_html(self):
        """Empty series HTML raises ValidationError."""
        adapter = LoCGAdapter()
        with pytest.raises(ValidationError, match="HTML is empty"):
            adapter.fetch_series_from_html("111275", "")

    def test_series_publisher_extraction(self):
        """Publisher extracted from various HTML patterns."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men (1991) | League of Comic Geeks</title></head>
        <body>
        <a href="/publishers/marvel">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_series_from_html("111275", html)

        assert result.publisher == "Marvel Comics"

    def test_series_year_extraction(self):
        """Series start year extracted from HTML."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men (1991) | League of Comic Geeks</title></head>
        <body>
        <span>(1991–2001)</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_series_from_html("111275", html)

        assert result.series_start_year == 1991


class TestLoCGAdapterIssueMapping:
    """Tests for LoCG issue HTML mapping."""

    def test_successful_issue_mapping_xmen_negative1(self):
        """LoCG issue HTML for X-Men #-1 maps correctly."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
        <title>X-Men #-1 | League of Comic Geeks</title>
        </head>
        <body>
        <h2 class="issue">#-1</h2>
        <a href="/comic/111275">Marvel Comics</a>
        <span>(1991 Series)</span>
        <span class="variant">Direct Edition</span>
        <span class="date">July 1997</span>
        <span class="price">$1.95</span>
        <span class="upc">75960601772099911</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("1169529", html)

        assert result.source == "locg"
        assert result.source_issue_id == "1169529"
        assert result.source_series_id == "111275"
        assert result.series_title == "X-Men #-1"
        assert result.series_start_year == 1991
        assert result.publisher == "Marvel Comics"
        assert result.issue_number == "-1"
        assert result.variant_suffix is None
        assert result.price == 1.95
        assert result.upc == "75960601772099911"

    def test_issue_mapping_with_variant(self):
        """LoCG issue HTML with variant suffix."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
        <title>X-Men #100 | League of Comic Geeks</title>
        </head>
        <body>
        <h2 class="issue">#100</h2>
        <a href="/comic/111275">Marvel Comics</a>
        <span>variant: A</span>
        <span class="variant-name">Adams Cover</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("123456", html)

        assert result.issue_number == "100"
        assert result.variant_suffix == "A"
        assert result.variant_name == "Adams Cover"

    def test_issue_number_extraction_from_title(self):
        """Issue number extracted from title tag."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
        <title>Amazing Spider-Man #50 | League of Comic Geeks</title>
        </head>
        <body>
        <a href="/comic/54321">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("789012", html)

        assert result.issue_number == "50"

    def test_issue_number_extraction_from_h2(self):
        """Issue number extracted from h2 element."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test | League of Comic Geeks</title></head>
        <body>
        <h2 class="issue">#25</h2>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.issue_number == "25"

    def test_missing_series_title(self):
        """Issue HTML without series title raises ValidationError."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
        <h2 class="issue">#1</h2>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: series title"
        ):
            adapter.fetch_issue_from_html("1169529", html)

    def test_missing_issue_number(self):
        """Issue HTML without issue number raises ValidationError."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: issue number"
        ):
            adapter.fetch_issue_from_html("1169529", html)

    def test_invalid_issue_number_format(self):
        """Invalid issue number format raises ValidationError."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1-3 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        with pytest.raises(ValidationError, match="Invalid issue number"):
            adapter.fetch_issue_from_html("1169529", html)

    def test_empty_issue_html(self):
        """Empty issue HTML raises ValidationError."""
        adapter = LoCGAdapter()
        with pytest.raises(ValidationError, match="HTML is empty"):
            adapter.fetch_issue_from_html("1169529", "")

    def test_cover_date_extraction(self):
        """Cover date extracted from HTML."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        <span>October 15, 1991</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.cover_date == date(1991, 10, 15)

    def test_price_extraction(self):
        """Price extracted from HTML."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        <span class="price">$2.99</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.price == 2.99

    def test_upc_extraction(self):
        """UPC extracted from HTML."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        <span>UPC: 75960601772099911</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.upc == "75960601772099911"


class TestLoCGAdapterHTTPMethods:
    """Tests for LoCG adapter HTTP methods."""

    @pytest.mark.asyncio
    async def test_fetch_series_successful_request(self, mock_http_client):
        """Successful HTTP request for series."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men (1991) | League of Comic Geeks</title></head>
        <body>
        <h1 class="title">X-Men</h1>
        <a href="/publishers/marvel">Marvel Comics</a>
        </body>
        </html>
        """

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        adapter = LoCGAdapter(http_client=mock_http_client)
        result = await adapter.fetch_series("111275")

        assert result.series_title == "X-Men (1991)"
        mock_http_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_issue_successful_request(self, mock_http_client):
        """Successful HTTP request for issue."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        adapter = LoCGAdapter(http_client=mock_http_client)
        result = await adapter.fetch_issue("1169529")

        assert result.issue_number == "1"
        mock_http_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_series_not_found(self, mock_http_client):
        """404 response raises NotFoundError."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "Not found", request=Mock(), response=mock_response
            )
        )
        mock_http_client.get = AsyncMock(return_value=mock_response)

        adapter = LoCGAdapter(http_client=mock_http_client)
        with pytest.raises(NotFoundError, match="Series not found"):
            await adapter.fetch_series("999999")

    @pytest.mark.asyncio
    async def test_fetch_issue_not_found(self, mock_http_client):
        """404 response raises NotFoundError."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "Not found", request=Mock(), response=mock_response
            )
        )
        mock_http_client.get = AsyncMock(return_value=mock_response)

        adapter = LoCGAdapter(http_client=mock_http_client)
        with pytest.raises(NotFoundError, match="Issue not found"):
            await adapter.fetch_issue("999999")

    @pytest.mark.asyncio
    async def test_fetch_series_http_error(self, mock_http_client):
        """Non-404 HTTP error raises SourceError."""
        from comic_identity_engine.adapters import SourceError

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "Server error", request=Mock(), response=mock_response
            )
        )
        mock_http_client.get = AsyncMock(return_value=mock_response)

        adapter = LoCGAdapter(http_client=mock_http_client)
        with pytest.raises(SourceError, match="HTTP error"):
            await adapter.fetch_series("111275")

    @pytest.mark.asyncio
    async def test_fetch_issue_network_error(self, mock_http_client):
        """Network error raises SourceError."""
        from comic_identity_engine.adapters import SourceError

        mock_http_client.get = AsyncMock(
            side_effect=httpx.RequestError("Connection failed")
        )

        adapter = LoCGAdapter(http_client=mock_http_client)
        with pytest.raises(SourceError, match="Network error"):
            await adapter.fetch_issue("1169529")


class TestLoCGAdapterHelpers:
    """Tests for LoCG adapter helper methods."""

    def test_extract_series_title_from_html(self):
        """Series title extraction from HTML."""
        adapter = LoCGAdapter()
        html = "<title>X-Men (1991) | League of Comic Geeks</title>"
        result = adapter._extract_series_title_from_html(html)

        assert result == "X-Men (1991)"

    def test_extract_series_title_no_match(self):
        """No title match returns None."""
        adapter = LoCGAdapter()
        html = "<p>No title here</p>"
        result = adapter._extract_series_title_from_html(html)

        assert result is None

    def test_extract_issue_number_from_title(self):
        """Issue number extraction from title tag."""
        adapter = LoCGAdapter()
        html = "<title>X-Men #50 | League of Comic Geeks</title>"
        result = adapter._extract_issue_number_from_html(html)

        assert result == "50"

    def test_extract_issue_number_from_h2(self):
        """Issue number extraction from h2 element."""
        adapter = LoCGAdapter()
        html = '<h2 class="issue">#25</h2>'
        result = adapter._extract_issue_number_from_html(html)

        assert result == "25"

    def test_extract_series_id_from_html(self):
        """Series ID extraction from HTML."""
        adapter = LoCGAdapter()
        html = '<a href="/comic/111275/x-men-1">Link</a>'
        result = adapter._extract_series_id_from_html(html)

        assert result == "111275"

    def test_extract_series_id_no_match(self):
        """No series ID match returns empty string."""
        adapter = LoCGAdapter()
        html = "<p>No series ID here</p>"
        result = adapter._extract_series_id_from_html(html)

        assert result == ""

    def test_extract_publisher_from_html(self):
        """Publisher extraction from HTML."""
        adapter = LoCGAdapter()
        html = '<a href="/publishers/marvel">Marvel Comics</a>'
        result = adapter._extract_publisher_from_html(html)

        assert result == "Marvel Comics"

    def test_extract_publisher_no_match(self):
        """No publisher match returns None."""
        adapter = LoCGAdapter()
        html = "<p>No publisher here</p>"
        result = adapter._extract_publisher_from_html(html)

        assert result is None

    def test_extract_series_start_year_from_html(self):
        """Series start year extraction from HTML."""
        adapter = LoCGAdapter()
        html = "<span>(1991–2001)</span>"
        result = adapter._extract_series_start_year_from_html(html)

        assert result == 1991

    def test_extract_series_start_year_no_match(self):
        """No year match returns None."""
        adapter = LoCGAdapter()
        html = "<p>No year here</p>"
        result = adapter._extract_series_start_year_from_html(html)

        assert result is None

    def test_extract_variant_suffix_from_html(self):
        """Variant suffix extraction from HTML."""
        adapter = LoCGAdapter()
        html = "<span>variant: A</span>"
        result = adapter._extract_variant_suffix_from_html(html)

        assert result == "A"

    def test_extract_variant_suffix_no_match(self):
        """No variant suffix match returns None."""
        adapter = LoCGAdapter()
        html = "<p>No variant here</p>"
        result = adapter._extract_variant_suffix_from_html(html)

        assert result is None

    def test_extract_variant_name_from_html(self):
        """Variant name extraction from HTML."""
        adapter = LoCGAdapter()
        html = '<span class="variant">Adams Cover</span>'
        result = adapter._extract_variant_name_from_html(html)

        assert result == "Adams Cover"

    def test_extract_variant_name_standard_returns_none(self):
        """Standard variant name returns None."""
        adapter = LoCGAdapter()
        html = '<span class="variant">Standard</span>'
        result = adapter._extract_variant_name_from_html(html)

        assert result is None

    def test_extract_cover_date_from_html(self):
        """Cover date extraction from HTML."""
        adapter = LoCGAdapter()
        html = "<span>July 15, 1997</span>"
        result = adapter._extract_cover_date_from_html(html)

        assert result == date(1997, 7, 15)

    def test_extract_cover_date_no_match(self):
        """No date match returns None."""
        adapter = LoCGAdapter()
        html = "<p>No date here</p>"
        result = adapter._extract_cover_date_from_html(html)

        assert result is None

    def test_extract_price_from_html(self):
        """Price extraction from HTML."""
        adapter = LoCGAdapter()
        html = "<span>$2.99</span>"
        result = adapter._extract_price_from_html(html)

        assert result == 2.99

    def test_extract_price_no_match(self):
        """No price match returns None."""
        adapter = LoCGAdapter()
        html = "<p>No price here</p>"
        result = adapter._extract_price_from_html(html)

        assert result is None

    def test_extract_upc_from_html(self):
        """UPC extraction from HTML."""
        adapter = LoCGAdapter()
        html = "<span>UPC: 75960601772099911</span>"
        result = adapter._extract_upc_from_html(html)

        assert result == "75960601772099911"

    def test_extract_upc_no_match(self):
        """No UPC match returns None."""
        adapter = LoCGAdapter()
        html = "<p>No UPC here</p>"
        result = adapter._extract_upc_from_html(html)

        assert result is None


class TestLoCGAdapterEdgeCases:
    """Edge case tests for LoCG adapter to improve coverage."""

    def test_series_title_empty_after_strip(self):
        """Title element exists but is empty after stripping."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>   | League of Comic Geeks</title></head>
        <body>
        <h1 class="title">  </h1>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        with pytest.raises(ValidationError, match="missing required field: title"):
            adapter.fetch_series_from_html("111275", html)

    def test_issue_number_with_decimal(self):
        """Issue number with decimal point."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #0.5 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.issue_number == "0.5"

    def test_issue_number_with_fraction(self):
        """Issue number with fraction."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1/2 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.issue_number == "1/2"

    def test_variant_suffix_multi_letter(self):
        """Multi-letter variant suffix."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        <span>variant: DE</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.variant_suffix == "DE"

    def test_cover_date_iso_format(self):
        """Cover date in ISO format."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        <span>1991-10-15</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.cover_date == date(1991, 10, 15)

    def test_cover_date_invalid_format(self):
        """Invalid cover date format returns None."""
        adapter = LoCGAdapter()
        html = "<span>Invalid Date</span>"
        result = adapter._extract_cover_date_from_html(html)

        assert result is None

    def test_price_invalid_format(self):
        """Invalid price format returns None."""
        adapter = LoCGAdapter()
        html = "<span>$abc</span>"
        result = adapter._extract_price_from_html(html)

        assert result is None

    def test_upc_extraction_from_barcode_field(self):
        """UPC extracted from barcode field."""
        adapter = LoCGAdapter()
        html = "<span>barcode: 75960601772099911</span>"
        result = adapter._extract_upc_from_html(html)

        assert result == "75960601772099911"

    def test_upc_extraction_from_isbn_field(self):
        """UPC extracted from ISBN field."""
        adapter = LoCGAdapter()
        html = "<span>ISBN: 978-0-7851-1234-5</span>"
        result = adapter._extract_upc_from_html(html)

        assert result == "978-0-7851-1234-5"

    def test_upc_too_short(self):
        """UPC that is too short returns None."""
        adapter = LoCGAdapter()
        html = "<span>UPC: 123456789</span>"
        result = adapter._extract_upc_from_html(html)

        assert result is None

    def test_series_year_from_published_text(self):
        """Series year extracted from 'Published' text."""
        adapter = LoCGAdapter()
        html = "<span>Published 1991</span>"
        result = adapter._extract_series_start_year_from_html(html)

        assert result == 1991

    def test_series_year_from_series_text(self):
        """Series year extracted from 'Series' text."""
        adapter = LoCGAdapter()
        html = "<span>1991 Series</span>"
        result = adapter._extract_series_start_year_from_html(html)

        assert result == 1991

    def test_variant_name_none_returns_none(self):
        """Variant name 'None' returns None."""
        adapter = LoCGAdapter()
        html = '<span class="variant">None</span>'
        result = adapter._extract_variant_name_from_html(html)

        assert result is None

    def test_timeout_parameter_stored(self):
        """Timeout parameter is stored."""
        adapter = LoCGAdapter(timeout=60.0)
        assert adapter.timeout == 60.0

    def test_default_timeout(self):
        """Default timeout is 30 seconds."""
        adapter = LoCGAdapter()
        assert adapter.timeout == 30.0

    def test_issue_with_negative_number(self):
        """Issue with negative number like #-1."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #-1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.issue_number == "-1"

    def test_series_with_no_publisher(self):
        """Series without publisher field."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men (1991) | League of Comic Geeks</title></head>
        <body>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_series_from_html("111275", html)

        assert result.publisher is None

    def test_series_with_no_year(self):
        """Series without year field."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men | League of Comic Geeks</title></head>
        <body>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_series_from_html("111275", html)

        assert result.series_start_year is None

    def test_issue_with_no_variant(self):
        """Issue without variant field."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.variant_suffix is None
        assert result.variant_name is None

    def test_issue_with_no_cover_date(self):
        """Issue without cover date field."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.cover_date is None

    def test_issue_with_no_price(self):
        """Issue without price field."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.price is None

    def test_issue_with_no_upc(self):
        """Issue without UPC field."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.upc is None

    def test_issue_with_no_series_year(self):
        """Issue without series year in HTML."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.series_start_year is None

    @pytest.mark.asyncio
    async def test_network_error_fetch_series(self, mock_http_client):
        """Network error when fetching series."""
        from comic_identity_engine.adapters import SourceError

        mock_http_client.get = AsyncMock(
            side_effect=httpx.RequestError("Connection failed")
        )

        adapter = LoCGAdapter(http_client=mock_http_client)
        with pytest.raises(SourceError, match="Network error"):
            await adapter.fetch_series("111275")

    @pytest.mark.asyncio
    async def test_http_error_fetch_issue(self, mock_http_client):
        """HTTP error (non-404) when fetching issue."""
        from comic_identity_engine.adapters import SourceError

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "Server error", request=Mock(), response=mock_response
            )
        )
        mock_http_client.get = AsyncMock(return_value=mock_response)

        adapter = LoCGAdapter(http_client=mock_http_client)
        with pytest.raises(SourceError, match="HTTP error"):
            await adapter.fetch_issue("1169529")

    def test_series_title_h1_fallback(self):
        """Series title extracted from h1 when title tag has no year."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test Series | League of Comic Geeks</title></head>
        <body>
        <h1 class="title">Amazing Spider-Man</h1>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_series_from_html("12345", html)

        assert result.series_title == "Amazing Spider-Man"

    def test_series_year_extraction_error(self):
        """Series year extraction with invalid data."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men | League of Comic Geeks</title></head>
        <body>
        <span>(not-a-year)</span>
        <span>(abc)</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_series_from_html("111275", html)

        assert result.series_start_year is None

    def test_cover_date_extraction_error(self):
        """Cover date extraction with invalid month name."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        <span>NotAMonth 15, 1991</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.cover_date is None

    def test_price_extraction_error(self):
        """Price extraction with non-numeric value."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        <span>$invalid</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.price is None

    def test_issue_number_validates_to_none(self):
        """Test issue number parsing that succeeds but returns None canonical."""

        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        <h2 class="issue">#1</h2>
        </body>
        </html>
        """

        mock_parse_result = Mock()
        mock_parse_result.success = True
        mock_parse_result.canonical_issue_number = None
        mock_parse_result.error_code = None

        with patch(
            "comic_identity_engine.adapters.locg.parse_issue_candidate",
            return_value=mock_parse_result,
        ):
            adapter = LoCGAdapter()
            with pytest.raises(ValidationError, match="produced no canonical form"):
                adapter.fetch_issue_from_html("12345", html)

    def test_series_title_only_h1_no_title(self):
        """Series title extraction when only h1 is present."""
        html = """
        <!DOCTYPE html>
        <html>
        <body>
        <h1 class="title">Batman</h1>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_series_from_html("54321", html)

        assert result.series_title == "Batman"

    def test_series_year_with_value_error(self):
        """Series year extraction when year is not a valid integer."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men | League of Comic Geeks</title></head>
        <body>
        <span>(abcd)</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_series_from_html("111275", html)

        assert result.series_start_year is None

    def test_cover_date_with_invalid_day(self):
        """Cover date extraction with day out of range."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        <span>January 99, 1991</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.cover_date is None

    def test_series_year_with_multiple_invalid_matches(self):
        """Series year extraction with multiple patterns failing."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men | League of Comic Geeks</title></head>
        <body>
        <span>(abcd)</span>
        <span>(efgh)</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_series_from_html("111275", html)

        assert result.series_start_year is None

    def test_cover_date_with_multiple_invalid_matches(self):
        """Cover date extraction with multiple patterns failing."""
        html = """
        <!DOCTYPE html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        <span>NotAMonth 99, 1991</span>
        <span>InvalidMonth 50, 2000</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.cover_date is None

    def test_price_with_multiple_invalid_matches(self):
        """Price extraction with multiple patterns failing."""
        html = """
        <!DOCTYPE html>
        <head><title>X-Men #1 | League of Comic Geeks</title></head>
        <body>
        <a href="/comic/111275">Marvel Comics</a>
        <span>$invalid1</span>
        <span>$invalid2</span>
        </body>
        </html>
        """

        adapter = LoCGAdapter()
        result = adapter.fetch_issue_from_html("12345", html)

        assert result.price is None


class TestLoCGAdapterAsync:
    """Async tests for LoCG adapter to verify async infrastructure works."""

    @pytest.mark.asyncio
    async def test_locg_adapter_has_async_methods(self):
        """Test that LoCG adapter has async fetch methods."""
        adapter = LoCGAdapter()
        # Verify the adapter has the expected async methods
        assert hasattr(adapter, "fetch_series")
        assert hasattr(adapter, "fetch_issue")
        assert hasattr(adapter, "fetch_series_from_html")
        assert hasattr(adapter, "fetch_issue_from_html")

    @pytest.mark.asyncio
    async def test_locg_adapter_can_use_mock_http_client(self, mock_http_client):
        """Test that LoCG adapter works with async mock HTTP client."""
        # Create adapter with mock client
        adapter = LoCGAdapter(http_client=mock_http_client)

        # Setup mock response
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>X-Men (1991) | League of Comic Geeks</title></head>
        <body>
        <h1 class="title">X-Men</h1>
        <a href="/comic/111275">Marvel Comics</a>
        </body>
        </html>
        """
        mock_response = Mock()
        mock_response.text = html
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        # Verify adapter stores the http_client
        assert adapter.http_client is mock_http_client
