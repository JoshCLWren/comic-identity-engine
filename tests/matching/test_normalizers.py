"""Tests for GCD matching normalizer functions."""

from comic_identity_engine.matching.normalizers import (
    normalize_publisher,
    normalize_series_name,
    normalize_series_name_strict,
    parse_issue_nr,
    parse_year,
    strip_diacritics,
    strip_subtitle,
    strip_vol_suffix,
)


class TestStripVolSuffix:
    def test_strips_vol_dot_number(self) -> None:
        assert strip_vol_suffix("X-Men, Vol. 1") == "X-Men"

    def test_strips_vol_without_dot(self) -> None:
        assert strip_vol_suffix("X-Men, Vol 2") == "X-Men"

    def test_strips_volume_spelled_out(self) -> None:
        assert strip_vol_suffix("X-Men, Volume 3") == "X-Men"

    def test_strips_vol_without_comma(self) -> None:
        assert strip_vol_suffix("X-Men Vol. 1") == "X-Men"

    def test_no_vol_unchanged(self) -> None:
        assert strip_vol_suffix("X-Men") == "X-Men"

    def test_vol_in_middle_unchanged(self) -> None:
        # Only strips from END
        assert strip_vol_suffix("Vol. 1 Special") == "Vol. 1 Special"


class TestStripSubtitle:
    def test_strips_colon_subtitle(self) -> None:
        assert strip_subtitle("WildC.A.T.s: Covert Action Teams") == "WildC.A.T.s"

    def test_no_colon_unchanged(self) -> None:
        assert strip_subtitle("X-Men") == "X-Men"

    def test_dash_unchanged(self) -> None:
        assert strip_subtitle("Spider-Man") == "Spider-Man"

    def test_strips_only_last_colon(self) -> None:
        result = strip_subtitle("A: B: C")
        assert result == "A: B"


class TestNormalizeSeriesName:
    def test_strips_vol_suffix(self) -> None:
        assert normalize_series_name("X-Men, Vol. 1") == "X-Men"

    def test_strips_publisher_parens(self) -> None:
        assert normalize_series_name("X-Men (Marvel Comics)") == "X-Men"

    def test_strips_roman_numeral_ii(self) -> None:
        assert normalize_series_name("X-Men II") == "X-Men"

    def test_strips_annual(self) -> None:
        assert normalize_series_name("X-Men Annual") == "X-Men"

    def test_strips_year_parens(self) -> None:
        assert normalize_series_name("X-Men (1991)") == "X-Men"

    def test_plain_name_unchanged(self) -> None:
        assert normalize_series_name("Amazing Spider-Man") == "Amazing Spider-Man"

    def test_preserves_hyphens(self) -> None:
        assert normalize_series_name("Spider-Man") == "Spider-Man"


class TestNormalizeSeriesNameStrict:
    def test_lowercases(self) -> None:
        assert normalize_series_name_strict("X-Men") == "xmen"

    def test_ampersand_to_and(self) -> None:
        assert normalize_series_name_strict("Cloak & Dagger") == "cloak and dagger"

    def test_strips_punctuation(self) -> None:
        assert normalize_series_name_strict("WildC.A.T.s") == "wildcats"

    def test_normalizes_whitespace(self) -> None:
        assert normalize_series_name_strict("X  Men") == "x men"

    def test_chains_vol_strip(self) -> None:
        assert normalize_series_name_strict("X-Men, Vol. 1") == "xmen"


class TestNormalizePublisher:
    def test_strips_comics_suffix(self) -> None:
        assert normalize_publisher("Marvel Comics") == "marvel"

    def test_strips_dc_comics(self) -> None:
        assert normalize_publisher("DC Comics") == "dc"

    def test_strips_publishing_suffix(self) -> None:
        assert normalize_publisher("Image Publishing") == "image"

    def test_strips_entertainment_suffix(self) -> None:
        assert normalize_publisher("Valiant Entertainment") == "valiant"

    def test_strips_parens(self) -> None:
        assert normalize_publisher("Marvel (US)") == "marvel"

    def test_takes_primary_for_joint(self) -> None:
        assert normalize_publisher("Marvel Comics and DC Comics") == "marvel"

    def test_empty_string(self) -> None:
        assert normalize_publisher("") == ""

    def test_lowercases(self) -> None:
        assert normalize_publisher("Dark Horse Comics") == "dark horse"


class TestParseIssueNr:
    def test_parses_integer_string(self) -> None:
        assert parse_issue_nr({"Issue Nr": "42"}) == "42"

    def test_parses_float_string(self) -> None:
        assert parse_issue_nr({"Issue Nr": "42.0"}) == "42"

    def test_returns_one_for_empty(self) -> None:
        assert parse_issue_nr({"Issue Nr": ""}) == "1"

    def test_returns_one_for_missing_key(self) -> None:
        assert parse_issue_nr({}) == "1"

    def test_returns_none_for_non_numeric(self) -> None:
        assert parse_issue_nr({"Issue Nr": "AU"}) is None

    def test_strips_whitespace(self) -> None:
        assert parse_issue_nr({"Issue Nr": "  42  "}) == "42"


class TestParseYear:
    def test_parses_valid_integer(self) -> None:
        assert parse_year({"Cover Year": 1991}) == 1991

    def test_parses_valid_string(self) -> None:
        assert parse_year({"Cover Year": "1991"}) == 1991

    def test_returns_none_for_empty(self) -> None:
        assert parse_year({"Cover Year": ""}) is None

    def test_returns_none_for_missing_key(self) -> None:
        assert parse_year({}) is None

    def test_returns_none_for_out_of_range_low(self) -> None:
        assert parse_year({"Cover Year": 1900}) is None

    def test_returns_none_for_out_of_range_high(self) -> None:
        assert parse_year({"Cover Year": 2030}) is None

    def test_returns_none_for_non_numeric(self) -> None:
        assert parse_year({"Cover Year": "nineteen ninety-one"}) is None

    def test_parses_float_string(self) -> None:
        assert parse_year({"Cover Year": "1991.0"}) == 1991


class TestStripDiacritics:
    def test_strips_umlaut(self) -> None:
        assert strip_diacritics("Rōnin") == "Ronin"

    def test_strips_accent(self) -> None:
        assert strip_diacritics("café") == "cafe"

    def test_strips_tilde(self) -> None:
        assert strip_diacritics("Español") == "Espanol"

    def test_preserves_plain_ascii(self) -> None:
        assert strip_diacritics("X-Men") == "X-Men"

    def test_strips_combining_characters(self) -> None:
        assert strip_diacritics("naïve") == "naive"

    def test_handles_empty_string(self) -> None:
        assert strip_diacritics("") == ""

    def test_strips_circumflex(self) -> None:
        assert strip_diacritics("Dûn") == "Dun"

    def test_strips_cedilla(self) -> None:
        assert strip_diacritics("garçon") == "garcon"
