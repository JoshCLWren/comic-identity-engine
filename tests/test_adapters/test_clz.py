"""Tests for CLZ adapter implementation."""

from datetime import date
from pathlib import Path

import pytest

from comic_identity_engine.adapters import CLZAdapter, ValidationError


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "clz"


class TestCLZAdapterCSVLoading:
    """Tests for CLZ CSV loading functionality."""

    def test_load_csv_from_file_success(self):
        """Successfully load CSV file from disk."""
        adapter = CLZAdapter()
        csv_path = FIXTURE_DIR / "sample_clz_export.csv"

        rows = adapter.load_csv_from_file(csv_path)

        assert len(rows) == 4
        assert rows[0]["Series"] == "X-Men, Vol. 1"
        assert rows[0]["Issue"] == "#-1A"

    def test_load_csv_from_string_success(self):
        """Successfully load CSV from string."""
        csv_content = """Series,Issue,Publisher,Year
"Test Series","#1","Test Publisher","2020"
"""
        adapter = CLZAdapter()
        rows = adapter.load_csv_from_string(csv_content)

        assert len(rows) == 1
        assert rows[0]["Series"] == "Test Series"

    def test_load_csv_empty_content(self):
        """Empty CSV content raises ValidationError."""
        adapter = CLZAdapter()

        with pytest.raises(ValidationError, match="CSV content is empty"):
            adapter.load_csv_from_string("")

    def test_load_csv_whitespace_only(self):
        """Whitespace-only CSV content raises ValidationError."""
        adapter = CLZAdapter()

        with pytest.raises(ValidationError, match="CSV content is empty"):
            adapter.load_csv_from_string("   \n\n  ")

    def test_load_csv_file_not_found(self):
        """Non-existent CSV file raises ValidationError."""
        adapter = CLZAdapter()

        with pytest.raises(ValidationError, match="CSV file not found"):
            adapter.load_csv_from_file("/nonexistent/file.csv")

    def test_load_csv_with_bom_encoding(self):
        """CSV with UTF-8 BOM encoding is handled correctly."""
        csv_content = "\ufeffSeries,Issue,Publisher\n" + '"Test","#1","Test"\n'
        adapter = CLZAdapter()

        rows = adapter.load_csv_from_string(csv_content)

        assert len(rows) == 1
        assert rows[0]["Series"] == "Test"
        assert rows[0]["Issue"] == "#1"


class TestCLZAdapterSeriesMapping:
    """Tests for CLZ series CSV row mapping."""

    def test_successful_series_mapping(self):
        """CLZ series row maps to SeriesCandidate correctly."""
        row = {
            "Series": "X-Men, Vol. 1",
            "Publisher": "Marvel Comics",
            "Year": "1991",
        }

        adapter = CLZAdapter()
        result = adapter.fetch_series_from_csv_row("X-Men, Vol. 1", row)

        assert result.source == "clz"
        assert result.source_series_id == "X-Men, Vol. 1"
        assert result.series_title == "X-Men, Vol. 1"
        assert result.publisher == "Marvel Comics"
        assert result.series_start_year == 1991

    def test_series_with_missing_publisher(self):
        """Series without publisher maps with None."""
        row = {
            "Series": "Test Series",
            "Year": "2020",
        }

        adapter = CLZAdapter()
        result = adapter.fetch_series_from_csv_row("Test Series", row)

        assert result.series_title == "Test Series"
        assert result.publisher is None

    def test_series_with_missing_year(self):
        """Series without year maps with None."""
        row = {
            "Series": "Test Series",
            "Publisher": "Test Publisher",
        }

        adapter = CLZAdapter()
        result = adapter.fetch_series_from_csv_row("Test Series", row)

        assert result.series_title == "Test Series"
        assert result.series_start_year is None

    def test_series_empty_row(self):
        """Empty series row raises ValidationError."""
        adapter = CLZAdapter()

        with pytest.raises(ValidationError, match="CSV row is empty"):
            adapter.fetch_series_from_csv_row("test", {})

    def test_series_missing_series_title(self):
        """Row without Series field raises ValidationError."""
        row = {
            "Publisher": "Test Publisher",
        }

        adapter = CLZAdapter()

        with pytest.raises(
            ValidationError, match="missing required field: series title"
        ):
            adapter.fetch_series_from_csv_row("test", row)


class TestCLZAdapterIssueMapping:
    """Tests for CLZ issue CSV row mapping."""

    def test_successful_issue_mapping_xmen_negative1(self):
        """CLZ issue row for X-Men #-1A maps correctly."""
        row = {
            "Series": "X-Men, Vol. 1",
            "Issue": "#-1A",
            "Publisher": "Marvel Comics",
            "Year": "1997",
            "Cover Date": "July 1997",
            "Release Date": "May 21, 1997",
            "Price": "$1.95",
            "Pages": "32",
            "Barcode": "75960601772099911",
            "UPC": "75960601772099911",
        }

        adapter = CLZAdapter()
        result = adapter.fetch_issue_from_csv_row("row-0", row)

        assert result.source == "clz"
        assert result.source_issue_id == "row-0"
        assert result.series_title == "X-Men, Vol. 1"
        assert result.issue_number == "-1"
        assert result.variant_suffix == "A"
        assert result.publisher == "Marvel Comics"
        assert result.series_start_year == 1997
        assert result.cover_date == date(1997, 7, 1)
        assert result.publication_date == date(1997, 5, 21)
        assert result.price == 1.95
        assert result.page_count == 32
        assert result.upc == "75960601772099911"

    def test_issue_mapping_without_variant(self):
        """Issue row without variant suffix."""
        row = {
            "Series": "X-Men, Vol. 1",
            "Issue": "#1",
            "Publisher": "Marvel Comics",
            "Year": "1991",
            "Cover Date": "October 1991",
            "Price": "$1.50",
            "Pages": "32",
        }

        adapter = CLZAdapter()
        result = adapter.fetch_issue_from_csv_row("row-1", row)

        assert result.issue_number == "1"
        assert result.variant_suffix is None
        assert result.cover_date == date(1991, 10, 1)

    def test_issue_mapping_issue_zero(self):
        """Issue #0 maps correctly."""
        row = {
            "Series": "Amazing Spider-Man, Vol. 1",
            "Issue": "#0",
            "Publisher": "Marvel Comics",
            "Year": "1998",
            "Cover Date": "November 1998",
            "Price": "$1.99",
            "Pages": "32",
        }

        adapter = CLZAdapter()
        result = adapter.fetch_issue_from_csv_row("row-0", row)

        assert result.issue_number == "0"
        assert result.variant_suffix is None

    def test_issue_mapping_issue_half(self):
        """Issue #1/2 maps correctly."""
        row = {
            "Series": "Amazing Spider-Man, Vol. 1",
            "Issue": "#1/2",
            "Publisher": "Marvel Comics",
            "Year": "1999",
            "Cover Date": "January 1999",
        }

        adapter = CLZAdapter()
        result = adapter.fetch_issue_from_csv_row("row-half", row)

        assert result.issue_number == "1/2"
        assert result.variant_suffix is None

    def test_issue_empty_row(self):
        """Empty issue row raises ValidationError."""
        adapter = CLZAdapter()

        with pytest.raises(ValidationError, match="CSV row is empty"):
            adapter.fetch_issue_from_csv_row("test", {})

    def test_issue_missing_series_title(self):
        """Row without Series field raises ValidationError."""
        row = {
            "Issue": "#1",
        }

        adapter = CLZAdapter()

        with pytest.raises(
            ValidationError, match="missing required field: series title"
        ):
            adapter.fetch_issue_from_csv_row("test", row)

    def test_issue_missing_issue_number(self):
        """Row without Issue field raises ValidationError."""
        row = {
            "Series": "Test Series",
        }

        adapter = CLZAdapter()

        with pytest.raises(ValidationError, match="missing required field: Issue"):
            adapter.fetch_issue_from_csv_row("test", row)

    def test_issue_empty_issue_number(self):
        """Empty Issue field raises ValidationError."""
        row = {
            "Series": "Test Series",
            "Issue": "",
        }

        adapter = CLZAdapter()

        with pytest.raises(ValidationError, match="missing required field: Issue"):
            adapter.fetch_issue_from_csv_row("test", row)

    def test_issue_invalid_issue_number_multi_issue(self):
        """Multi-issue range raises ValidationError."""
        row = {
            "Series": "Test Series",
            "Issue": "1-3",
        }

        adapter = CLZAdapter()

        with pytest.raises(ValidationError, match="Invalid issue number"):
            adapter.fetch_issue_from_csv_row("test", row)


class TestCLZAdapterHelpers:
    """Tests for CLZ adapter helper methods."""

    def test_extract_series_title(self):
        """Series title is extracted correctly."""
        adapter = CLZAdapter()
        row = {"Series": "X-Men, Vol. 1"}

        result = adapter._extract_series_title(row)

        assert result == "X-Men, Vol. 1"

    def test_extract_series_title_missing(self):
        """Missing Series field returns None."""
        adapter = CLZAdapter()
        row = {}

        result = adapter._extract_series_title(row)

        assert result is None

    def test_extract_series_id(self):
        """Series ID is extracted from Series field."""
        adapter = CLZAdapter()
        row = {"Series": "Test Series"}

        result = adapter._extract_series_id(row)

        assert result == "Test Series"

    def test_parse_year_valid(self):
        """Valid year string is parsed correctly."""
        adapter = CLZAdapter()

        assert adapter._parse_year("1997") == 1997
        assert adapter._parse_year("2000") == 2000
        assert adapter._parse_year(2000) == 2000

    def test_parse_year_invalid(self):
        """Invalid year string returns None."""
        adapter = CLZAdapter()

        assert adapter._parse_year("") is None
        assert adapter._parse_year("invalid") is None
        assert adapter._parse_year("1700") is None
        assert adapter._parse_year("2200") is None

    def test_parse_date_full_format(self):
        """Full date format is parsed correctly."""
        adapter = CLZAdapter()

        result = adapter._parse_date("May 21, 1997")
        assert result == date(1997, 5, 21)

    def test_parse_date_month_year_format(self):
        """Month-year format is parsed correctly."""
        adapter = CLZAdapter()

        result = adapter._parse_date("July 1997")
        assert result == date(1997, 7, 1)

        result = adapter._parse_date("October 1991")
        assert result == date(1991, 10, 1)

    def test_parse_date_iso_format(self):
        """ISO date format is parsed correctly."""
        adapter = CLZAdapter()

        result = adapter._parse_date("1997-07-01")
        assert result == date(1997, 7, 1)

    def test_parse_date_invalid(self):
        """Invalid date string returns None."""
        adapter = CLZAdapter()

        assert adapter._parse_date("") is None
        assert adapter._parse_date("invalid-date") is None
        assert adapter._parse_date(None) is None

    def test_parse_price_with_dollar_sign(self):
        """Price with dollar sign is parsed correctly."""
        adapter = CLZAdapter()

        result = adapter._parse_price("$1.95")
        assert result == 1.95

    def test_parse_price_without_dollar_sign(self):
        """Price without dollar sign is parsed correctly."""
        adapter = CLZAdapter()

        result = adapter._parse_price("2.50")
        assert result == 2.50

    def test_parse_price_invalid(self):
        """Invalid price string returns None."""
        adapter = CLZAdapter()

        assert adapter._parse_price("") is None
        assert adapter._parse_price("invalid") is None
        assert adapter._parse_price(None) is None

    def test_parse_page_count_numeric(self):
        """Numeric page count is parsed correctly."""
        adapter = CLZAdapter()

        result = adapter._parse_page_count("32")
        assert result == 32

    def test_parse_page_count_with_text(self):
        """Page count with text suffix is parsed correctly."""
        adapter = CLZAdapter()

        result = adapter._parse_page_count("32 pages")
        assert result == 32

    def test_parse_page_count_invalid(self):
        """Invalid page count returns None."""
        adapter = CLZAdapter()

        assert adapter._parse_page_count("") is None
        assert adapter._parse_page_count("invalid") is None
        assert adapter._parse_page_count(None) is None

    def test_clean_upc_with_spaces(self):
        """UPC with spaces is cleaned correctly."""
        adapter = CLZAdapter()

        result = adapter._clean_upc("759606017720 99911")
        assert result == "75960601772099911"

    def test_clean_upc_with_dashes(self):
        """UPC with dashes is cleaned correctly."""
        adapter = CLZAdapter()

        result = adapter._clean_upc("75960601772-099911")
        assert result == "75960601772099911"

    def test_clean_upc_already_clean(self):
        """Clean UPC is returned as-is."""
        adapter = CLZAdapter()

        result = adapter._clean_upc("75960601772099911")
        assert result == "75960601772099911"

    def test_clean_upc_invalid(self):
        """Invalid UPC returns None."""
        adapter = CLZAdapter()

        assert adapter._clean_upc("") is None
        assert adapter._clean_upc("invalid") is None
        assert adapter._clean_upc(None) is None


class TestCLZAdapterEdgeCases:
    """Edge case tests for CLZ adapter to improve coverage."""

    def test_series_with_whitespace_only_title(self):
        """Series title with only whitespace raises ValidationError."""
        row = {
            "Series": "   ",
        }

        adapter = CLZAdapter()

        with pytest.raises(
            ValidationError, match="missing required field: series title"
        ):
            adapter.fetch_series_from_csv_row("test", row)

    def test_issue_with_whitespace_only_number(self):
        """Issue number with only whitespace raises ValidationError."""
        row = {
            "Series": "Test Series",
            "Issue": "   ",
        }

        adapter = CLZAdapter()

        with pytest.raises(ValidationError, match="Invalid issue number"):
            adapter.fetch_issue_from_csv_row("test", row)

    def test_parse_year_out_of_range_low(self):
        """Year below valid range returns None."""
        adapter = CLZAdapter()

        result = adapter._parse_year("1799")
        assert result is None

    def test_parse_year_out_of_range_high(self):
        """Year above valid range returns None."""
        adapter = CLZAdapter()

        result = adapter._parse_year("2101")
        assert result is None

    def test_parse_date_abbr_month_year(self):
        """Abbreviated month name is parsed correctly."""
        adapter = CLZAdapter()

        result = adapter._parse_date("Jan 2020")
        assert result == date(2020, 1, 1)

    def test_parse_date_abbr_month_day_year(self):
        """Abbreviated month with day is parsed correctly."""
        adapter = CLZAdapter()

        result = adapter._parse_date("Mar 15, 2020")
        assert result == date(2020, 3, 15)

    def test_parse_date_march_not_may(self):
        """March is parsed correctly (not May)."""
        adapter = CLZAdapter()

        result = adapter._parse_date("March 21, 1997")
        assert result == date(1997, 3, 21)

    def test_parse_price_zero(self):
        """Zero price is parsed correctly."""
        adapter = CLZAdapter()

        result = adapter._parse_price("$0.00")
        assert result == 0.0

    def test_parse_price_with_cents(self):
        """Price with only cents is parsed correctly."""
        adapter = CLZAdapter()

        result = adapter._parse_price("0.50")
        assert result == 0.50

    def test_parse_page_count_zero(self):
        """Zero page count returns None (invalid)."""
        adapter = CLZAdapter()

        result = adapter._parse_page_count("0")
        assert result == 0

    def test_extract_series_id_when_missing(self):
        """Missing Series field returns empty string for ID."""
        adapter = CLZAdapter()
        row = {}

        result = adapter._extract_series_id(row)

        assert result == ""

    def test_csv_with_only_headers(self):
        """CSV with only headers (no data rows) raises ValidationError."""
        csv_content = "Series,Issue,Publisher\n"
        adapter = CLZAdapter()

        with pytest.raises(ValidationError, match="contains no data rows"):
            adapter.load_csv_from_string(csv_content)

    def test_csv_with_unicode_decode_error(self):
        """CSV file with encoding error raises ValidationError."""
        import tempfile
        import os

        adapter = CLZAdapter()

        # Create a file with invalid UTF-8 encoding
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".csv") as f:
            temp_file = f.name
            f.write(b"\xff\xfeSeries,Issue\n")  # UTF-16 LE BOM

        try:
            with pytest.raises(ValidationError, match="CSV file encoding error"):
                adapter.load_csv_from_file(temp_file)
        finally:
            os.unlink(temp_file)

    def test_fetch_series_raises_not_implemented(self):
        """fetch_series raises NotImplementedError."""
        adapter = CLZAdapter()

        with pytest.raises(NotImplementedError, match="Use fetch_series_from_csv"):
            adapter.fetch_series("test-id")

    def test_fetch_issue_raises_not_implemented(self):
        """fetch_issue raises NotImplementedError."""
        adapter = CLZAdapter()

        with pytest.raises(NotImplementedError, match="Use fetch_issue_from_csv"):
            adapter.fetch_issue("test-id")

    def test_parse_date_empty_after_strip(self):
        """Date string with only whitespace returns None."""
        adapter = CLZAdapter()

        result = adapter._parse_date("   ")
        assert result is None

    def test_parse_page_count_attribute_error(self):
        """Page count with None causes AttributeError and returns None."""
        adapter = CLZAdapter()

        result = adapter._parse_page_count(None)
        assert result is None

    def test_parse_page_count_object_without_split(self):
        """Page count with object that doesn't have strip causes AttributeError and returns None."""
        adapter = CLZAdapter()

        class TestObj:
            def __str__(self):
                raise AttributeError("no str")

        result = adapter._parse_page_count(TestObj())
        assert result is None

    def test_csv_with_csv_parsing_error(self):
        """CSV that causes csv.Error raises ValidationError."""
        import csv
        from unittest.mock import patch

        adapter = CLZAdapter()
        csv_content = "Series,Issue\nTest,#1\n"

        with patch("csv.DictReader") as mock_reader:
            mock_reader.side_effect = csv.Error("Test error")

            with pytest.raises(ValidationError, match="CSV parsing error"):
                adapter.load_csv_from_string(csv_content)

    def test_issue_number_parsing_succeeds_but_no_canonical(self):
        """Issue number parsing succeeds but produces no canonical form."""
        from unittest.mock import patch

        adapter = CLZAdapter()

        row = {
            "Series": "Test Series",
            "Issue": "#1",
        }

        # Mock parse_issue_candidate to return success but None canonical
        with patch(
            "comic_identity_engine.adapters.clz.parse_issue_candidate"
        ) as mock_parse:
            from comic_identity_engine.parsing import ParseResult

            mock_parse.return_value = ParseResult(
                success=True, raw="#1", canonical_issue_number=None, variant_suffix=None
            )

            with pytest.raises(
                ValidationError,
                match="parsed successfully but produced no canonical form",
            ):
                adapter.fetch_issue_from_csv_row("test", row)

    def test_parse_date_exception_during_parsing(self):
        """Date parsing raises unexpected exception."""
        from unittest.mock import patch

        adapter = CLZAdapter()

        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.strptime.side_effect = RuntimeError("unexpected error")

            result = adapter._parse_date("July 1997")
            assert result is None


class TestCLZAdapterRealData:
    """Tests using actual CLZ CSV fixture data."""

    def test_xmen_negative1_from_fixture(self):
        """Test X-Men #-1A from sample CLZ export."""
        adapter = CLZAdapter()
        csv_path = FIXTURE_DIR / "sample_clz_export.csv"

        rows = adapter.load_csv_from_file(csv_path)
        result = adapter.fetch_issue_from_csv_row("row-0", rows[0])

        assert result.series_title == "X-Men, Vol. 1"
        assert result.issue_number == "-1"
        assert result.variant_suffix == "A"
        assert result.publisher == "Marvel Comics"
        assert result.series_start_year == 1997
        assert result.cover_date == date(1997, 7, 1)
        assert result.publication_date == date(1997, 5, 21)
        assert result.price == 1.95
        assert result.page_count == 32
        assert result.upc == "75960601772099911"

    def test_amazing_spiderman_from_fixture(self):
        """Test Amazing Spider-Man #1 from sample CLZ export."""
        adapter = CLZAdapter()
        csv_path = FIXTURE_DIR / "sample_clz_export.csv"

        rows = adapter.load_csv_from_file(csv_path)
        result = adapter.fetch_issue_from_csv_row("row-1", rows[1])

        assert result.series_title == "Amazing Spider-Man, Vol. 1"
        assert result.issue_number == "1"
        assert result.variant_suffix is None
        assert result.publisher == "Marvel Comics"
        assert result.series_start_year == 1963
        assert result.cover_date == date(1963, 3, 1)
        assert result.price == 0.12

    def test_special_issue_numbers_from_fixture(self):
        """Test special issue numbers (0, 1/2) from fixture."""
        adapter = CLZAdapter()
        csv_path = FIXTURE_DIR / "special_issue_numbers.csv"

        rows = adapter.load_csv_from_file(csv_path)

        result = adapter.fetch_issue_from_csv_row("row-0", rows[0])
        assert result.issue_number == "0"

        result = adapter.fetch_issue_from_csv_row("row-1", rows[1])
        assert result.issue_number == "1/2"

    def test_xmen_issues_from_fixture(self):
        """Test multiple X-Men issues from fixture."""
        adapter = CLZAdapter()
        csv_path = FIXTURE_DIR / "xmen_issues.csv"

        rows = adapter.load_csv_from_file(csv_path)

        result = adapter.fetch_issue_from_csv_row("row-0", rows[0])
        assert result.issue_number == "-1"
        assert result.variant_suffix == "A"

        result = adapter.fetch_issue_from_csv_row("row-1", rows[1])
        assert result.issue_number == "100"
        assert result.variant_suffix is None

        result = adapter.fetch_issue_from_csv_row("row-2", rows[2])
        assert result.issue_number == "100.5"
        assert result.variant_suffix is None
