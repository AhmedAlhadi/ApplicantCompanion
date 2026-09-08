"""Extract and normalize application deadlines from job descriptions."""
from __future__ import annotations

import calendar
import re
from datetime import date

_MONTHS = {
    name.lower(): index
    for index, name in enumerate(calendar.month_name)
    if name
}
_MONTHS.update(
    {
        name.lower(): index
        for index, name in enumerate(calendar.month_abbr)
        if name
    }
)
_MONTH_ALT = {
    "sept": 9,
    "يناير": 1, "كانون الثاني": 1, "كانون2": 1,
    "فبراير": 2, "شباط": 2,
    "مارس": 3, "آذار": 3,
    "أبريل": 4, "ابريل": 4, "نيسان": 4,
    "مايو": 5, "أيار": 5, "ايار": 5,
    "يونيو": 6, "حزيران": 6,
    "يوليو": 7, "تموز": 7,
    "أغسطس": 8, "اغسطس": 8, "آب": 8,
    "سبتمبر": 9, "أيلول": 9, "ايلول": 9,
    "أكتوبر": 10, "اكتوبر": 10, "تشرين الأول": 10, "تشرين1": 10,
    "نوفمبر": 11, "تشرين الثاني": 11, "تشرين2": 11,
    "ديسمبر": 12, "كانون الأول": 12, "كانون1": 12,
}
_MONTHS.update(_MONTH_ALT)
_MONTH_NAMES = "|".join(sorted((re.escape(name) for name in _MONTHS), key=len, reverse=True))

_ISO_RE = re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")
_SLASH_RE = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d{2})\b")
_TEXT_DMY_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_NAMES})\.?,?\s+(20\d{{2}}|\d{{2}})\b",
    re.I,
)
_TEXT_MDY_RE = re.compile(
    rf"\b({_MONTH_NAMES})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d{{2}}|\d{{2}})\b",
    re.I,
)
_COMPACT_RE = re.compile(
    rf"\b(\d{{1,2}})-({_MONTH_NAMES})-(\d{{2}}|\d{{4}})\b",
    re.I,
)

_LABEL_RE = re.compile(
    r"(?im)^(?:application\s+)?(?:deadline|closing(?:\s+date)?|close\s+date|"
    r"last\s+date(?:\s+to\s+apply)?|due\s+date|apply\s+(?:by|before|until)|"
    r"آخر\s*موعد(?:\s*للتقديم)?|تاريخ\s*الإغلاق|آخر\s*تاريخ(?:\s*للتقديم)?|"
    r"موعد\s*(?:انتهاء\s*)?التقديم|يقدم\s*الطلب\s*قبل)"
    r"\s*[:\-]\s*(.+)$"
)
_INLINE_RES = [
    re.compile(
        r"(?i)(?:application\s+)?deadline(?:\s+for\s+applications?)?\s*[:\-]\s*(.{3,120})"
    ),
    re.compile(
        r"(?i)closing\s+date(?:\s+for\s+applications?)?\s*[:\-]\s*(.{3,120})"
    ),
    re.compile(r"(?i)apply\s+(?:by|before|until)\s*[:\-]?\s*(.{3,120})"),
    re.compile(
        r"(?i)applications?\s+(?:close|are\s+due|must be (?:received|submitted)|due)"
        r"\s+(?:on|by)?\s*(.{3,120})"
    ),
    re.compile(
        r"(?i)open\s*(?:&|and)\s*closing\s+dates?\s*[:\-]?\s*.{0,40}?\bto\s+(.{3,60})"
    ),
    re.compile(r"آخر\s*موعد(?:\s*للتقديم)?\s*[:\-]\s*(.{3,120})"),
    re.compile(r"تاريخ\s*الإغلاق\s*[:\-]\s*(.{3,120})"),
    re.compile(r"يقدم\s*الطلب\s*قبل\s*(.{3,120})"),
]
_NON_DATE_DEADLINES = re.compile(
    r"^(rolling|open until filled|until filled|asap|none|n/?a)$",
    re.I,
)


def _year(value: str) -> int:
    year = int(value)
    if year < 100:
        return 2000 + year
    return year


def _iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _iter_dates(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()

    def add(match_start: int, iso: str | None) -> None:
        if not iso:
            return
        key = (match_start, iso)
        if key in seen:
            return
        seen.add(key)
        found.append(key)

    for match in _ISO_RE.finditer(text):
        add(match.start(), _iso(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    for match in _SLASH_RE.finditer(text):
        first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if first > 12 and second <= 12:
            add(match.start(), _iso(year, second, first))
        elif second > 12 and first <= 12:
            add(match.start(), _iso(year, first, second))
        # Ambiguous numeric dates are skipped rather than guessed.
    for match in _TEXT_DMY_RE.finditer(text):
        month = _MONTHS[match.group(2).lower()]
        add(match.start(), _iso(_year(match.group(3)), month, int(match.group(1))))
    for match in _TEXT_MDY_RE.finditer(text):
        month = _MONTHS[match.group(1).lower()]
        add(match.start(), _iso(_year(match.group(3)), month, int(match.group(2))))
    for match in _COMPACT_RE.finditer(text):
        month = _MONTHS[match.group(2).lower()]
        add(match.start(), _iso(_year(match.group(3)), month, int(match.group(1))))
    found.sort(key=lambda item: item[0])
    return found


def normalize_application_deadline(value: str | None) -> str:
    """Return YYYY-MM-DD when a calendar date is present; otherwise a short token."""
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return ""
    dates = _iter_dates(raw)
    if dates:
        return dates[-1][1] if re.search(r"\bto\b", raw, re.I) and len(dates) > 1 else dates[0][1]
    compact = raw[:32].strip()
    if _NON_DATE_DEADLINES.match(compact):
        return compact.lower()
    return ""


def extract_application_deadline(jd_text: str | None) -> str:
    """Pull an application/closing date from JD text when one is stated."""
    jd = jd_text or ""
    for match in _LABEL_RE.finditer(jd):
        normalized = normalize_application_deadline(match.group(1))
        if normalized:
            return normalized
    for pattern in _INLINE_RES:
        match = pattern.search(jd)
        if not match:
            continue
        normalized = normalize_application_deadline(match.group(1))
        if normalized:
            return normalized
    return ""
