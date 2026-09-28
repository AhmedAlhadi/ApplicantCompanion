"""Map provider/internal exceptions to short, end-user-safe messages."""
from __future__ import annotations

import re
from typing import Any

# Patterns are matched against the lowercased exception text.
_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"maximum context length|context.?length|context window|too many tokens|requested about \d+ tokens"),
        "This job has too much detail to analyze in one pass. Try a shorter job description, or remove unused career records and try again.",
    ),
    (
        re.compile(r"rate.?limit|429|too many requests"),
        "The AI service is busy right now. Please wait a moment and try again.",
    ),
    (
        re.compile(r"timeout|timed out|deadline exceeded"),
        "The analysis took too long and was stopped. Please try again.",
    ),
    (
        re.compile(r"401|403|unauthorized|invalid.?api.?key|authentication"),
        "The AI service could not be reached. Please try again later or contact support.",
    ),
    (
        re.compile(r"502|503|504|bad gateway|service unavailable|overloaded"),
        "The AI service is temporarily unavailable. Please try again shortly.",
    ),
    (
        re.compile(r"no requirements extracted"),
        "We could not find clear requirements in this job description. Try pasting a fuller JD.",
    ),
    (
        re.compile(r"jd parsing failed|job.?analysis"),
        "We could not analyze this job description. Check the text and try again.",
    ),
    (
        re.compile(r"matching failed|candidate_matching"),
        "We could not match your profile to this job. Please try again.",
    ),
    (
        re.compile(r"network|connection|dns|unreachable"),
        "A network problem interrupted the analysis. Please try again.",
    ),
]


_DEFAULT = "Something went wrong while processing this request. Please try again."


def public_error(exc: Any, *, fallback: str | None = None) -> str:
    """Return a user-facing message; never echo raw provider payloads."""
    text = str(exc or "")
    lowered = text.lower()
    for pattern, message in _RULES:
        if pattern.search(lowered):
            return message
    return fallback or _DEFAULT
