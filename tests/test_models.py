"""Tests for models.py - SeriesCandidate and IssueCandidate."""

from datetime import date
from longbox_commons.models import SeriesCandidate, IssueCandidate


class TestSeriesCandidate:
    """Tests for SeriesCandidate model."""

    def test_model_dump(self):
        """SeriesCandidate.model_dump() returns correct dictionary."""
        candidate = SeriesCandidate(
            source="gcd",
            source_series_id="4254",
            series_title="X-Men",
            series_start_year=1991,
            publisher="Marvel",
            series_end_year=2001,
            volume_number=1,
            raw_payload={"test": "data"},
        )

        result = candidate.model_dump(exclude={"raw_payload"})

        assert result["source"] == "gcd"
        assert result["source_series_id"] == "4254"
        assert result["series_title"] == "X-Men"
        assert result["series_start_year"] == 1991
        assert result["publisher"] == "Marvel"
        assert result["series_end_year"] == 2001
        assert result["volume_number"] == 1
        assert "raw_payload" not in result  # raw_payload is excluded


class TestIssueCandidate:
    """Tests for IssueCandidate model."""

    def test_model_dump_with_all_fields(self):
        """IssueCandidate.model_dump() returns correct dictionary with all fields."""
        candidate = IssueCandidate(
            source="gcd",
            source_series_id="4254",
            source_issue_id="125295",
            series_title="X-Men",
            series_start_year=1991,
            publisher="Marvel",
            issue_number="-1",
            variant_suffix="A",
            cover_date=date(1997, 7, 1),
            publication_date=date(1997, 5, 21),
            price=1.95,
            page_count=44,
            upc="75960601772099911",
            isbn="1234567890",
            variant_name="Direct Edition",
            raw_payload={"test": "data"},
        )

        result = candidate.model_dump(exclude={"raw_payload"})

        assert result["source"] == "gcd"
        assert result["source_series_id"] == "4254"
        assert result["source_issue_id"] == "125295"
        assert result["series_title"] == "X-Men"
        assert result["series_start_year"] == 1991
        assert result["publisher"] == "Marvel"
        assert result["issue_number"] == "-1"
        assert result["variant_suffix"] == "A"
        assert result["cover_date"] == date(1997, 7, 1)
        assert result["publication_date"] == date(1997, 5, 21)
        assert result["price"] == 1.95
        assert result["page_count"] == 44
        assert result["upc"] == "75960601772099911"
        assert result["isbn"] == "1234567890"
        assert result["variant_name"] == "Direct Edition"
        assert "raw_payload" not in result  # raw_payload is excluded

    def test_model_dump_with_optional_fields_none(self):
        """IssueCandidate.model_dump() handles None optional fields correctly."""
        candidate = IssueCandidate(
            source="gcd",
            source_series_id="4254",
            source_issue_id="125295",
            series_title="X-Men",
            series_start_year=1991,
            publisher=None,
            issue_number="1",
            variant_suffix=None,
        )

        result = candidate.model_dump()

        assert result["publisher"] is None
        assert result["variant_suffix"] is None
        assert result["cover_date"] is None
        assert result["publication_date"] is None
        assert result["price"] is None
        assert result["page_count"] is None
        assert result["upc"] is None
        assert result["isbn"] is None
        assert result["variant_name"] is None

    def test_display_issue_number_with_variant(self):
        """display_issue_number() returns issue.variant when variant_suffix exists."""
        candidate = IssueCandidate(
            source="gcd",
            source_series_id="4254",
            source_issue_id="125295",
            series_title="X-Men",
            series_start_year=1991,
            publisher="Marvel",
            issue_number="-1",
            variant_suffix="A",
        )

        result = candidate.display_issue_number()

        assert result == "-1.A"

    def test_display_issue_number_without_variant(self):
        """display_issue_number() returns issue number when no variant_suffix."""
        candidate = IssueCandidate(
            source="gcd",
            source_series_id="4254",
            source_issue_id="125295",
            series_title="X-Men",
            series_start_year=1991,
            publisher="Marvel",
            issue_number="-1",
            variant_suffix=None,
        )

        result = candidate.display_issue_number()

        assert result == "-1"

    def test_display_issue_number_with_complex_variant(self):
        """display_issue_number() handles complex variant suffixes."""
        candidate = IssueCandidate(
            source="gcd",
            source_series_id="4254",
            source_issue_id="125295",
            series_title="X-Men",
            series_start_year=1991,
            publisher="Marvel",
            issue_number="-1",
            variant_suffix="WIZ.SIGNED",
        )

        result = candidate.display_issue_number()

        assert result == "-1.WIZ.SIGNED"
