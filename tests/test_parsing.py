from comic_identity_engine.parsing import parse_issue_candidate, ParseResult


class TestValidIssueNumbers:
    """Tests 1-10: Valid issue number formats"""

    def test_decimal_issue(self):
        result = parse_issue_candidate("0.5")
        assert result.success is True
        assert result.raw == "0.5"
        assert result.canonical_issue_number == "0.5"
        assert result.variant_suffix is None

    def test_fractional_issue(self):
        result = parse_issue_candidate("1/2")
        assert result.success is True
        assert result.raw == "1/2"
        assert result.canonical_issue_number == "1/2"
        assert result.variant_suffix is None

    def test_negative_issue_with_hash(self):
        result = parse_issue_candidate("#-1")
        assert result.success is True
        assert result.raw == "#-1"
        assert result.canonical_issue_number == "-1"
        assert result.variant_suffix is None

    def test_negative_with_variant(self):
        result = parse_issue_candidate("-1A")
        assert result.success is True
        assert result.raw == "-1A"
        assert result.canonical_issue_number == "-1"
        assert result.variant_suffix == "A"

    def test_high_number_with_distribution_code(self):
        result = parse_issue_candidate("1000.DE")
        assert result.success is True
        assert result.raw == "1000.DE"
        assert result.canonical_issue_number == "1000"
        assert result.variant_suffix == "DE"

    def test_letter_variant(self):
        result = parse_issue_candidate("12B")
        assert result.success is True
        assert result.raw == "12B"
        assert result.canonical_issue_number == "12"
        assert result.variant_suffix == "B"

    def test_zero_issue_valid(self):
        result = parse_issue_candidate("0")
        assert result.success is True
        assert result.raw == "0"
        assert result.canonical_issue_number == "0"
        assert result.variant_suffix is None

    def test_complex_variant_with_dots(self):
        result = parse_issue_candidate("-1.WIZ.SIGNED")
        assert result.success is True
        assert result.raw == "-1.WIZ.SIGNED"
        assert result.canonical_issue_number == "-1"
        assert result.variant_suffix == "WIZ.SIGNED"

    def test_whitespace_handling(self):
        result = parse_issue_candidate("  #-1  ")
        assert result.success is True
        assert result.raw == "  #-1  "
        assert result.canonical_issue_number == "-1"
        assert result.variant_suffix is None

    def test_plain_number(self):
        result = parse_issue_candidate("1")
        assert result.success is True
        assert result.raw == "1"
        assert result.canonical_issue_number == "1"
        assert result.variant_suffix is None


class TestInvalidIssueNumbers:
    """Tests 11-15: Invalid issue number formats"""

    def test_empty_string(self):
        result = parse_issue_candidate("")
        assert result.success is False
        assert result.raw == ""
        assert result.error_code == "EMPTY_INPUT"
        assert "cannot be empty" in result.error_message

    def test_whitespace_only(self):
        result = parse_issue_candidate("   ")
        assert result.success is False
        assert result.raw == "   "
        assert result.error_code == "EMPTY_INPUT"
        assert "cannot be empty" in result.error_message

    def test_only_separator_hyphen(self):
        result = parse_issue_candidate("-")
        assert result.success is False
        assert result.raw == "-"
        assert result.error_code == "ONLY_SEPARATOR"
        assert "must contain digits" in result.error_message

    def test_only_letters(self):
        result = parse_issue_candidate("ABC")
        assert result.success is False
        assert result.raw == "ABC"
        assert result.error_code == "INVALID_FORMAT"

    def test_multiple_consecutive_dots(self):
        result = parse_issue_candidate("1..2")
        assert result.success is False
        assert result.raw == "1..2"
        assert result.error_code == "INVALID_FORMAT"


class TestEdgeCases:
    """Tests 16-23: Edge cases and additional patterns"""

    def test_multi_issue_range_hyphen(self):
        result = parse_issue_candidate("1-3")
        assert result.success is False
        assert result.raw == "1-3"
        assert result.error_code == "MULTI_ISSUE_RANGE"

    def test_multi_issue_ampersand(self):
        result = parse_issue_candidate("5 & 6")
        assert result.success is False
        assert result.raw == "5 & 6"
        assert result.error_code == "MULTI_ISSUE_RANGE"

    def test_series_prefix_invalid(self):
        result = parse_issue_candidate("X-Men -1")
        assert result.success is False
        assert result.raw == "X-Men -1"
        assert result.error_code == "INVALID_FORMAT"

    def test_leading_zeros_preserved(self):
        result = parse_issue_candidate("0001")
        assert result.success is True
        assert result.raw == "0001"
        assert result.canonical_issue_number == "0001"
        assert result.variant_suffix is None

    def test_letter_range_multi_issue(self):
        result = parse_issue_candidate("1A-1C")
        assert result.success is False
        assert result.raw == "1A-1C"
        assert result.error_code == "MULTI_ISSUE_RANGE"

    def test_negative_one_valid(self):
        result = parse_issue_candidate("-1")
        assert result.success is True
        assert result.raw == "-1"
        assert result.canonical_issue_number == "-1"
        assert result.variant_suffix is None

    def test_range_one_minus_one(self):
        result = parse_issue_candidate("1-1")
        assert result.success is False
        assert result.raw == "1-1"
        assert result.error_code == "MULTI_ISSUE_RANGE"


class TestAdditionalFailureCases:
    """Additional edge case validation"""

    def test_none_input(self):
        result: ParseResult = parse_issue_candidate(None)  # type: ignore[arg-type]
        assert result.success is False
        assert result.raw == ""
        assert result.error_code == "EMPTY_INPUT"

    def test_only_separator_dot(self):
        result = parse_issue_candidate(".")
        assert result.success is False
        assert result.raw == "."
        assert result.error_code == "ONLY_SEPARATOR"

    def test_only_separator_slash(self):
        result = parse_issue_candidate("/")
        assert result.success is False
        assert result.raw == "/"
        assert result.error_code == "ONLY_SEPARATOR"

    def test_multiple_slashes(self):
        result = parse_issue_candidate("1//2")
        assert result.success is False
        assert result.raw == "1//2"
        assert result.error_code == "INVALID_FORMAT"

    def test_multiple_hyphens(self):
        result = parse_issue_candidate("1-2-3")
        assert result.success is False
        assert result.raw == "1-2-3"
        assert result.error_code == "MULTI_ISSUE_RANGE"

    def test_hash_only(self):
        result = parse_issue_candidate("#")
        assert result.success is False
        assert result.raw == "#"
        assert result.error_code == "ONLY_SEPARATOR"

    def test_comma_separated_multi(self):
        result = parse_issue_candidate("7,8")
        assert result.success is False
        assert result.raw == "7,8"
        assert result.error_code == "MULTI_ISSUE_RANGE"

    def test_invalid_variant_chars(self):
        result = parse_issue_candidate("1A!")
        assert result.success is False
        assert result.raw == "1A!"
        assert result.error_code == "INVALID_FORMAT"

    def test_variant_with_decimal_issue(self):
        result = parse_issue_candidate("1.5A")
        assert result.success is True
        assert result.canonical_issue_number == "1.5"
        assert result.variant_suffix == "A"

    def test_negative_decimal_with_variant(self):
        result = parse_issue_candidate("-0.5B")
        assert result.success is True
        assert result.canonical_issue_number == "-0.5"
        assert result.variant_suffix == "B"
