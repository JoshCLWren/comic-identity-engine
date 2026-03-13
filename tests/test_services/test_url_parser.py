"""Tests for URL parser service."""

import pytest

from comic_identity_engine.services.url_parser import (
    parse_url,
    ParsedUrl,
)
from comic_identity_engine.errors import ParseError


class TestParseUrl:
    """Tests for parse_url function."""

    def test_parse_gcd_issue_url(self):
        """Test parsing GCD issue URL."""
        url = "https://www.comics.org/issue/125295/"
        result = parse_url(url)

        assert result.platform == "gcd"
        assert result.source_issue_id == "125295"
        assert result.source_series_id is None
        assert result.variant_suffix is None

    def test_parse_gcd_issue_url_without_trailing_slash(self):
        """Test parsing GCD issue URL without trailing slash."""
        url = "https://www.comics.org/issue/125295"
        result = parse_url(url)

        assert result.platform == "gcd"
        assert result.source_issue_id == "125295"

    def test_parse_gcd_series_url(self):
        """Test parsing GCD series URL."""
        url = "https://www.comics.org/series/4254/"
        result = parse_url(url)

        assert result.platform == "gcd"
        assert result.source_issue_id == "4254"
        assert result.source_series_id == "4254"

    def test_parse_locg_url_with_variant(self):
        """Test parsing LoCG URL with variant parameter."""
        url = "https://leagueofcomicgeeks.com/comic/1169529/x-men-1?variant=6930677"
        result = parse_url(url)

        assert result.platform == "locg"
        assert result.source_issue_id == "6930677"
        assert result.source_series_id == "1169529"

    def test_parse_locg_url_without_variant(self):
        """Test parsing LoCG URL without variant parameter."""
        url = "https://leagueofcomicgeeks.com/comic/111275/x-men-1"
        result = parse_url(url)

        assert result.platform == "locg"
        # LoCG URLs use /comic/ISSUE_ID[/slug] format where the first number is the issue ID
        assert result.source_issue_id == "111275"
        assert result.source_series_id is None

    def test_parse_ccl_url_with_guid(self):
        """Test parsing CCL URL with GUID."""
        url = "https://www.comiccollectorlive.com/issue/comic-books/X-Men-1991/-1/98ab98c9-a87a-4cd2-b49a-ee5232abc0ad"
        result = parse_url(url)

        assert result.platform == "ccl"
        assert result.source_issue_id == "98ab98c9-a87a-4cd2-b49a-ee5232abc0ad"

    def test_parse_ccl_url_with_variant(self):
        """Test parsing CCL URL with variant in slug."""
        url = "https://www.comiccollectorlive.com/issue/-1-B-Chris-Bachalo-Cover/f352ec33-f77b-4fa6-9d47-7927c39c4a9b"
        result = parse_url(url)

        assert result.platform == "ccl"
        assert result.source_issue_id == "f352ec33-f77b-4fa6-9d47-7927c39c4a9b"

    def test_parse_aa_url(self):
        """Test parsing Atomic Avenue URL."""
        url = "https://atomicavenue.com/atomic/item/217255/1/XMen-2nd-Series-XMen-2nd-Series-1"
        result = parse_url(url)

        assert result.platform == "aa"
        assert result.source_issue_id == "217255"

    def test_parse_aa_series_url(self):
        """Test parsing Atomic Avenue series URL."""
        url = "https://atomicavenue.com/atomic/series/217254"
        result = parse_url(url)

        assert result.platform == "aa"
        assert result.source_issue_id == "217254"
        assert result.source_series_id == "217254"

    def test_parse_cpg_url(self):
        """Test parsing CPG URL."""
        url = "https://www.comicspriceguide.com/titles/x-men/-1/phvpiu"
        result = parse_url(url)

        assert result.platform == "cpg"
        assert result.source_issue_id == "phvpiu"

    def test_parse_cpg_url_with_variant(self):
        """Test parsing CPG URL with variant."""
        url = "https://www.comicspriceguide.com/titles/x-men/-1B/pkxpbvq"
        result = parse_url(url)

        assert result.platform == "cpg"
        assert result.source_issue_id == "pkxpbvq"
        assert result.variant_suffix == "B"

    def test_parse_hip_url(self):
        """Test parsing HIP Comic URL."""
        url = "https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/"
        result = parse_url(url)

        assert result.platform == "hip"
        assert result.source_issue_id == "1-1"
        assert result.source_series_id == "x-men-1991"

    def test_parse_hip_url_with_variant(self):
        """Test parsing HIP Comic URL with variant."""
        url = "https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/direct-edition/"
        result = parse_url(url)

        assert result.platform == "hip"
        assert result.source_issue_id == "1-1"
        assert result.variant_suffix == "directedition"

    def test_parse_hip_url_with_query_string(self):
        """Test parsing HIP Comic URL with query string."""
        url = "https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/?keywords="
        result = parse_url(url)

        assert result.platform == "hip"
        assert result.source_issue_id == "1-1"
        assert result.source_series_id == "x-men-1991"
        assert result.variant_suffix is None
        assert result.full_url == url

    def test_parse_url_empty_string(self):
        """Test parsing empty string raises ParseError."""
        with pytest.raises(ParseError, match="must be a non-empty string"):
            parse_url("")

    def test_parse_url_none(self):
        """Test parsing None raises ParseError."""
        with pytest.raises(ParseError, match="must be a non-empty string"):
            parse_url(None)  # type: ignore[arg-type]

    def test_parse_url_without_protocol(self):
        """Test parsing URL without protocol raises ParseError."""
        with pytest.raises(ParseError, match="must start with http:// or https://"):
            parse_url("www.comics.org/issue/125295/")

    def test_parse_unsupported_url(self):
        """Test parsing unsupported URL raises ParseError."""
        with pytest.raises(ParseError, match="Unsupported or unrecognized URL format"):
            parse_url("https://www.example.com/comic/123")

    def test_parse_clz_url_raises_not_implemented(self):
        """Test parsing CLZ URL raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="CLZ.*CSV import"):
            parse_url("https://comicbookdb.com/title.cgi?title=9547")

    def test_parse_malformed_url(self):
        """Test parsing malformed URL raises ParseError."""
        with pytest.raises(ParseError):
            parse_url("https://www.comics.org/invalid/")

    def test_parse_url_with_whitespace(self):
        """Test parsing URL with leading/trailing whitespace."""
        url = "  https://www.comics.org/issue/125295/  "
        result = parse_url(url)

        assert result.platform == "gcd"
        assert result.source_issue_id == "125295"


class TestParsedUrlDataclass:
    """Tests for ParsedUrl dataclass."""

    def test_parsed_url_attributes(self):
        """Test ParsedUrl has correct attributes."""
        parsed = ParsedUrl(
            platform="gcd",
            source_issue_id="125295",
            source_series_id="4254",
            variant_suffix="A",
        )

        assert parsed.platform == "gcd"
        assert parsed.source_issue_id == "125295"
        assert parsed.source_series_id == "4254"
        assert parsed.variant_suffix == "A"

    def test_parsed_url_defaults(self):
        """Test ParsedUrl default values."""
        parsed = ParsedUrl(
            platform="gcd",
            source_issue_id="125295",
        )

        assert parsed.source_series_id is None
        assert parsed.variant_suffix is None


class TestLoCGUrlParser:
    """Tests for LoCG URL parser edge cases."""

    def test_parse_locg_series_url(self):
        """Test parsing LoCG series URL (not issue)."""
        url = "https://leagueofcomicgeeks.com/comics/series/111275/x-men-2021"
        result = parse_url(url)

        assert result.platform == "locg"
        assert result.source_issue_id == "111275"
        assert result.source_series_id == "111275"

    def test_parse_locg_url_numeric_issue_id(self):
        """Test parsing LoCG URL with numeric issue ID format (alternative pattern)."""
        url = "https://leagueofcomicgeeks.com/comic/111275/6930677"
        result = parse_url(url)

        assert result.platform == "locg"
        assert result.source_issue_id == "6930677"
        assert result.source_series_id == "111275"

    def test_parse_locg_malformed_url(self):
        """Test parsing malformed LoCG URL raises ParseError."""
        with pytest.raises(ParseError, match="Invalid LoCG URL format"):
            parse_url("https://leagueofcomicgeeks.com/invalid/path")


class TestCCLUrlParser:
    """Tests for CCL URL parser edge cases."""

    def test_parse_ccl_malformed_url(self):
        """Test parsing malformed CCL URL without GUID raises ParseError."""
        with pytest.raises(ParseError, match="Invalid CCL URL format"):
            parse_url("https://www.comiccollectorlive.com/issue/invalid")


class TestAAParser:
    """Tests for Atomic Avenue URL parser edge cases."""

    def test_parse_aa_url_with_variant_suffix(self):
        """Test parsing AA URL with variant suffix (not 1)."""
        url = "https://atomicavenue.com/atomic/item/217255/2/XMen-Variant"
        result = parse_url(url)

        assert result.platform == "aa"
        assert result.source_issue_id == "217255"
        assert result.variant_suffix == "2"

    def test_parse_aa_malformed_url(self):
        """Test parsing malformed AA URL raises ParseError."""
        with pytest.raises(ParseError, match="Invalid AA URL format"):
            parse_url("https://atomicavenue.com/atomic/invalid/123")


class TestCPGParser:
    """Tests for Comics Price Guide URL parser edge cases."""

    def test_parse_cpg_series_url(self):
        """Test parsing CPG series URL."""
        url = "https://www.comicspriceguide.com/titles/x-men-2021"
        result = parse_url(url)

        assert result.platform == "cpg"
        assert result.source_issue_id == "x-men-2021"
        assert result.source_series_id == "x-men-2021"

    def test_parse_cpg_issue_with_negative_one_variant(self):
        """Test parsing CPG URL with -1 issue and variant suffix (e.g., -1ABC)."""
        url = "https://www.comicspriceguide.com/titles/x-men/-1ABC/phvpiu"
        result = parse_url(url)

        assert result.platform == "cpg"
        assert result.source_issue_id == "phvpiu"
        assert result.variant_suffix == "ABC"

    def test_parse_cpg_issue_with_variant_suffix(self):
        """Test parsing CPG URL with variant suffix."""
        url = "https://www.comicspriceguide.com/titles/x-men/1-A/pkxpbvq"
        result = parse_url(url)

        assert result.platform == "cpg"
        assert result.source_issue_id == "pkxpbvq"
        assert result.variant_suffix == "A"

    def test_parse_cpg_issue_with_hyphen_in_number(self):
        """Test parsing CPG URL with hyphen in number (not variant)."""
        url = "https://www.comicspriceguide.com/titles/x-men/1-2/pkxpbvq"
        result = parse_url(url)

        assert result.platform == "cpg"
        assert result.source_issue_id == "pkxpbvq"
        assert result.variant_suffix is None

    def test_parse_cpg_malformed_url(self):
        """Test parsing malformed CPG URL raises ParseError."""
        with pytest.raises(ParseError, match="Invalid CPG URL format"):
            parse_url("https://www.comicspriceguide.com/invalid/path")


class TestHIPParser:
    """Tests for Hip Comic URL parser edge cases."""

    def test_parse_hip_series_url(self):
        """Test parsing HIP series URL."""
        url = "https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991"
        result = parse_url(url)

        assert result.platform == "hip"
        assert result.source_issue_id == "x-men-1991"
        assert result.source_series_id == "x-men-1991"

    def test_parse_hip_url_with_keywords_suffix(self):
        """Test parsing HIP URL with keywords suffix (should not be treated as variant)."""
        url = "https://www.hipcomic.com/price-guide/us/marvel/comic/x-men-1991/1-1/keywords"
        result = parse_url(url)

        assert result.platform == "hip"
        assert result.source_issue_id == "1-1"
        assert result.variant_suffix is None

    def test_parse_hip_malformed_url(self):
        """Test parsing malformed HIP URL raises ParseError."""
        with pytest.raises(ParseError, match="Invalid HIP URL format"):
            parse_url("https://www.hipcomic.com/price-guide/invalid")


class TestGCDParser:
    """Tests for GCD URL parser edge cases."""

    def test_parse_gcd_malformed_url(self):
        """Test parsing malformed GCD URL raises ParseError."""
        with pytest.raises(ParseError, match="Invalid GCD URL format"):
            parse_url("https://www.comics.org/invalid/123")


class TestUrlParserEdgeCases:
    """Tests for edge cases across all platforms."""

    def test_parse_non_string_input(self):
        """Test parsing non-string input raises ParseError."""
        with pytest.raises(ParseError, match="must be a non-empty string"):
            parse_url(123)  # type: ignore[arg-type]

    def test_parse_url_with_unexpected_query_params(self):
        """Test parsing URL with unexpected query parameters still works."""
        url = "https://www.comics.org/issue/125295/?foo=bar&baz=qux"
        result = parse_url(url)

        assert result.platform == "gcd"
        assert result.source_issue_id == "125295"

    def test_parse_locg_url_with_multiple_query_params(self):
        """Test parsing LoCG URL with multiple query parameters."""
        url = "https://leagueofcomicgeeks.com/comic/111275/x-men-1?variant=6930677&foo=bar"
        result = parse_url(url)

        assert result.platform == "locg"
        assert result.source_issue_id == "6930677"
        assert result.source_series_id == "111275"

    def test_parse_url_with_fragment(self):
        """Test parsing URL with fragment identifier."""
        url = "https://www.comics.org/issue/125295/#details"
        result = parse_url(url)

        assert result.platform == "gcd"
        assert result.source_issue_id == "125295"

    def test_parse_url_case_insensitive_path(self):
        """Test parsing URL with uppercase path doesn't match regex."""
        # Regex patterns are case-sensitive
        with pytest.raises(ParseError, match="Invalid GCD URL format"):
            parse_url("https://www.comics.org/ISSUE/125295/")

    def test_parse_url_with_http_protocol(self):
        """Test parsing URL with http (not https) protocol."""
        url = "http://www.comics.org/issue/125295/"
        result = parse_url(url)

        assert result.platform == "gcd"
        assert result.source_issue_id == "125295"

    def test_parse_platform_detection_with_similar_domains(self):
        """Test platform detection with similar domain pattern."""
        # fakecomics.org is not in the domain list, so it should not match
        # The urlparse-based implementation prevents domain spoofing
        with pytest.raises(ParseError, match="Unsupported or unrecognized URL format"):
            parse_url("https://fakecomics.org/not-an-issue-path")

    def test_parse_url_with_port(self):
        """Test parsing URL with port number works correctly with urlparse."""
        # urlparse correctly extracts the domain without the port
        url = "https://www.comics.org:443/issue/125295/"
        result = parse_url(url)

        assert result.platform == "gcd"
        assert result.source_issue_id == "125295"

    def test_parse_url_with_auth(self):
        """Test parsing URL with authentication (unusual but valid)."""
        url = "https://user:pass@www.comics.org/issue/125295/"
        result = parse_url(url)

        assert result.platform == "gcd"
        assert result.source_issue_id == "125295"
