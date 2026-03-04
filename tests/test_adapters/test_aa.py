"""Tests for Atomic Avenue (AA) adapter implementation."""

import pytest

from comic_identity_engine.adapters import AAAdapter, ValidationError


# Fixed UUID constants for deterministic tests
FIXED_SERIES_UUID = "00000000-0000-0000-0000-000000000001"
FIXED_ISSUE_UUID = "00000000-0000-0000-0000-000000000002"


class TestAAAdapterSeriesMapping:
    """Tests for AA series HTML mapping."""

    def test_successful_series_mapping(self):
        """AA series HTML maps to SeriesCandidate correctly."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
            <div class="dropLeftMargin">
                <img src="https://atomicavenue.com/images/flags/pngs/United States.png" alt="US" />
                Marvel, 1983-1994
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_series_from_html("20384", html)

        assert result.source == "aa"
        assert result.source_series_id == "20384"
        assert result.series_title == "Alpha Flight (1st Series)"
        assert result.series_start_year == 1983
        assert result.series_end_year == 1994
        assert result.publisher == "Marvel"

    def test_series_without_end_year(self):
        """Series HTML without end year maps correctly."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
            <div class="dropLeftMargin">
                <img src="https://atomicavenue.com/images/flags/pngs/United States.png" alt="US" />
                Marvel, 1983
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_series_from_html("20384", html)

        assert result.series_start_year == 1983
        assert result.series_end_year is None

    def test_missing_series_title(self):
        """Series HTML without title raises ValidationError."""
        html = """
        <html>
        <body>
            <div class="dropLeftMargin">
                <img src="https://atomicavenue.com/images/flags/pngs/United States.png" alt="US" />
                Marvel, 1983-1994
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: series_title"
        ):
            adapter.fetch_series_from_html("20384", html)

    def test_empty_html(self):
        """Empty series HTML raises ValidationError."""
        adapter = AAAdapter()
        with pytest.raises(ValidationError, match="HTML is empty"):
            adapter.fetch_series_from_html("20384", "")

    def test_series_with_publisher_only(self):
        """Series HTML with only publisher and year."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
            <div class="dropLeftMargin">
                Marvel, 1983-1994
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_series_from_html("20384", html)

        assert result.publisher == "Marvel"
        assert result.series_start_year == 1983
        assert result.series_end_year == 1994


class TestAAAdapterIssueMapping:
    """Tests for AA issue HTML mapping."""

    def test_successful_issue_mapping(self):
        """AA issue HTML maps to IssueCandidate correctly."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
            <div class="dropLeftMargin">
                <img src="https://atomicavenue.com/images/flags/pngs/United States.png" alt="US" />
                Marvel, 1983-1994
            </div>
            <div class="issueInfo">
                <span class="issueSearchIssueNum"><b>37</b></span>
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_issue_from_html("209583", html)

        assert result.source == "aa"
        assert result.source_issue_id == "209583"
        assert result.source_series_id == "20384"
        assert result.series_title == "Alpha Flight (1st Series)"
        assert result.series_start_year == 1983
        assert result.publisher == "Marvel"
        assert result.issue_number == "37"
        assert result.variant_suffix is None

    def test_issue_with_variant(self):
        """AA issue HTML with variant suffix."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
            <div class="dropLeftMargin">
                Marvel, 1983-1994
            </div>
            <div class="issueInfo">
                <span class="issueSearchIssueNum"><b>37A</b></span>
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_issue_from_html("209583", html)

        assert result.issue_number == "37"
        assert result.variant_suffix == "A"

    def test_issue_with_dotted_variant(self):
        """AA issue HTML with dotted variant suffix."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
            <div class="dropLeftMargin">
                Marvel, 1983-1994
            </div>
            <div class="issueInfo">
                <span class="issueSearchIssueNum"><b>37.B</b></span>
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_issue_from_html("209583", html)

        assert result.issue_number == "37"
        assert result.variant_suffix == "B"

    def test_issue_with_multi_letter_variant(self):
        """AA issue HTML with multi-letter variant suffix."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
            <div class="dropLeftMargin">
                Marvel, 1983-1994
            </div>
            <div class="issueInfo">
                <span class="issueSearchIssueNum"><b>37DE</b></span>
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_issue_from_html("209583", html)

        assert result.issue_number == "37"
        assert result.variant_suffix == "DE"

    def test_missing_series_title_in_issue(self):
        """Issue HTML without series title raises ValidationError."""
        html = """
        <html>
        <body>
            <div class="dropLeftMargin">
                Marvel, 1983-1994
            </div>
            <div class="issueInfo">
                <span class="issueSearchIssueNum"><b>37</b></span>
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: series_title"
        ):
            adapter.fetch_issue_from_html("209583", html)

    def test_missing_issue_number(self):
        """Issue HTML without issue number raises ValidationError."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
            <div class="dropLeftMargin">
                Marvel, 1983-1994
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: issue_number"
        ):
            adapter.fetch_issue_from_html("209583", html)

    def test_invalid_issue_number_format(self):
        """Invalid issue number format raises ValidationError."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
            <div class="dropLeftMargin">
                Marvel, 1983-1994
            </div>
            <div class="issueInfo">
                <span class="issueSearchIssueNum"><b>1-3</b></span>
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: issue_number"
        ):
            adapter.fetch_issue_from_html("209583", html)

    def test_empty_issue_html(self):
        """Empty issue HTML raises ValidationError."""
        adapter = AAAdapter()
        with pytest.raises(ValidationError, match="HTML is empty"):
            adapter.fetch_issue_from_html("209583", "")


class TestAAAdapterHelpers:
    """Tests for AA adapter helper methods."""

    def test_extract_series_title(self):
        """Series title is extracted correctly."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
        </body>
        </html>
        """

        adapter = AAAdapter()
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)
        result = adapter._extract_series_title(parser)

        assert result == "Alpha Flight (1st Series)"

    def test_extract_series_title_without_link(self):
        """Series title is extracted from h2 without link."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                Alpha Flight (1st Series)
            </h2>
        </body>
        </html>
        """

        adapter = AAAdapter()
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)
        result = adapter._extract_series_title(parser)

        assert result == "Alpha Flight (1st Series)"

    def test_extract_series_metadata_full(self):
        """Series metadata with publisher and years is extracted correctly."""
        html = """
        <html>
        <body>
            <div class="dropLeftMargin">
                <img src="https://atomicavenue.com/images/flags/pngs/United States.png" alt="US" />
                Marvel, 1983-1994
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)
        publisher, start_year, end_year = adapter._extract_series_metadata(parser)

        assert publisher == "Marvel"
        assert start_year == 1983
        assert end_year == 1994

    def test_extract_series_metadata_no_end_year(self):
        """Series metadata without end year."""
        html = """
        <html>
        <body>
            <div class="dropLeftMargin">
                Marvel, 1983
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)
        publisher, start_year, end_year = adapter._extract_series_metadata(parser)

        assert publisher == "Marvel"
        assert start_year == 1983
        assert end_year is None

    def test_extract_series_metadata_missing(self):
        """Missing series metadata returns None values."""
        html = """
        <html>
        <body>
            <div class="dropLeftMargin">
                Some text without year info
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)
        publisher, start_year, end_year = adapter._extract_series_metadata(parser)

        assert publisher is None
        assert start_year is None
        assert end_year is None

    def test_extract_issue_number(self):
        """Issue number is extracted correctly."""
        html = """
        <html>
        <body>
            <div class="issueInfo">
                <span class="issueSearchIssueNum"><b>37</b></span>
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)
        result = adapter._extract_issue_number(parser)

        assert result == "37"

    def test_extract_issue_number_missing_element(self):
        """Missing issue number element returns None."""
        html = """
        <html>
        <body>
            <div>No issue info here</div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)
        result = adapter._extract_issue_number(parser)

        assert result is None

    def test_extract_series_id_from_html(self):
        """Series ID is extracted from link href."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
        </body>
        </html>
        """

        adapter = AAAdapter()
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)
        result = adapter._extract_series_id_from_html(parser)

        assert result == "20384"

    def test_extract_series_id_missing_link(self):
        """Missing series link returns empty string."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                Alpha Flight (1st Series)
            </h2>
        </body>
        </html>
        """

        adapter = AAAdapter()
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)
        result = adapter._extract_series_id_from_html(parser)

        assert result == ""


class TestAAAdapterEdgeCases:
    """Edge case tests for AA adapter to improve coverage."""

    def test_series_with_none_html(self):
        """Series with None HTML raises ValidationError."""
        adapter = AAAdapter()
        with pytest.raises(ValidationError, match="HTML is empty"):
            adapter.fetch_series_from_html("20384", None)

    def test_issue_with_none_html(self):
        """Issue with None HTML raises ValidationError."""
        adapter = AAAdapter()
        with pytest.raises(ValidationError, match="HTML is empty"):
            adapter.fetch_issue_from_html("209583", None)

    def test_series_with_whitespace_only(self):
        """Series with whitespace-only HTML still parses title."""
        html = """
        <html>
        <body>

            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>

        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_series_from_html("20384", html)

        assert result.series_title == "Alpha Flight (1st Series)"

    def test_issue_number_with_decimal(self):
        """Issue number with decimal is parsed correctly."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
            <div class="dropLeftMargin">
                Marvel, 1983-1994
            </div>
            <div class="issueInfo">
                <span class="issueSearchIssueNum"><b>0.5</b></span>
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_issue_from_html("209583", html)

        assert result.issue_number == "0.5"

    def test_issue_number_with_negative(self):
        """Issue number with negative is parsed correctly."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/20384/1/Alpha-Flight-1st-Series">
                    Alpha Flight (1st Series)
                </a>
            </h2>
            <div class="dropLeftMargin">
                Marvel, 1983-1994
            </div>
            <div class="issueInfo">
                <span class="issueSearchIssueNum"><b>-1</b></span>
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_issue_from_html("209583", html)

        assert result.issue_number == "-1"

    def test_series_title_with_unicode(self):
        """Series title with Unicode characters is handled."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/12345/1/Test-Série">
                    Test Série
                </a>
            </h2>
            <div class="dropLeftMargin">
                Éditeur, 2020
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_series_from_html("12345", html)

        assert result.series_title == "Test Série"
        assert result.publisher == "Éditeur"

    def test_publisher_with_multiple_words(self):
        """Publisher with multiple words is extracted correctly."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/12345/1/Test-Series">
                    Test Series
                </a>
            </h2>
            <div class="dropLeftMargin">
                DC Comics, 2020
            </div>
        </body>
        </html>
        """

        adapter = AAAdapter()
        result = adapter.fetch_series_from_html("12345", html)

        assert result.publisher == "DC Comics"

    def test_series_metadata_div_missing(self):
        """Missing metadata div returns None values."""
        html = """
        <html>
        <body>
            <h2 class="dropLeftMargin">
                <a href="https://atomicavenue.com/atomic/series/12345/1/Test-Series">
                    Test Series
                </a>
            </h2>
        </body>
        </html>
        """

        adapter = AAAdapter()
        from selectolax.lexbor import LexborHTMLParser

        parser = LexborHTMLParser(html)
        publisher, start_year, end_year = adapter._extract_series_metadata(parser)

        assert publisher is None
        assert start_year is None
        assert end_year is None


class TestAAAdapterRealData:
    """Tests using actual AA HTML responses."""

    @pytest.mark.skip(reason="Real HTML files not available in Docker environment")
    def test_alpha_flight_37_real_html(self):
        """Test with actual Alpha Flight #37 AA HTML."""
        pass

    @pytest.mark.skip(reason="Real HTML files not available in Docker environment")
    def test_alpha_flight_series_real_html(self):
        """Test with actual Alpha Flight series AA HTML."""
        pass
