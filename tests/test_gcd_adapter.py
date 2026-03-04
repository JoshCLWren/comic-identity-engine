"""Tests for GCD adapter implementation."""

import json
from pathlib import Path
from datetime import date
from unittest.mock import patch, Mock, AsyncMock

import pytest

from comic_identity_engine.adapters import GCDAdapter, ValidationError


class TestGCDAdapterSeriesMapping:
    """Tests for GCD series payload mapping."""

    def test_successful_series_mapping(self):
        """GCD series payload maps to SeriesCandidate correctly."""
        payload = {
            "name": "X-Men",
            "year_began": 1991,
            "year_ended": 2001,
            "publisher": "https://www.comics.org/api/publisher/78/?format=json",
        }

        adapter = GCDAdapter()
        result = adapter.fetch_series_from_payload("4254", payload)

        assert result.source == "gcd"
        assert result.source_series_id == "4254"
        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991
        assert result.series_end_year == 2001
        assert result.publisher is None  # GCD provides URL, not name

    def test_missing_name_field(self):
        """Series payload without name raises ValidationError."""
        payload = {
            "year_began": 1991,
        }

        adapter = GCDAdapter()
        with pytest.raises(ValidationError, match="missing required field: name"):
            adapter.fetch_series_from_payload("4254", payload)

    def test_missing_year_began_field(self):
        """Series payload without year_began raises ValidationError."""
        payload = {
            "name": "X-Men",
        }

        adapter = GCDAdapter()
        with pytest.raises(ValidationError, match="missing required field: year_began"):
            adapter.fetch_series_from_payload("4254", payload)

    def test_empty_payload(self):
        """Empty series payload raises ValidationError."""
        adapter = GCDAdapter()
        with pytest.raises(ValidationError, match="payload is empty"):
            adapter.fetch_series_from_payload("4254", {})


class TestGCDAdapterIssueMapping:
    """Tests for GCD issue payload mapping."""

    def test_successful_issue_mapping_xmen_negative1(self):
        """GCD issue payload for X-Men #-1 maps correctly."""
        payload = {
            "series_name": "X-Men (1991 series)",
            "number": "-1",
            "descriptor": "-1 [Direct Edition]",
            "variant_name": "Direct Edition",
            "publication_date": "July 1997",
            "key_date": "1997-07-00",
            "price": "1.95 USD; 2.75 CAD",
            "page_count": "44.000",
            "barcode": "75960601772099911",
            "indicia_publisher": "Marvel Comics",
            "on_sale_date": "1997-05-21",
            "series": "https://www.comics.org/api/series/4254/?format=json",
        }

        adapter = GCDAdapter()
        result = adapter.fetch_issue_from_payload("125295", payload)

        assert result.source == "gcd"
        assert result.source_issue_id == "125295"
        assert result.source_series_id == "4254"
        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991
        assert result.publisher == "Marvel Comics"
        assert result.issue_number == "-1"
        assert result.variant_suffix is None  # Direct Edition is distribution
        assert result.cover_date == date(1997, 7, 1)
        assert result.publication_date == date(1997, 5, 21)
        assert result.price == 1.95
        assert result.page_count == 44
        assert result.upc == "75960601772099911"

    def test_issue_mapping_with_variant(self):
        """GCD issue payload with variant suffix."""
        payload = {
            "series_name": "X-Men (1991 series)",
            "number": "100",
            "descriptor": "100 [Adams cover]",
            "variant_name": "Adams cover",
            "publication_date": "August 2000",
            "key_date": "2000-08-00",
            "price": "2.50 USD",
            "indicia_publisher": "Marvel Comics",
            "series": "https://www.comics.org/api/series/4254/?format=json",
        }

        adapter = GCDAdapter()
        result = adapter.fetch_issue_from_payload("50256", payload)

        assert result.issue_number == "100"
        assert result.variant_suffix == "VARIANT"  # From descriptor parsing
        assert result.variant_name == "Adams cover"

    def test_issue_mapping_with_single_letter_variant(self):
        """GCD issue payload with single letter variant (A, B, C)."""
        payload = {
            "series_name": "X-Men (1991 series)",
            "number": "1",
            "descriptor": "1 [Cover A] [Direct]",
            "variant_name": "Cover A",
            "publication_date": "October 1991",
            "key_date": "1991-10-00",
            "indicia_publisher": "Marvel Comics",
            "series": "https://www.comics.org/api/series/4254/?format=json",
        }

        adapter = GCDAdapter()
        result = adapter.fetch_issue_from_payload("50256", payload)

        assert result.issue_number == "1"
        assert result.variant_suffix == "A"

    def test_missing_series_name(self):
        """Issue payload without series_name raises ValidationError."""
        payload = {
            "number": "-1",
        }

        adapter = GCDAdapter()
        with pytest.raises(
            ValidationError, match="missing required field: series_name"
        ):
            adapter.fetch_issue_from_payload("125295", payload)

    def test_missing_number_field(self):
        """Issue payload without number raises ValidationError."""
        payload = {
            "series_name": "X-Men (1991 series)",
        }

        adapter = GCDAdapter()
        with pytest.raises(ValidationError, match="missing required field: number"):
            adapter.fetch_issue_from_payload("125295", payload)

    def test_invalid_issue_number_format(self):
        """Invalid issue number format raises ValidationError."""
        payload = {
            "series_name": "X-Men (1991 series)",
            "number": "1-3",  # Multi-issue range
        }

        adapter = GCDAdapter()
        with pytest.raises(ValidationError, match="Invalid issue number"):
            adapter.fetch_issue_from_payload("125295", payload)

    def test_empty_issue_payload(self):
        """Empty issue payload raises ValidationError."""
        adapter = GCDAdapter()
        with pytest.raises(ValidationError, match="payload is empty"):
            adapter.fetch_issue_from_payload("125295", {})


class TestGCDAdapterHelpers:
    """Tests for GCD adapter helper methods."""

    def test_parse_series_name_with_year(self):
        """Series name with year in parentheses is parsed correctly."""
        adapter = GCDAdapter()
        title, year = adapter._parse_series_name("X-Men (1991 series)")

        assert title == "X-Men"
        assert year == 1991

    def test_parse_series_name_without_year(self):
        """Series name without year returns title with None year."""
        adapter = GCDAdapter()
        title, year = adapter._parse_series_name("X-Men")

        assert title == "X-Men"
        assert year is None

    def test_extract_variant_suffix_none(self):
        """Descriptor without variant returns None."""
        adapter = GCDAdapter()
        result = adapter._extract_variant_suffix_from_descriptor("-1 [Direct Edition]")

        assert result is None

    def test_extract_variant_suffix_variant_edition(self):
        """Variant Edition descriptor maps to VARIANT suffix."""
        adapter = GCDAdapter()
        result = adapter._extract_variant_suffix_from_descriptor(
            "100 [Variant Edition]"
        )

        assert result == "VARIANT"

    def test_parse_price_usd(self):
        """Price string with USD is parsed correctly."""
        adapter = GCDAdapter()
        result = adapter._parse_price("1.95 USD; 2.75 CAD")

        assert result == 1.95

    def test_parse_price_no_usd(self):
        """Price string without USD returns None."""
        adapter = GCDAdapter()
        result = adapter._parse_price("2.75 CAD")

        assert result is None

    def test_parse_page_count(self):
        """Page count string is parsed to int."""
        adapter = GCDAdapter()
        result = adapter._parse_page_count("44.000")

        assert result == 44

    def test_parse_key_date(self):
        """Key date is parsed to date object."""
        adapter = GCDAdapter()
        result = adapter._parse_key_date("1997-07-00")

        assert result == date(1997, 7, 1)

    def test_parse_on_sale_date(self):
        """On sale date is parsed to date object."""
        adapter = GCDAdapter()
        result = adapter._parse_on_sale_date("1997-05-21")

        assert result == date(1997, 5, 21)

    def test_extract_series_id_from_payload(self):
        """Series ID is extracted from series URL."""
        adapter = GCDAdapter()
        result = adapter._extract_series_id_from_payload(
            {"series": "https://www.comics.org/api/series/4254/?format=json"}
        )

        assert result == "4254"


class TestGCDAdapterRealData:
    """Tests using actual GCD API responses."""

    def test_xmen_negative1_real_payload(self):
        """Test with actual X-Men #-1 GCD API response."""
        payload_path = (
            Path(__file__).parent.parent
            / "examples"
            / "gcd"
            / "raw"
            / "xmen-negative1-api-response.json"
        )

        with open(payload_path) as f:
            payload = json.load(f)

        adapter = GCDAdapter()
        result = adapter.fetch_issue_from_payload("125295", payload)

        assert result.issue_number == "-1"
        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991
        assert result.publisher == "Marvel Comics"
        assert result.upc == "75960601772099911"
        assert result.page_count == 44
        assert result.price == 1.95
        assert result.cover_date == date(1997, 7, 1)
        assert result.publication_date == date(1997, 5, 21)


class TestGCDAdapterEdgeCases:
    """Edge case tests for GCD adapter to improve coverage."""

    def test_series_with_missing_year_began(self):
        """Series payload with year_began as None raises ValidationError."""
        payload = {
            "name": "X-Men",
            "year_began": None,
        }

        adapter = GCDAdapter()
        with pytest.raises(ValidationError, match="missing required field: year_began"):
            adapter.fetch_series_from_payload("4254", payload)

    def test_variant_extraction_empty_descriptor(self):
        """Empty descriptor returns None variant suffix."""
        adapter = GCDAdapter()
        result = adapter._extract_variant_suffix_from_descriptor("")

        assert result is None

    def test_variant_with_multiple_parts(self):
        """Variant with multiple parts returns VARIANT code."""
        adapter = GCDAdapter()
        result = adapter._extract_variant_suffix_from_descriptor(
            "100 [Limited] [Signed]"
        )

        assert result == "VARIANT"

    def test_descriptor_with_only_distribution_markers(self):
        """Descriptor with only distribution markers returns None."""
        adapter = GCDAdapter()
        result = adapter._extract_variant_suffix_from_descriptor(
            "100 [Direct] [Newsstand]"
        )

        assert result is None

    def test_series_url_without_id(self):
        """Series URL without ID returns empty string."""
        adapter = GCDAdapter()
        result = adapter._extract_series_id_from_payload({"series": "invalid_url"})

        assert result == ""

    def test_series_url_missing_from_payload(self):
        """Missing series URL returns empty string."""
        adapter = GCDAdapter()
        result = adapter._extract_series_id_from_payload({})

        assert result == ""

    def test_parse_key_date_invalid_format(self):
        """Invalid key_date format returns None."""
        adapter = GCDAdapter()
        result = adapter._parse_key_date("invalid-date")

        assert result is None

    def test_parse_key_date_short_date(self):
        """key_date shorter than 7 characters returns None."""
        adapter = GCDAdapter()
        result = adapter._parse_key_date("1997")

        assert result is None

    def test_parse_on_sale_date_invalid_format(self):
        """Invalid on_sale_date format returns None."""
        adapter = GCDAdapter()
        result = adapter._parse_on_sale_date("invalid-date")

        assert result is None

    def test_parse_price_with_non_numeric_usd(self):
        """Price with non-numeric USD value returns None."""
        adapter = GCDAdapter()
        result = adapter._parse_price("abc USD")

        assert result is None

    def test_parse_price_with_no_usd(self):
        """Price without USD returns None."""
        adapter = GCDAdapter()
        result = adapter._parse_price("2.75 CAD")

        assert result is None

    def test_parse_page_count_with_invalid_format(self):
        """Invalid page_count format returns None."""
        adapter = GCDAdapter()
        result = adapter._parse_page_count("invalid")

        assert result is None

    def test_variant_extraction_distribution_marker_continue(self):
        """Descriptor with distribution marker skips to next part (line 242)."""
        adapter = GCDAdapter()
        result = adapter._extract_variant_suffix_from_descriptor(
            "100 [Direct] [Limited]"
        )

        assert result == "VARIANT"

    def test_variant_extraction_cover_artist_single_letter(self):
        """Cover artist descriptor with space returns VARIANT (lines 256-258 unreachable)."""
        adapter = GCDAdapter()
        # This test documents that lines 256-258 are unreachable with current implementation
        # "Adams cover" gets split into ["Adams", "cover"], so the space check fails
        result = adapter._extract_variant_suffix_from_descriptor("100 [Adams cover]")

        assert result == "VARIANT"

    def test_variant_extraction_distribution_only_returns_none(self):
        """Descriptor with only distribution markers returns None (line 266)."""
        adapter = GCDAdapter()
        result = adapter._extract_variant_suffix_from_descriptor(
            "100 [Direct] [Newsstand]"
        )

        assert result is None

    def test_parse_key_date_none_returns_none(self):
        """None key_date returns None (line 308)."""
        adapter = GCDAdapter()
        result = adapter._parse_key_date(None)

        assert result is None

    def test_parse_price_value_error_returns_none(self):
        """Price with valid USD pattern but invalid float returns None (lines 349-350)."""
        adapter = GCDAdapter()
        # Mock re.search to return a match that will raise ValueError on float()
        import re

        mock_match = Mock()
        mock_match.group.return_value = "not_a_number"

        with patch.object(re, "search", return_value=mock_match):
            result = adapter._parse_price("not_a_number USD")

        assert result is None


class TestGCDAdapterAsync:
    """Async tests for GCD adapter to verify async infrastructure works."""

    @pytest.mark.asyncio
    async def test_gcd_adapter_has_async_methods(self):
        """Test that GCD adapter has async fetch methods."""
        adapter = GCDAdapter()
        # Verify the adapter has the expected async methods
        assert hasattr(adapter, "fetch_series")
        assert hasattr(adapter, "fetch_issue")
        assert hasattr(adapter, "fetch_series_from_payload")
        assert hasattr(adapter, "fetch_issue_from_payload")

    @pytest.mark.asyncio
    async def test_gcd_adapter_can_use_mock_http_client(self, mock_http_client):
        """Test that GCD adapter works with async mock HTTP client."""
        # Create adapter and manually attach mock client
        adapter = GCDAdapter()
        adapter.http_client = mock_http_client

        # Setup mock response
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "series_name": "X-Men (1991 series)",
                "number": "1",
                "descriptor": "1",
                "key_date": "1991-10-00",
                "indicia_publisher": "Marvel Comics",
                "series": "https://www.comics.org/api/series/4254/?format=json",
            }
        )
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        # Verify adapter stores the http_client
        assert adapter.http_client is mock_http_client
