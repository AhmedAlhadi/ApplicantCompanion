"""Normalize freeform career dates to YYYY-MM for String(10) columns."""
from __future__ import annotations

import re
from typing import Any

_OPEN_ENDED = {
    "",
    "present",
    "current",
    "now",
    "ongoing",
    "today",
    "n/a",
    "na",
    "none",
    "null",
    "حتى الآن",
    "حتى الان",
    "الحالي",
    "حاليا",
    "حالياً",
}

_MONTHS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
    "يناير": 1,
    "كانون الثاني": 1,
    "فبراير": 2,
    "شباط": 2,
    "مارس": 3,
    "آذار": 3,
    "اذار": 3,
    "أبريل": 4,
    "ابريل": 4,
    "نيسان": 4,
    "مايو": 5,
    "أيار": 5,
    "ايار": 5,
    "يونيو": 6,
    "يونيه": 6,
    "حزيران": 6,
    "يوليو": 7,
    "يوليه": 7,
    "تموز": 7,
    "أغسطس": 8,
    "اغسطس": 8,
    "آب": 8,
    "اب": 8,
    "سبتمبر": 9,
    "أيلول": 9,
    "ايلول": 9,
    "تشرين الأول": 10,
    "تشرين الاول": 10,
    "أكتوبر": 10,
    "اكتوبر": 10,
    "تشرين الثاني": 11,
    "نوفمبر": 11,
    "كانون الأول": 12,
    "كانون الاول": 12,
    "ديسمبر": 12,
}

_MONTH_NAMES = tuple(sorted(_MONTHS, key=len, reverse=True))
_MONTH_RE = re.compile(
    r"(?<![a-zA-Z\u0600-\u06FF])("
    + "|".join(re.escape(name) for name in _MONTH_NAMES)
    + r")(?![a-zA-Z\u0600-\u06FF])",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?![0-9sS])")
_ISO_RE = re.compile(r"^(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?$")
_MONTH_YEAR_NUM_RE = re.compile(r"^(\d{1,2})[-/](\d{4})$")
_YEAR_ONLY_RE = re.compile(r"^(\d{4})$")
_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DATE_FIELDS = (
    "start_date",
    "end_date",
    "issue_date",
    "expiry_date",
    "publication_date",
)


def _fmt(year: int, month: int) -> str | None:
    if not 1 <= month <= 12 or not 1900 <= year <= 2100:
        return None
    return f"{year:04d}-{month:02d}"


def normalize_career_date(value: Any) -> str | None:
    """Coerce a CV-style date to YYYY-MM (or YYYY when the month is unknown).

    Open-ended values such as Present become None. Unparseable values also
    become None so they never overflow career date columns (varchar(10)).
    """
    if value is None:
        return None
    raw = str(value).translate(_DIGIT_MAP).strip()
    raw = re.sub(r"\s+", " ", raw).strip(" .,;/")
    if not raw:
        return None
    lowered = raw.casefold()
    if lowered in _OPEN_ENDED:
        return None

    iso = _ISO_RE.match(raw)
    if iso:
        return _fmt(int(iso.group(1)), int(iso.group(2)))

    month_year = _MONTH_YEAR_NUM_RE.match(raw)
    if month_year:
        return _fmt(int(month_year.group(2)), int(month_year.group(1)))

    year_only = _YEAR_ONLY_RE.match(raw)
    if year_only:
        year = int(year_only.group(1))
        if 1900 <= year <= 2100:
            return f"{year:04d}"
        return None

    month_match = _MONTH_RE.search(lowered)
    year_match = _YEAR_RE.search(raw)
    if month_match and year_match:
        return _fmt(int(year_match.group(1)), _MONTHS[month_match.group(1).casefold()])
    if year_match and not month_match:
        year = int(year_match.group(1))
        if 1900 <= year <= 2100:
            return f"{year:04d}"
    return None


def career_date_or_empty(value: Any) -> str:
    return normalize_career_date(value) or ""


def apply_career_dates(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize known date keys in a dict in place and return it."""
    for field in _DATE_FIELDS:
        if field in payload:
            payload[field] = normalize_career_date(payload.get(field))
    return payload
