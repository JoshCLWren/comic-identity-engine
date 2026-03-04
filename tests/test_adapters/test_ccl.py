"""Tests for CCL adapter implementation."""

from datetime import date
from unittest.mock import Mock, AsyncMock

import pytest

from comic_identity_engine.adapters import CCLAdapter, ValidationError


class TestCCLAdapterFetch:
    """Tests for CCL series payload mapping."""

    def test_successful_series_mapping(self):
        """CCL series HTML payload maps to SeriesCandidate correctly."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
            <a href="/LiveData/Publisher.aspx?id=123">Marvel</a>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_series_from_payload(
            "84ac79ed-2a10-4a38-9b4c-6df3e0db37de", payload
        )

        assert result.source == "ccl"
        assert result.source_series_id == "84ac79ed-2a10-4a38-9b4c-6df3e0db37de"
        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991
        assert result.publisher == "Marvel"

    def test_series_with_content_field(self):
        """Series payload with 'content' field instead of 'html'."""
        html = """
        <html>
        <body>
            <h1>Amazing Spider-Man (1963)</h1>
            <a href="/LiveData/Publisher.aspx?id=456">Marvel</a>
        </body>
        </html>
        """

        payload = {"content": html}

        adapter = CCLAdapter()
        result = adapter.fetch_series_from_payload("test-series-id", payload)

        assert result.series_title == "Amazing Spider-Man"
        assert result.series_start_year == 1963
        assert result.publisher == "Marvel"

    def test_missing_title(self):
        """Series payload without title raises ValidationError."""
        html = """
        <html>
        <body>
            <p>No title here</p>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        with pytest.raises(ValidationError, match="missing required field: title"):
            adapter.fetch_series_from_payload("test-series-id", payload)

    def test_missing_html_field(self):
        """Series payload without html/content raises ValidationError."""
        payload = {"data": "some data"}

        adapter = CCLAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: html/content"
        ):
            adapter.fetch_series_from_payload("test-series-id", payload)

    def test_empty_payload(self):
        """Empty series payload raises ValidationError."""
        adapter = CCLAdapter()
        with pytest.raises(ValidationError, match="payload is empty"):
            adapter.fetch_series_from_payload("test-series-id", {})


class TestCCLAdapterIssueMapping:
    """Tests for CCL issue payload mapping."""

    def test_successful_issue_mapping_xmen_negative1(self):
        """CCL issue HTML payload for X-Men #-1 variant C maps correctly."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue -1-C DF Carlos Pacheco Cover (Signed by Lobdell) 1/500</h1>
            <table>
                <tr><td>Number:</td><td>-1</td></tr>
                <tr><td>Variant:</td><td>C</td></tr>
                <tr><td>Cover Price:</td><td>$1.95</td></tr>
                <tr><td>Publish Date:</td><td>JUL 01 1997</td></tr>
                <tr><td>Sale Date:</td><td>JUL 02 1997</td></tr>
            </table>
            <a href="/LiveData/Publisher.aspx?id=123">Marvel</a>
            <a href="/issues/comic-books/X-Men-1991/page-1/84ac79ed-2a10-4a38-9b4c-6df3e0db37de">All Issues</a>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_issue_from_payload(
            "e6fa653b-d05e-45db-98ee-de21965bedea", payload
        )

        assert result.source == "ccl"
        assert result.source_issue_id == "e6fa653b-d05e-45db-98ee-de21965bedea"
        assert result.source_series_id == "84ac79ed-2a10-4a38-9b4c-6df3e0db37de"
        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991
        assert result.publisher == "Marvel"
        assert result.issue_number == "-1"
        assert result.variant_suffix == "C"
        assert result.cover_date == date(1997, 7, 1)
        assert result.publication_date == date(1997, 7, 2)
        assert result.price == 1.95

    def test_issue_mapping_without_variant(self):
        """CCL issue payload without variant."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue 1 By Marvel</h1>
            <table>
                <tr><td>Number:</td><td>1</td></tr>
                <tr><td>Cover Price:</td><td>$2.50</td></tr>
                <tr><td>Publish Date:</td><td>OCT 10 1991</td></tr>
            </table>
            <a href="/LiveData/Publisher.aspx?id=123">Marvel</a>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_issue_from_payload("test-issue-id", payload)

        assert result.issue_number == "1"
        assert result.variant_suffix is None
        assert result.price == 2.50

    def test_issue_with_lowercase_variant(self):
        """CCL issue payload with lowercase variant converts to uppercase."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue 1-a By Marvel</h1>
            <table>
                <tr><td>Number:</td><td>1</td></tr>
                <tr><td>Variant:</td><td>a</td></tr>
            </table>
            <a href="/LiveData/Publisher.aspx?id=123">Marvel</a>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_issue_from_payload("test-issue-id", payload)

        assert result.variant_suffix == "A"

    def test_issue_with_decimal_number(self):
        """CCL issue payload with decimal issue number."""
        html = """
        <html>
        <body>
            <h1>Amazing Spider-Man (2018) issue 0.1 By Marvel</h1>
            <table>
                <tr><td>Number:</td><td>0.1</td></tr>
                <tr><td>Cover Price:</td><td>$5.99</td></tr>
            </table>
            <a href="/LiveData/Publisher.aspx?id=123">Marvel</a>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_issue_from_payload("test-issue-id", payload)

        assert result.issue_number == "0.1"

    def test_missing_page_title(self):
        """Issue payload without page title raises ValidationError."""
        html = """
        <html>
        <body>
            <p>No title here</p>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        with pytest.raises(ValidationError, match="missing required field: page title"):
            adapter.fetch_issue_from_payload("test-issue-id", payload)

    def test_missing_html_field(self):
        """Issue payload without html/content raises ValidationError."""
        payload = {"data": "some data"}

        adapter = CCLAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: html/content"
        ):
            adapter.fetch_issue_from_payload("test-issue-id", payload)

    def test_empty_issue_payload(self):
        """Empty issue payload raises ValidationError."""
        adapter = CCLAdapter()
        with pytest.raises(ValidationError, match="payload is empty"):
            adapter.fetch_issue_from_payload("test-issue-id", {})

    def test_invalid_issue_number_in_title(self):
        """Issue title with invalid issue number raises ValidationError."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue ABC By Marvel</h1>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: issue number"
        ):
            adapter.fetch_issue_from_payload("test-issue-id", payload)

    def test_issue_without_publisher(self):
        """Issue payload without publisher link still works."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue 1 By Marvel</h1>
            <table>
                <tr><td>Number:</td><td>1</td></tr>
            </table>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_issue_from_payload("test-issue-id", payload)

        assert result.publisher is None

    def test_issue_with_content_field(self):
        """Issue payload with 'content' field instead of 'html'."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue 1 By Marvel</h1>
            <table>
                <tr><td>Number:</td><td>1</td></tr>
            </table>
            <a href="/LiveData/Publisher.aspx?id=123">Marvel</a>
        </body>
        </html>
        """

        payload = {"content": html}

        adapter = CCLAdapter()
        result = adapter.fetch_issue_from_payload("test-issue-id", payload)

        assert result.issue_number == "1"


class TestCCLAdapterHelpers:
    """Tests for CCL adapter helper methods."""

    def test_extract_series_title_with_year(self):
        """Series title with year is extracted correctly."""
        adapter = CCLAdapter()
        title = adapter._extract_series_title_from_part("X-Men (1991)")

        assert title == "X-Men"

    def test_extract_series_title_without_year(self):
        """Series title without year returns as-is."""
        adapter = CCLAdapter()
        title = adapter._extract_series_title_from_part("X-Men")

        assert title == "X-Men"

    def test_extract_issue_number_negative(self):
        """Negative issue number is extracted correctly."""
        adapter = CCLAdapter()
        issue_num = adapter._extract_issue_number_from_part(
            "-1-C DF Carlos Pacheco Cover"
        )

        assert issue_num == "-1"

    def test_extract_issue_number_decimal(self):
        """Decimal issue number is extracted correctly."""
        adapter = CCLAdapter()
        issue_num = adapter._extract_issue_number_from_part("0.5 Some Description")

        assert issue_num == "0.5"

    def test_extract_start_year_from_title(self):
        """Start year is extracted from series title."""
        adapter = CCLAdapter()
        year = adapter._extract_start_year_from_title("X-Men (1991)")

        assert year == 1991

    def test_extract_start_year_no_year(self):
        """Title without year returns None."""
        adapter = CCLAdapter()
        year = adapter._extract_start_year_from_title("X-Men")

        assert year is None

    def test_parse_date_string_july_1997(self):
        """Date string 'JUL 01 1997' is parsed correctly."""
        adapter = CCLAdapter()
        result = adapter._parse_date_string("JUL 01 1997")

        assert result == date(1997, 7, 1)

    def test_parse_date_string_with_comma(self):
        """Date string with comma is parsed correctly."""
        adapter = CCLAdapter()
        result = adapter._parse_date_string("Jul 01, 1997")

        assert result == date(1997, 7, 1)

    def test_parse_date_string_lowercase(self):
        """Lowercase date string is parsed correctly."""
        adapter = CCLAdapter()
        result = adapter._parse_date_string("oct 10 1991")

        assert result == date(1991, 10, 10)

    def test_parse_date_string_invalid(self):
        """Invalid date string returns None."""
        adapter = CCLAdapter()
        result = adapter._parse_date_string("invalid date")

        assert result is None

    def test_parse_date_string_empty(self):
        """Empty date string returns None."""
        adapter = CCLAdapter()
        result = adapter._parse_date_string("")

        assert result is None

    def test_parse_date_string_none(self):
        """None date string returns None."""
        adapter = CCLAdapter()
        result = adapter._parse_date_string(None)

        assert result is None

    def test_extract_price_dollar_sign(self):
        """Price with dollar sign is extracted correctly."""
        adapter = CCLAdapter()
        result = adapter._parse_price_string("$1.95")

        assert result == 1.95

    def test_extract_price_no_dollar_sign(self):
        """Price without dollar sign is extracted correctly."""
        adapter = CCLAdapter()
        result = adapter._parse_price_string("2.50")

        assert result == 2.50


class TestCCLAdapterEdgeCases:
    """Edge case tests for CCL adapter to improve coverage."""

    def test_series_with_whitespace_title(self):
        """Series title with extra whitespace is trimmed."""
        html = """
        <html>
        <body>
            <h1>   X-Men   (1991)   </h1>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_series_from_payload("test-series-id", payload)

        assert result.series_title == "X-Men"

    def test_issue_with_missing_series_id(self):
        """Issue without series ID link returns empty string."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue 1 By Marvel</h1>
            <table>
                <tr><td>Number:</td><td>1</td></tr>
            </table>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_issue_from_payload("test-issue-id", payload)

        assert result.source_series_id == ""

    def test_parse_page_title_malformed(self):
        """Malformed page title returns None for all parts."""
        adapter = CCLAdapter()
        series_title, series_title_full, issue_number = adapter._parse_page_title(
            "Invalid Title Format"
        )

        assert series_title is None
        assert series_title_full is None
        assert issue_number is None

    def test_parse_page_title_no_issue_word(self):
        """Title without 'issue' word returns None."""
        adapter = CCLAdapter()
        series_title, series_title_full, issue_number = adapter._parse_page_title(
            "X-Men (1991) Something Else"
        )

        assert series_title is None
        assert series_title_full is None
        assert issue_number is None

    def test_extract_series_id_malformed_link(self):
        """Malformed series link returns empty string."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = '<a href="/issues/comic-books/X-Men-1991/page-1/invalid-uuid">All Issues</a>'
        parser = LexborHTMLParser(html)

        result = adapter._extract_series_id_from_parser(parser)

        assert result == ""

    def test_extract_variant_non_alpha(self):
        """Variant with non-alpha characters returns None."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = """
        <table>
            <tr><td>Variant:</td><td>123</td></tr>
        </table>
        """
        parser = LexborHTMLParser(html)

        result = adapter._extract_variant_from_parser(parser)

        assert result is None

    def test_extract_variant_multi_char(self):
        """Variant with multiple characters returns None."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = """
        <table>
            <tr><td>Variant:</td><td>ABC</td></tr>
        </table>
        """
        parser = LexborHTMLParser(html)

        result = adapter._extract_variant_from_parser(parser)

        assert result is None

    def test_extract_price_invalid_format(self):
        """Price with invalid format returns None."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = """
        <table>
            <tr><td>Cover Price:</td><td>priceless</td></tr>
        </table>
        """
        parser = LexborHTMLParser(html)

        result = adapter._extract_price(parser)

        assert result is None

    def test_extract_publisher_no_link(self):
        """HTML without publisher link returns None."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = "<html><body><p>No publisher link</p></body></html>"
        parser = LexborHTMLParser(html)

        result = adapter._extract_publisher(parser)

        assert result is None

    def test_series_with_no_publisher(self):
        """Series without publisher link still works."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991)</h1>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_series_from_payload("test-series-id", payload)

        assert result.publisher is None

    def test_extract_variant_no_variant_row(self):
        """HTML without variant row returns None."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = """
        <table>
            <tr><td>Number:</td><td>1</td></tr>
        </table>
        """
        parser = LexborHTMLParser(html)

        result = adapter._extract_variant_from_parser(parser)

        assert result is None

    def test_extract_price_no_price_row(self):
        """HTML without price row returns None."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = """
        <table>
            <tr><td>Number:</td><td>1</td></tr>
        </table>
        """
        parser = LexborHTMLParser(html)

        result = adapter._extract_price(parser)

        assert result is None

    def test_parse_date_string_wrong_format(self):
        """Date string in wrong format returns None."""
        adapter = CCLAdapter()
        result = adapter._parse_date_string("1997-07-01")

        assert result is None

    def test_parse_price_string_invalid(self):
        """Invalid price string returns None."""
        adapter = CCLAdapter()
        result = adapter._parse_price_string("abc")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_series_404_raises_not_found(self, mock_http_client):
        """fetch_series() raises NotFoundError on 404."""
        import httpx

        mock_request = Mock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=mock_request, response=mock_response
        )
        mock_http_client.get = AsyncMock(return_value=mock_response)

        adapter = CCLAdapter(http_client=mock_http_client)
        from comic_identity_engine.adapters import NotFoundError

        with pytest.raises(NotFoundError, match="Series not found"):
            await adapter.fetch_series("12345")

    @pytest.mark.asyncio
    async def test_fetch_issue_404_raises_not_found(self, mock_http_client):
        """fetch_issue() raises NotFoundError on 404."""
        import httpx

        mock_request = Mock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=mock_request, response=mock_response
        )
        mock_http_client.get = AsyncMock(return_value=mock_response)

        adapter = CCLAdapter(http_client=mock_http_client)
        from comic_identity_engine.adapters import NotFoundError

        with pytest.raises(NotFoundError, match="Issue not found"):
            await adapter.fetch_issue("28636")

    def test_extract_date_by_label_no_match(self):
        """Date extraction with no matching label returns None."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = """
        <table>
            <tr><td>Other Label:</td><td>JUL 01 1997</td></tr>
        </table>
        """
        parser = LexborHTMLParser(html)

        result = adapter._extract_date_by_label(parser, "publish date:")

        assert result is None

    def test_issue_title_without_series(self):
        """Issue title without series part raises ValidationError."""
        html = """
        <html>
        <body>
            <h1>issue 1 By Marvel</h1>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: series title"
        ):
            adapter.fetch_issue_from_payload("test-issue-id", payload)

    def test_issue_title_without_issue_number(self):
        """Issue title without issue number raises ValidationError."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue By Marvel</h1>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: issue number"
        ):
            adapter.fetch_issue_from_payload("test-issue-id", payload)

    def test_multi_issue_range_in_title(self):
        """Issue title with multi-issue range raises ValidationError."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue 1-3 By Marvel</h1>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: issue number"
        ):
            adapter.fetch_issue_from_payload("test-issue-id", payload)

    def test_issue_title_variant_in_number(self):
        """Issue with variant letter in title extracts correctly."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue 1A By Marvel</h1>
            <table>
                <tr><td>Number:</td><td>1</td></tr>
            </table>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_issue_from_payload("test-issue-id", payload)

        assert result.issue_number == "1"

    def test_series_year_extraction_from_series_html(self):
        """Series year extraction from HTML works correctly."""
        html = """
        <html>
        <body>
            <h1>Amazing Spider-Man (1963)</h1>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_series_from_payload("test-series-id", payload)

        assert result.series_start_year == 1963

    def test_parse_issue_number_from_complex_string(self):
        """Issue number extraction from complex string works."""
        adapter = CCLAdapter()
        issue_num = adapter._extract_issue_number_from_part("1/2-HU Variant")

        assert issue_num == "1/2"

    def test_series_title_parsing_with_parentheses_in_name(self):
        """Series title with extra parentheses is handled."""
        adapter = CCLAdapter()
        title = adapter._extract_series_title_from_part("X-Men (1991) (Vol. 2)")

        assert title == "X-Men"

    def test_parse_month_names_case_insensitive(self):
        """All month names are parsed case-insensitively."""
        adapter = CCLAdapter()

        months = [
            ("JAN 01 2020", date(2020, 1, 1)),
            ("Feb 15 2020", date(2020, 2, 15)),
            ("MAR 31 2020", date(2020, 3, 31)),
            ("apr 10 2020", date(2020, 4, 10)),
            ("May 05 2020", date(2020, 5, 5)),
            ("JUN 20 2020", date(2020, 6, 20)),
            ("jul 25 2020", date(2020, 7, 25)),
            ("Aug 12 2020", date(2020, 8, 12)),
            ("SEP 08 2020", date(2020, 9, 8)),
            ("oct 30 2020", date(2020, 10, 30)),
            ("Nov 22 2020", date(2020, 11, 22)),
            ("dec 18 2020", date(2020, 12, 18)),
        ]

        for date_str, expected in months:
            result = adapter._parse_date_string(date_str)
            assert result == expected, f"Failed for {date_str}"

    def test_extract_variant_lowercase(self):
        """Lowercase variant is converted to uppercase."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = """
        <table>
            <tr><td>Variant:</td><td>b</td></tr>
        </table>
        """
        parser = LexborHTMLParser(html)

        result = adapter._extract_variant_from_parser(parser)

        assert result == "B"

    def test_price_extraction_with_whitespace(self):
        """Price extraction handles whitespace."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = """
        <table>
            <tr><td>Cover Price:</td><td> $ 1.95 </td></tr>
        </table>
        """
        parser = LexborHTMLParser(html)

        result = adapter._extract_price(parser)

        assert result == 1.95

    def test_series_id_extraction_from_different_url_format(self):
        """Series ID extraction handles different URL formats."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = '<a href="https://www.comiccollectorlive.com/issues/comic-books/X-Men-1991/page-1/84ac79ed-2a10-4a38-9b4c-6df3e0db37de">All Issues</a>'
        parser = LexborHTMLParser(html)

        result = adapter._extract_series_id_from_parser(parser)

        assert result == "84ac79ed-2a10-4a38-9b4c-6df3e0db37de"

    def test_empty_html_string(self):
        """Empty HTML string is handled gracefully."""
        html = ""

        payload = {"html": html}

        adapter = CCLAdapter()
        with pytest.raises(ValidationError, match="missing required field"):
            adapter.fetch_issue_from_payload("test-issue-id", payload)

    def test_whitespace_only_html(self):
        """Whitespace-only HTML is handled gracefully."""
        html = "   \n\n   "

        payload = {"html": html}

        adapter = CCLAdapter()
        with pytest.raises(ValidationError, match="missing required field"):
            adapter.fetch_issue_from_payload("test-issue-id", payload)

    def test_issue_with_fractional_number(self):
        """Fractional issue number is parsed correctly."""
        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue 1/2 By Marvel</h1>
            <table>
                <tr><td>Number:</td><td>1/2</td></tr>
            </table>
            <a href="/LiveData/Publisher.aspx?id=123">Marvel</a>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_issue_from_payload("test-issue-id", payload)

        assert result.issue_number == "1/2"

    def test_extract_start_year_none_title(self):
        """None title returns None."""
        adapter = CCLAdapter()
        result = adapter._extract_start_year_from_title(None)
        assert result is None

    def test_extract_start_year_invalid_year(self):
        """Invalid year in parentheses returns None."""
        adapter = CCLAdapter()
        result = adapter._extract_start_year_from_title("X-Men (abcd)")
        assert result is None

    def test_extract_series_title_no_parentheses(self):
        """Series title without parentheses returns full title."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = "<html><body><h1>X-Men</h1></body></html>"
        parser = LexborHTMLParser(html)

        result = adapter._extract_series_title(parser)

        assert result == "X-Men"

    def test_series_year_no_parentheses(self):
        """Series without year in title returns None."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = "<html><body><h1>X-Men</h1></body></html>"
        parser = LexborHTMLParser(html)

        result = adapter._extract_series_year(parser)

        assert result is None

    def test_issue_parsing_with_slash_variant(self):
        """Issue with slash variant is handled correctly."""
        adapter = CCLAdapter()

        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue 1/2 By Marvel</h1>
            <table>
                <tr><td>Number:</td><td>1/2</td></tr>
            </table>
            <a href="/LiveData/Publisher.aspx?id=123">Marvel</a>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()
        result = adapter.fetch_issue_from_payload("test-issue-id", payload)

        assert result.issue_number == "1/2"

    def test_parse_price_string_empty(self):
        """Empty price string returns None."""
        adapter = CCLAdapter()
        result = adapter._parse_price_string("")
        assert result is None

    def test_parse_price_string_none(self):
        """None price string returns None."""
        adapter = CCLAdapter()
        result = adapter._parse_price_string(None)
        assert result is None

    def test_parse_date_string_invalid_date(self):
        """Valid format but invalid date values return None."""
        adapter = CCLAdapter()
        result = adapter._parse_date_string("FEB 30 2020")
        assert result is None

    def test_issue_parsing_succeeds_but_validation_fails(self):
        """Issue number extracts but parse_issue_candidate fails."""
        from unittest.mock import patch

        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue 999 By Marvel</h1>
            <table>
                <tr><td>Number:</td><td>999</td></tr>
            </table>
            <a href="/LiveData/Publisher.aspx?id=123">Marvel</a>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()

        with patch(
            "comic_identity_engine.adapters.ccl.parse_issue_candidate"
        ) as mock_parse:
            mock_result = Mock()
            mock_result.success = False
            mock_result.error_code = "TEST_ERROR"
            mock_parse.return_value = mock_result

            with pytest.raises(ValidationError, match="Invalid issue number"):
                adapter.fetch_issue_from_payload("test-issue-id", payload)

    def test_issue_parse_success_but_no_canonical(self):
        """parse_issue_candidate returns success but no canonical number."""
        from unittest.mock import patch

        html = """
        <html>
        <body>
            <h1>X-Men (1991) issue 1 By Marvel</h1>
            <table>
                <tr><td>Number:</td><td>1</td></tr>
            </table>
            <a href="/LiveData/Publisher.aspx?id=123">Marvel</a>
        </body>
        </html>
        """

        payload = {"html": html}

        adapter = CCLAdapter()

        with patch(
            "comic_identity_engine.adapters.ccl.parse_issue_candidate"
        ) as mock_parse:
            mock_result = Mock()
            mock_result.success = True
            mock_result.canonical_issue_number = None
            mock_parse.return_value = mock_result

            with pytest.raises(
                ValidationError,
                match="parsed successfully but produced no canonical form",
            ):
                adapter.fetch_issue_from_payload("test-issue-id", payload)

    def test_extract_start_year_invalid_conversion(self):
        """ValueError when converting non-numeric year returns None."""
        adapter = CCLAdapter()
        from unittest.mock import patch

        with patch("comic_identity_engine.adapters.ccl.re.search") as mock_search:
            mock_match = Mock()
            mock_match.group.return_value = "abcd"  # Invalid year
            mock_search.return_value = mock_match

            result = adapter._extract_start_year_from_title("X-Men (abcd)")
            assert result is None

    def test_series_year_no_h1_element(self):
        """Series year extraction with no h1 element returns None."""
        adapter = CCLAdapter()
        from selectolax.lexbor import LexborHTMLParser

        html = "<html><body><p>No h1 here</p></body></html>"
        parser = LexborHTMLParser(html)

        result = adapter._extract_series_year(parser)

        assert result is None

    def test_parse_price_value_error(self):
        """ValueError when parsing price returns None."""
        adapter = CCLAdapter()
        from unittest.mock import patch

        with patch("comic_identity_engine.adapters.ccl.re.search") as mock_search:
            mock_match = Mock()
            mock_match.group.return_value = "invalid"  # Can't convert to float
            mock_search.return_value = mock_match

            result = adapter._parse_price_string("$invalid")
            assert result is None
