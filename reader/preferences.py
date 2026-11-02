"""Validate persisted reading preferences independently of Qt and the browser."""

from __future__ import annotations

import math

DEFAULTS = {
    "theme": "light",
    "direction": "smart",
    "fontSize": 17,
    "lineHeight": 2,
    "wide": False,
    "syncScroll": True,
    "previewZoom": 100,
}
SIDEBAR_SECTIONS = ("files", "library", "outline")


def bounded_number(value, default, minimum, maximum, *, integer=False):
    """Repair invalid values before clamping; NaN and infinity are never persisted."""
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return default
    if isinstance(value, bool) or not math.isfinite(number):
        return default
    number = max(minimum, min(maximum, number))
    return int(number) if integer else number


def normalize_preferences(values: object) -> dict:
    """Return a fresh, complete settings object containing only supported fields."""
    values = values if isinstance(values, dict) else {}
    result = dict(DEFAULTS)
    for key, options in (("theme", ("light", "dark")), ("direction", ("smart", "rtl", "ltr"))):
        if values.get(key) in options:
            result[key] = values[key]
    for key in ("wide", "syncScroll"):
        if isinstance(values.get(key), bool):
            result[key] = values[key]
    for key, minimum, maximum, integer in (
        ("fontSize", 14, 24, True),
        ("lineHeight", 1.6, 2.6, False),
        ("previewZoom", 50, 300, True),
    ):
        result[key] = bounded_number(
            values.get(key), DEFAULTS[key], minimum, maximum, integer=integer
        )
    sidebar = values.get("sidebar")
    sidebar = sidebar if isinstance(sidebar, dict) else {}
    result["sidebar"] = {}
    for key in SIDEBAR_SECTIONS:
        entry = sidebar.get(key)
        entry = entry if isinstance(entry, dict) else {}
        result["sidebar"][key] = {
            "open": entry.get("open") is not False,
            "weight": bounded_number(entry.get("weight"), 1, 0.01, 100),
        }
    return result
