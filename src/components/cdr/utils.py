def mask_phone_number(value: str, visible_last: int = 4, visible_first: int = 1) -> str:
    """
    Masks phone number like: +9*******7787
    - visible_first: number of digits to show at the start (default 1 → shows +9)
    - visible_last: number of digits to show at the end (default 4)
    """
    if not value:
        return ""

    # Extract only digits
    digits = "".join(filter(str.isdigit, value))

    if len(digits) <= visible_first + visible_last:
        return "*" * len(digits)

    first_part = digits[:visible_first]
    last_part = digits[-visible_last:]
    middle_length = len(digits) - visible_first - visible_last

    masked = first_part + "*" * middle_length + last_part

    # Add '+' back if original value had it
    if value.startswith("+"):
        return "+" + masked

    return masked
