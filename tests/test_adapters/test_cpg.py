"""Tests for CPG adapter implementation."""

from datetime import date
import pytest

from comic_identity_engine.adapters import CPGAdapter, ValidationError


class TestCPGAdapterSeriesMapping:
    """Tests for CPG series payload mapping."""

    def test_successful_series_mapping(self):
        """CPG series payload maps to SeriesCandidate correctly."""
        payload = {
            "title": "X-Men",
            "publisher": "Marvel",
            "year": 1991,
        }

        adapter = CPGAdapter()
        result = adapter.fetch_series_from_payload("x-men", payload)

        assert result.source == "cpg"
        assert result.source_series_id == "x-men"
        assert result.series_title == "X-Men"
        assert result.series_start_year == 1991
        assert result.publisher == "Marvel"

    def test_series_mapping_with_name_field(self):
        """CPG series payload with name field instead of title."""
        payload = {
            "name": "Amazing Spider-Man",
            "publisher": "Marvel",
            "year": 1963,
        }

        adapter = CPGAdapter()
        result = adapter.fetch_series_from_payload("amazing-spider-man", payload)

        assert result.series_title == "Amazing Spider-Man"
        assert result.series_start_year == 1963

    def test_series_mapping_with_title_dict(self):
        """CPG series payload with title as dict."""
        payload = {
            "title": {"name": "X-Men", "nameSEO": "x-men"},
            "publisher": "Marvel",
            "year": 1991,
        }

        adapter = CPGAdapter()
        result = adapter.fetch_series_from_payload("x-men", payload)

        assert result.series_title == "X-Men"

    def test_series_mapping_missing_title_and_name(self):
        """Series payload without title or name raises ValidationError."""
        payload = {
            "publisher": "Marvel",
            "year": 1991,
        }

        adapter = CPGAdapter()
        with pytest.raises(ValidationError, match="missing required field: title/name"):
            adapter.fetch_series_from_payload("x-men", payload)

    def test_series_mapping_with_publication_year(self):
        """Series payload with publicationYear field."""
        payload = {
            "title": "X-Men",
            "publisher": "Marvel",
            "publicationYear": 1991,
        }

        adapter = CPGAdapter()
        result = adapter.fetch_series_from_payload("x-men", payload)

        assert result.series_start_year == 1991

    def test_series_mapping_no_year(self):
        """Series payload without year field."""
        payload = {
            "title": "X-Men",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_series_from_payload("x-men", payload)

        assert result.series_start_year is None

    def test_series_mapping_invalid_year(self):
        """Series payload with invalid year field."""
        payload = {
            "title": "X-Men",
            "publisher": "Marvel",
            "year": "invalid",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_series_from_payload("x-men", payload)

        assert result.series_start_year is None

    def test_series_mapping_no_publisher(self):
        """Series payload without publisher field."""
        payload = {
            "title": "X-Men",
            "year": 1991,
        }

        adapter = CPGAdapter()
        result = adapter.fetch_series_from_payload("x-men", payload)

        assert result.publisher is None

    def test_empty_series_payload(self):
        """Empty series payload raises ValidationError."""
        adapter = CPGAdapter()
        with pytest.raises(ValidationError, match="payload is empty"):
            adapter.fetch_series_from_payload("x-men", {})

    def test_series_mapping_fallback_to_nameseo(self):
        """Series payload with only nameSEO field."""
        payload = {
            "nameSEO": "x-men",
            "publisher": "Marvel",
            "year": 1991,
        }

        adapter = CPGAdapter()
        result = adapter.fetch_series_from_payload("x-men", payload)

        assert result.series_title == "x-men"


class TestCPGAdapterIssueMapping:
    """Tests for CPG issue payload mapping."""

    def test_successful_issue_mapping_xmen_negative1(self):
        """CPG issue payload for X-Men #-1 maps correctly."""
        payload = {
            "number": "-1",
            "title": "X-Men",
            "publisher": "Marvel",
            "year": 1997,
            "publicationDate": "1997-07-01",
            "releaseDate": "1997-05-21",
            "price": "1.95",
            "upc": "75960601772099911",
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("abc123", payload)

        assert result.source == "cpg"
        assert result.source_issue_id == "abc123"
        assert result.source_series_id == "x-men"
        assert result.series_title == "X-Men"
        assert result.series_start_year == 1997
        assert result.publisher == "Marvel"
        assert result.issue_number == "-1"
        assert result.variant_suffix is None
        assert result.cover_date == date(1997, 7, 1)
        assert result.publication_date == date(1997, 5, 21)
        assert result.price == 1.95
        assert result.upc == "75960601772099911"

    def test_issue_mapping_with_variant(self):
        """CPG issue payload with variant suffix."""
        payload = {
            "number": "100A",
            "title": "X-Men",
            "publisher": "Marvel",
            "year": 2000,
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("xyz789", payload)

        assert result.issue_number == "100"
        assert result.variant_suffix == "A"

    def test_issue_mapping_with_title_dict(self):
        """CPG issue payload with title as dict."""
        payload = {
            "number": "1",
            "title": {"name": "X-Men", "nameSEO": "x-men"},
            "publisher": "Marvel",
            "year": 1991,
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("def456", payload)

        assert result.series_title == "X-Men"

    def test_issue_mapping_fallback_to_nameseo(self):
        """CPG issue payload with only nameSEO for title."""
        payload = {
            "number": "1",
            "nameSEO": "x-men",
            "publisher": "Marvel",
            "year": 1991,
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("ghi012", payload)

        assert result.series_title == "x-men"

    def test_issue_mapping_fallback_to_name(self):
        """CPG issue payload with only name for title."""
        payload = {
            "number": "1",
            "name": "x-men",
            "publisher": "Marvel",
            "year": 1991,
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("jkl345", payload)

        assert result.series_title == "x-men"

    def test_issue_missing_title(self):
        """Issue payload without title/name raises ValidationError."""
        payload = {
            "number": "1",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()
        with pytest.raises(ValidationError, match="missing required field: title"):
            adapter.fetch_issue_from_payload("mno678", payload)

    def test_issue_missing_number(self):
        """Issue payload without number raises ValidationError."""
        payload = {
            "title": "X-Men",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()
        with pytest.raises(ValidationError, match="missing required field: number"):
            adapter.fetch_issue_from_payload("pqr901", payload)

    def test_issue_invalid_number_format(self):
        """Invalid issue number format raises ValidationError."""
        payload = {
            "number": "1-3",
            "title": "X-Men",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()
        with pytest.raises(ValidationError, match="Invalid issue number"):
            adapter.fetch_issue_from_payload("stu234", payload)

    def test_empty_issue_payload(self):
        """Empty issue payload raises ValidationError."""
        adapter = CPGAdapter()
        with pytest.raises(ValidationError, match="payload is empty"):
            adapter.fetch_issue_from_payload("vwx567", {})

    def test_issue_with_path_issue_variant(self):
        """Issue with variant in path_issue field."""
        payload = {
            "number": "100",
            "title": "X-Men",
            "publisher": "Marvel",
            "path_issue": "100-B",
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("yza890", payload)

        assert result.issue_number == "100"
        assert result.variant_suffix == "B"

    def test_issue_with_price_as_number(self):
        """Issue with price as number instead of string."""
        payload = {
            "number": "1",
            "title": "X-Men",
            "publisher": "Marvel",
            "price": 2.99,
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("bcd123", payload)

        assert result.price == 2.99

    def test_issue_with_price_dollar_sign(self):
        """Issue with price string containing dollar sign."""
        payload = {
            "number": "1",
            "title": "X-Men",
            "publisher": "Marvel",
            "price": "$3.50",
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("efg456", payload)

        assert result.price == 3.50

    def test_issue_with_barcode(self):
        """Issue with barcode field instead of upc."""
        payload = {
            "number": "1",
            "title": "X-Men",
            "publisher": "Marvel",
            "barcode": "75960601772099911",
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("hij789", payload)

        assert result.upc == "75960601772099911"

    def test_issue_with_decimal_issue_number(self):
        """Issue with decimal issue number."""
        payload = {
            "number": "0.5",
            "title": "X-Men",
            "publisher": "Marvel",
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("klm012", payload)

        assert result.issue_number == "0.5"


class TestCPGAdapterHelpers:
    """Tests for CPG adapter helper methods."""

    def test_extract_title_from_dict(self):
        """Title extraction from dict payload."""
        adapter = CPGAdapter()
        result = adapter._extract_title_from_payload(
            {"title": {"name": "X-Men", "nameSEO": "x-men"}}
        )

        assert result == "X-Men"

    def test_extract_title_from_string(self):
        """Title extraction from string payload."""
        adapter = CPGAdapter()
        result = adapter._extract_title_from_payload({"title": "X-Men"})

        assert result == "X-Men"

    def test_extract_title_from_nameseo(self):
        """Title extraction fallback to nameSEO."""
        adapter = CPGAdapter()
        result = adapter._extract_title_from_payload({"nameSEO": "x-men", "title": ""})

        assert result == "x-men"

    def test_extract_title_from_name(self):
        """Title extraction fallback to name."""
        adapter = CPGAdapter()
        result = adapter._extract_title_from_payload({"name": "x-men"})

        assert result == "x-men"

    def test_extract_title_none(self):
        """Title extraction returns None when not found."""
        adapter = CPGAdapter()
        result = adapter._extract_title_from_payload({})

        assert result is None

    def test_extract_year_from_year_field(self):
        """Year extraction from year field."""
        adapter = CPGAdapter()
        result = adapter._extract_year_from_payload({"year": 1991})

        assert result == 1991

    def test_extract_year_from_publication_year(self):
        """Year extraction from publicationYear field."""
        adapter = CPGAdapter()
        result = adapter._extract_year_from_payload({"publicationYear": 1991})

        assert result == 1991

    def test_extract_year_invalid(self):
        """Year extraction with invalid value returns None."""
        adapter = CPGAdapter()
        result = adapter._extract_year_from_payload({"year": "invalid"})

        assert result is None

    def test_extract_year_none(self):
        """Year extraction with None returns None."""
        adapter = CPGAdapter()
        result = adapter._extract_year_from_payload({})

        assert result is None

    def test_extract_variant_from_path_issue(self):
        """Variant extraction from path_issue field."""
        adapter = CPGAdapter()
        result = adapter._extract_variant_from_url({"path_issue": "100-A"})

        assert result == "A"

    def test_extract_variant_from_number(self):
        """Variant extraction from number field."""
        adapter = CPGAdapter()
        result = adapter._extract_variant_from_url({"number": "100-B"})

        assert result == "B"

    def test_extract_variant_negative_one(self):
        """Variant extraction with -1 issue returns None."""
        adapter = CPGAdapter()
        result = adapter._extract_variant_from_url({"number": "-1"})

        assert result is None

    def test_extract_variant_no_variant(self):
        """Variant extraction without variant returns None."""
        adapter = CPGAdapter()
        result = adapter._extract_variant_from_url({"number": "100"})

        assert result is None

    def test_extract_variant_numeric_suffix(self):
        """Variant extraction with numeric suffix returns None."""
        adapter = CPGAdapter()
        result = adapter._extract_variant_from_url({"path_issue": "100-2"})

        assert result is None

    def test_extract_variant_none_input(self):
        """Variant extraction with None input returns None."""
        adapter = CPGAdapter()
        result = adapter._extract_variant_from_url({})

        assert result is None

    def test_parse_date_iso_format(self):
        """Date parsing from ISO format."""
        adapter = CPGAdapter()
        result = adapter._parse_date("1997-07-01")

        assert result == date(1997, 7, 1)

    def test_parse_date_month_only(self):
        """Date parsing from month-only format."""
        adapter = CPGAdapter()
        result = adapter._parse_date("1997-07")

        assert result == date(1997, 7, 1)

    def test_parse_date_year_only(self):
        """Date parsing from year-only format."""
        adapter = CPGAdapter()
        result = adapter._parse_date("1997")

        assert result == date(1997, 1, 1)

    def test_parse_date_text_with_year(self):
        """Date parsing from text containing year."""
        adapter = CPGAdapter()
        result = adapter._parse_date("July 1997")

        assert result == date(1997, 1, 1)

    def test_parse_date_invalid(self):
        """Date parsing with invalid format returns None."""
        adapter = CPGAdapter()
        result = adapter._parse_date("invalid-date")

        assert result is None

    def test_parse_date_none(self):
        """Date parsing with None returns None."""
        adapter = CPGAdapter()
        result = adapter._parse_date(None)

        assert result is None

    def test_parse_date_object(self):
        """Date parsing with date object returns same object."""
        adapter = CPGAdapter()
        input_date = date(1997, 7, 1)
        result = adapter._parse_date(input_date)

        assert result == input_date

    def test_parse_price_float(self):
        """Price parsing from float."""
        adapter = CPGAdapter()
        result = adapter._parse_price(3.99)

        assert result == 3.99

    def test_parse_price_int(self):
        """Price parsing from int."""
        adapter = CPGAdapter()
        result = adapter._parse_price(3)

        assert result == 3.0

    def test_parse_price_zero(self):
        """Price parsing from zero preserves 0.0."""
        adapter = CPGAdapter()
        result = adapter._parse_price(0)

        assert result == 0.0

    def test_parse_price_string(self):
        """Price parsing from string."""
        adapter = CPGAdapter()
        result = adapter._parse_price("3.99")

        assert result == 3.99

    def test_parse_price_dollar_sign(self):
        """Price parsing from string with dollar sign."""
        adapter = CPGAdapter()
        result = adapter._parse_price("$3.99")

        assert result == 3.99

    def test_parse_price_none(self):
        """Price parsing with None returns None."""
        adapter = CPGAdapter()
        result = adapter._parse_price(None)

        assert result is None

    def test_parse_price_invalid(self):
        """Price parsing with invalid string returns None."""
        adapter = CPGAdapter()
        result = adapter._parse_price("invalid")

        assert result is None


class TestCPGAdapterEdgeCases:
    """Edge case tests for CPG adapter."""

    def test_issue_with_zero_issue_number(self):
        """Issue mapping with issue number 0."""
        payload = {
            "number": "0",
            "title": "X-Men",
            "publisher": "Marvel",
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("zero001", payload)

        assert result.issue_number == "0"

    def test_issue_with_slash_issue_number(self):
        """Issue mapping with slash issue number."""
        payload = {
            "number": "1/2",
            "title": "X-Men",
            "publisher": "Marvel",
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("half001", payload)

        assert result.issue_number == "1/2"

    def test_series_mapping_with_empty_title_dict(self):
        """Series mapping with empty title dict."""
        payload = {
            "title": {},
            "name": "x-men",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_series_from_payload("x-men", payload)

        assert result.series_title == "x-men"

    def test_issue_mapping_with_empty_title_dict(self):
        """Issue mapping with empty title dict."""
        payload = {
            "number": "1",
            "title": {},
            "name": "x-men",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("empty001", payload)

        assert result.series_title == "x-men"

    def test_issue_with_no_publisher(self):
        """Issue mapping without publisher."""
        payload = {
            "number": "1",
            "title": "X-Men",
            "name": "x-men",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("nopub001", payload)

        assert result.publisher is None

    def test_issue_with_no_dates(self):
        """Issue mapping without dates."""
        payload = {
            "number": "1",
            "title": "X-Men",
            "name": "x-men",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("nodate001", payload)

        assert result.cover_date is None
        assert result.publication_date is None

    def test_issue_with_no_price(self):
        """Issue mapping without price."""
        payload = {
            "number": "1",
            "title": "X-Men",
            "name": "x-men",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("noprice001", payload)

        assert result.price is None

    def test_issue_with_no_upc(self):
        """Issue mapping without UPC."""
        payload = {
            "number": "1",
            "title": "X-Men",
            "name": "x-men",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("noupc001", payload)

        assert result.upc is None

    def test_series_title_extracts_from_dict_with_nameseo_fallback(self):
        """Title extraction prefers name over nameSEO."""
        adapter = CPGAdapter()
        result = adapter._extract_title_from_payload(
            {"title": {"name": "X-Men", "nameSEO": "x-men-seo"}}
        )

        assert result == "X-Men"

    def test_year_extraction_prefers_year_over_publication_year(self):
        """Year extraction prefers year field."""
        adapter = CPGAdapter()
        result = adapter._extract_year_from_payload(
            {"year": 1991, "publicationYear": 1990}
        )

        assert result == 1991

    def test_parse_date_handles_different_separators(self):
        """Date parsing handles different separators."""
        adapter = CPGAdapter()

        result1 = adapter._parse_date("1997/07/01")
        assert result1 == date(1997, 7, 1)

        result2 = adapter._parse_date("1997.07.01")
        assert result2 == date(1997, 7, 1)

    def test_price_extraction_handles_commas(self):
        """Price parsing handles commas."""
        adapter = CPGAdapter()
        result = adapter._parse_price("1,299.99")

        assert result == 1299.99

    def test_variant_extraction_handles_lowercase(self):
        """Variant extraction converts to uppercase."""
        adapter = CPGAdapter()
        result = adapter._extract_variant_from_url({"path_issue": "100-a"})

        assert result == "A"

    def test_issue_mapping_with_whitespace_in_number(self):
        """Issue mapping handles whitespace in number."""
        payload = {
            "number": " 1 ",
            "title": "X-Men",
            "name": "x-men",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("space001", payload)

        assert result.issue_number == "1"

    def test_fetch_series_raises_not_implemented(self):
        """fetch_series raises NotImplementedError."""
        adapter = CPGAdapter()

        with pytest.raises(NotImplementedError, match="fetch_series_from_payload"):
            adapter.fetch_series("x-men")

    def test_fetch_issue_raises_not_implemented(self):
        """fetch_issue raises NotImplementedError."""
        adapter = CPGAdapter()

        with pytest.raises(NotImplementedError, match="fetch_issue_from_payload"):
            adapter.fetch_issue("abc123")

    def test_series_mapping_preserves_raw_payload(self):
        """Series mapping preserves raw payload."""
        payload = {
            "title": "X-Men",
            "publisher": "Marvel",
            "year": 1991,
            "extra_field": "extra_value",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_series_from_payload("x-men", payload)

        assert result.raw_payload == payload

    def test_issue_mapping_preserves_raw_payload(self):
        """Issue mapping preserves raw payload."""
        payload = {
            "number": "1",
            "title": "X-Men",
            "name": "x-men",
            "extra_field": "extra_value",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("raw001", payload)

        assert result.raw_payload == payload

    def test_issue_number_with_hash_prefix(self):
        """Issue number with # prefix is handled correctly."""
        payload = {
            "number": "#1",
            "title": "X-Men",
            "name": "x-men",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()
        result = adapter.fetch_issue_from_payload("hash001", payload)

        assert result.issue_number == "1"

    def test_parse_date_slash_separator_two_parts(self):
        """Date parsing with / separator and only year/month."""
        adapter = CPGAdapter()
        result = adapter._parse_date("1997/07")

        assert result == date(1997, 7, 1)

    def test_parse_date_slash_separator_invalid_date(self):
        """Date parsing with / separator but invalid date values."""
        adapter = CPGAdapter()
        result = adapter._parse_date("invalid/13")

        assert result is None

    def test_parse_date_dot_separator_two_parts(self):
        """Date parsing with . separator and only year/month."""
        adapter = CPGAdapter()
        result = adapter._parse_date("1997.07")

        assert result == date(1997, 7, 1)

    def test_parse_date_dot_separator_invalid_date(self):
        """Date parsing with . separator but invalid date values."""
        adapter = CPGAdapter()
        result = adapter._parse_date("invalid.13")

        assert result is None

    def test_parse_date_year_match_invalid(self):
        """Date parsing when year match but date() raises ValueError."""
        adapter = CPGAdapter()
        result = adapter._parse_date("10000")

        assert result is None

    def test_issue_mapping_with_canonical_none(self):
        """Issue mapping when canonical_issue_number is None (edge case)."""
        from unittest.mock import patch

        payload = {
            "number": "1",
            "title": "X-Men",
            "name": "x-men",
            "publisher": "Marvel",
        }

        adapter = CPGAdapter()

        mock_result = type(
            "MockResult",
            (),
            {"success": True, "canonical_issue_number": None, "variant_suffix": None},
        )()

        with patch(
            "comic_identity_engine.adapters.cpg.parse_issue_candidate",
            return_value=mock_result,
        ):
            with pytest.raises(ValidationError, match="produced no canonical form"):
                adapter.fetch_issue_from_payload("none001", payload)

    def test_parse_price_invalid_float_conversion(self):
        """Price parsing when float conversion fails."""
        adapter = CPGAdapter()
        result = adapter._parse_price("NaN")

        assert result is None
