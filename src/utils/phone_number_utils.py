import re


def _clean_number(number: str) -> str:
    """Remove all characters except digits and +"""
    return re.sub(r"[^\d+]", "", number.strip())


def _normalize_with_plus(cleaned: str) -> str:
    """Handle numbers that already start with +"""
    digits = cleaned[1:]
    if digits.startswith("91") and len(digits) == 12:
        return cleaned
    if len(digits) == 10 and digits[0] != "0":
        return "+91" + digits
    return cleaned


def _normalize_indian_number(digits: str, with_plus: bool = True) -> str:
    """
    Handle Indian number normalization.
    with_plus=True  → +91XXXXXXXXXX
    with_plus=False → 91XXXXXXXXXX
    """
    prefix = "+91" if with_plus else "91"

    if digits.startswith("91") and len(digits) == 12:
        return ("+" if with_plus else "") + digits
    if len(digits) == 11 and digits.startswith("0"):
        return prefix + digits[1:]
    if len(digits) == 10:
        return prefix + digits
    return prefix + digits if digits else ""


def normalize_phone_number(number: str, with_plus: bool = True) -> str:
    """
    Normalize phone numbers.

    Args:
        number:    Raw phone number string.
        with_plus: If True  → E.164 format  e.g. +91XXXXXXXXXX (default)
                   If False → No + prefix   e.g.  91XXXXXXXXXX

    Examples:
        normalize_phone_number("9876543210")               → "+919876543210"
        normalize_phone_number("9876543210", with_plus=False) → "919876543210"
        normalize_phone_number("+919876543210", with_plus=False) → "919876543210"
        normalize_phone_number("09876543210", with_plus=False)   → "919876543210"
    """
    if not number:
        return ""

    cleaned = _clean_number(number)

    if cleaned.startswith("+"):
        normalized = _normalize_with_plus(cleaned)
        # Strip + if with_plus=False
        return normalized.lstrip("+") if not with_plus else normalized

    digits = re.sub(r"\D", "", cleaned)
    return _normalize_indian_number(digits, with_plus=with_plus)
