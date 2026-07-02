"""Australian address helpers (normalization, formatting, migration)."""

from __future__ import annotations

import re

AU_STATES = ("ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA")

_MULTI_SPACE = re.compile(r"\s+")


def compact_address_line(raw: object) -> str:
    """Trim and collapse internal whitespace for street / unit lines."""
    return _MULTI_SPACE.sub(" ", str(raw or "").strip())


def compact_suburb(raw: object) -> str:
    """Trim, collapse whitespace, and title-case suburb names."""
    text = _MULTI_SPACE.sub(" ", str(raw or "").strip())
    if not text:
        return ""
    return text.title()


def compact_postcode(raw: object) -> str:
    """Keep up to four postcode digits."""
    return re.sub(r"\D", "", str(raw or "").strip())[:4]


def normalize_state(raw: object) -> str:
    state = str(raw or "").strip().upper()
    if not state:
        return ""
    if state not in AU_STATES:
        raise ValueError("State must be one of: ACT, NSW, NT, QLD, SA, TAS, VIC, WA.")
    return state


def normalize_postcode(raw: object) -> str:
    pc = re.sub(r"\D", "", str(raw or "").strip())
    if not pc:
        return ""
    if len(pc) != 4:
        raise ValueError("Postcode must be 4 digits.")
    return pc


def normalize_au_address(*, line1: object, line2: object, suburb: object, state: object, postcode: object) -> dict:
    line1_s = compact_address_line(line1)
    line2_s = compact_address_line(line2)
    suburb_s = compact_suburb(suburb)
    state_s = normalize_state(state)
    postcode_s = normalize_postcode(postcode)

    if any([line2_s, suburb_s, state_s, postcode_s]) and not line1_s:
        raise ValueError("Address line 1 is required.")

    if state_s and not postcode_s:
        raise ValueError("Postcode is required when a state is selected.")
    if postcode_s and not state_s:
        raise ValueError("State is required when a postcode is entered.")

    return {
        "address_line1": line1_s,
        "address_line2": line2_s,
        "suburb": suburb_s,
        "state": state_s,
        "postcode": postcode_s,
    }


def format_address_lines(addr: dict | None) -> list[str]:
    addr = addr or {}
    line1 = (addr.get("address_line1") or "").strip()
    line2 = (addr.get("address_line2") or "").strip()
    suburb = (addr.get("suburb") or "").strip()
    state = (addr.get("state") or "").strip().upper()
    postcode = (addr.get("postcode") or "").strip()

    lines: list[str] = []
    if line1:
        lines.append(line1)
    if line2:
        lines.append(line2)

    city_parts = [p for p in [suburb, state, postcode] if p]
    if city_parts:
        lines.append(" ".join(city_parts))
    return lines


def format_address_multiline(addr: dict | None) -> str:
    return "\n".join(format_address_lines(addr))


def migrate_legacy_address(old_string: object) -> dict:
    """Best-effort conversion from old free-text address to structured fields.

    Heuristic:
    - Split on commas into chunks
    - First chunk => line1
    - Remaining chunks => try to infer suburb/state/postcode
    """
    raw = str(old_string or "").strip()
    if not raw:
        return {
            "address_line1": "",
            "address_line2": "",
            "suburb": "",
            "state": "",
            "postcode": "",
        }

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return {
            "address_line1": raw,
            "address_line2": "",
            "suburb": "",
            "state": "",
            "postcode": "",
        }

    line1 = parts[0]
    tail = " ".join(parts[1:]).strip()

    postcode = ""
    state = ""
    suburb = ""

    if tail:
        tokens = tail.split()
        if tokens and re.fullmatch(r"\d{4}", tokens[-1]):
            postcode = tokens.pop(-1)
        if tokens and tokens[-1].upper() in AU_STATES:
            state = tokens.pop(-1).upper()
        suburb = " ".join(tokens).strip()

    return {
        "address_line1": line1,
        "address_line2": "",
        "suburb": suburb,
        "state": state,
        "postcode": postcode,
    }

