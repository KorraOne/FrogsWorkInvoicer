"""Input normalization and validation helpers.

These functions are used for user-entered business and customer fields where we want
to accept flexible formatting (spaces/dashes) but store a consistent canonical form.
"""

from __future__ import annotations

import re


def _digits(raw: object) -> str:
    return re.sub(r"\D", "", str(raw or ""))


def normalize_abn(raw: object) -> str:
    """Return ABN digits (11) or empty string.

    Accepts any separators. Raises ValueError if non-empty and not 11 digits.
    """
    digits = _digits(raw).strip()
    if not digits:
        return ""
    if len(digits) != 11:
        raise ValueError("ABN must be 11 digits.")
    return digits


def normalize_bsb(raw: object) -> str:
    """Return BSB as XXX-XXX or empty string.

    Accepts xxxxxx, xxx xxx, xxx-xxx. Raises ValueError if non-empty and not 6 digits.
    """
    digits = _digits(raw).strip()
    if not digits:
        return ""
    if len(digits) != 6:
        raise ValueError("BSB must be 6 digits.")
    return f"{digits[0:3]}-{digits[3:6]}"


def normalize_account_number(raw: object) -> str:
    """Return account number digits (5–9) or empty string.

    Raises ValueError if non-empty and outside the accepted range.
    """
    digits = _digits(raw).strip()
    if not digits:
        return ""
    if not (5 <= len(digits) <= 9):
        raise ValueError("Account number must be 5–9 digits.")
    return digits

