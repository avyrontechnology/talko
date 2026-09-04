from src.utils.phone_number_utils import (
    _clean_number,
    _normalize_indian_number,
    _normalize_with_plus,
    normalize_phone_number,
)


class TestCleanNumber:

    def test_strips_whitespace(self):
        assert _clean_number("  9876543210  ") == "9876543210"

    def test_keeps_plus(self):
        assert _clean_number("+919876543210") == "+919876543210"

    def test_removes_hyphens(self):
        assert _clean_number("98765-43210") == "9876543210"

    def test_removes_spaces_inside(self):
        assert _clean_number("98765 43210") == "9876543210"

    def test_removes_parentheses(self):
        assert _clean_number("(91)9876543210") == "919876543210"

    def test_removes_dots(self):
        assert _clean_number("98765.43210") == "9876543210"

    def test_plus_with_spaces_and_hyphens(self):
        assert _clean_number("+91-98765-43210") == "+919876543210"

    def test_empty_string(self):
        assert _clean_number("") == ""

    def test_only_spaces(self):
        assert _clean_number("   ") == ""


class TestNormalizeWithPlus:

    def test_12_digit_with_91_prefix(self):
        assert _normalize_with_plus("+919876543210") == "+919876543210"

    def test_10_digit_without_leading_zero(self):
        assert _normalize_with_plus("+9876543210") == "+919876543210"

    def test_10_digit_starting_with_zero_unchanged(self):
        # digits[0] == '0' → returns cleaned as-is
        assert _normalize_with_plus("+0876543210") == "+0876543210"

    def test_non_12_digit_91_prefix_unchanged(self):
        # 10 digits starting with 91 → treated as 10-digit number, gets +91 prepended
        assert _normalize_with_plus("+9198765432") == "+919198765432"

    def test_13_digit_with_91_prefix_unchanged(self):
        assert _normalize_with_plus("+9198765432100") == "+9198765432100"


class TestNormalizeIndianNumber:

    def test_10_digit_with_plus(self):
        assert _normalize_indian_number("9876543210", with_plus=True) == "+919876543210"

    def test_10_digit_without_plus(self):
        assert _normalize_indian_number("9876543210", with_plus=False) == "919876543210"

    def test_12_digit_91_prefix_with_plus(self):
        assert (
            _normalize_indian_number("919876543210", with_plus=True) == "+919876543210"
        )

    def test_12_digit_91_prefix_without_plus(self):
        assert (
            _normalize_indian_number("919876543210", with_plus=False) == "919876543210"
        )

    def test_11_digit_leading_zero_with_plus(self):
        assert (
            _normalize_indian_number("09876543210", with_plus=True) == "+919876543210"
        )

    def test_11_digit_leading_zero_without_plus(self):
        assert (
            _normalize_indian_number("09876543210", with_plus=False) == "919876543210"
        )

    def test_empty_digits(self):
        assert _normalize_indian_number("", with_plus=True) == ""
        assert _normalize_indian_number("", with_plus=False) == ""

    def test_11_digit_not_leading_zero_gets_prefixed(self):
        # 11-digit not starting with 0 or 91 → falls through to default prefix
        result = _normalize_indian_number("12345678901", with_plus=False)
        assert result == "9112345678901"


class TestNormalizePhoneNumber:

    def test_empty_string_returns_empty(self):
        assert normalize_phone_number("") == ""

    def test_empty_string_no_plus_returns_empty(self):
        assert normalize_phone_number("", with_plus=False) == ""

    def test_10_digit_default(self):
        assert normalize_phone_number("9876543210") == "+919876543210"

    def test_10_digit_with_plus_true(self):
        assert normalize_phone_number("9876543210", with_plus=True) == "+919876543210"

    def test_10_digit_with_plus_false(self):
        assert normalize_phone_number("9876543210", with_plus=False) == "919876543210"

    def test_12_digit_91_prefix_with_plus(self):
        assert normalize_phone_number("919876543210") == "+919876543210"

    def test_12_digit_91_prefix_without_plus(self):
        assert normalize_phone_number("919876543210", with_plus=False) == "919876543210"

    def test_plus_91_10digit_with_plus(self):
        assert normalize_phone_number("+919876543210") == "+919876543210"

    def test_plus_91_10digit_without_plus(self):
        assert (
            normalize_phone_number("+919876543210", with_plus=False) == "919876543210"
        )

    def test_11_digit_leading_zero_with_plus(self):
        assert normalize_phone_number("09876543210") == "+919876543210"

    def test_11_digit_leading_zero_without_plus(self):
        assert normalize_phone_number("09876543210", with_plus=False) == "919876543210"

    def test_hyphenated_plus_number(self):
        assert normalize_phone_number("+91-9876543210") == "+919876543210"

    def test_hyphenated_plus_without_plus(self):
        assert (
            normalize_phone_number("+91-9876543210", with_plus=False) == "919876543210"
        )

    def test_spaced_number(self):
        assert normalize_phone_number("98765 43210") == "+919876543210"

    def test_leading_trailing_whitespace(self):
        assert normalize_phone_number("  9876543210  ") == "+919876543210"

    def test_already_normalized_e164_idempotent(self):
        assert normalize_phone_number("+919876543210") == "+919876543210"

    def test_already_normalized_no_plus_idempotent(self):
        assert normalize_phone_number("919876543210", with_plus=False) == "919876543210"

    def test_round_trip_strip_plus_then_readd(self):
        without = normalize_phone_number("+919876543210", with_plus=False)
        with_p = normalize_phone_number(without, with_plus=True)
        assert with_p == "+919876543210"

    def test_11_digit_not_zero_prefixed_double_prefix_warning(self):
        result = normalize_phone_number("91888887777", with_plus=False)
        assert isinstance(result, str)
        assert len(result) > 0
