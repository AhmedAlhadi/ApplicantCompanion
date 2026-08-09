"""Prompt-injection protection (§43).

External content (JD text, webpages, uploaded documents) is DATA, never
instructions. Two layers of defense:

1. Structural: untrusted content is always wrapped in clearly delimited tags
   and every prompt states the rule explicitly.
2. Sanitization: well-known injection phrases are neutralized in the copy of
   the content that is sent to the model (the original is preserved in the
   database untouched).
"""
from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"forget\s+(everything|all)\s+(you|that)",
    r"reveal\s+(your|the)\s+(system\s+)?prompt",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*",
    r"</?system>",
    r"\[\[.*?(instruction|command).*?\]\]",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def detect_injection(text: str) -> list[str]:
    """Return the list of matched injection patterns (for audit logging)."""
    hits = []
    for pattern, rx in zip(INJECTION_PATTERNS, _COMPILED):
        if rx.search(text):
            hits.append(pattern)
    return hits


def sanitize_untrusted(text: str) -> str:
    """Neutralize common injection phrases in content bound for an LLM."""
    sanitized = text
    for rx in _COMPILED:
        sanitized = rx.sub("[removed]", sanitized)
    return sanitized


def wrap_untrusted(text: str, tag: str = "untrusted_content") -> str:
    """Wrap untrusted content in delimiters referenced by prompt instructions."""
    return f"<{tag}>\n{sanitize_untrusted(text)}\n</{tag}>"
