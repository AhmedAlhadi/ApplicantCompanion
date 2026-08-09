"""Versioned prompt registry (§37).

Prompts live as versioned files under backend/prompts/<name>/<version>.{system,user}.txt
and are loaded through this module — never scattered through application code.

File format:
    system file: YAML-like header lines "key: value" until a line with only
    "---", then the free text of the system prompt.
    user file:   a template rendered with str.format(**context).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_HEADER_RE = re.compile(r"^([a-z_]+):\s*(.*)$")


@dataclass
class Prompt:
    name: str
    version: str
    purpose: str = ""
    role: str = ""
    input_schema: str = ""
    output_schema: str = ""
    constraints: list[str] = field(default_factory=list)
    system: str = ""
    user_template: str = ""

    def render_user(self, **context) -> str:
        class _SafeDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        return self.user_template.format_map(_SafeDict(**context)) if context else self.user_template


def _parse_system_file(text: str) -> tuple[dict[str, str], str]:
    meta: dict[str, str] = {}
    body_lines: list[str] = []
    in_header = True
    for line in text.splitlines():
        if in_header and line.strip() == "---":
            in_header = False
            continue
        if in_header:
            m = _HEADER_RE.match(line)
            if m:
                meta[m.group(1)] = m.group(2).strip()
                continue
        in_header = False
        body_lines.append(line)
    return meta, "\n".join(body_lines).strip()


def load_prompt(name: str, version: str | None = None) -> Prompt:
    """Load the latest (or a specific) version of a named prompt."""
    prompt_dir = PROMPTS_DIR / name
    if not prompt_dir.is_dir():
        raise FileNotFoundError(f"Prompt not found: {name}")
    if version is None:
        versions = sorted(
            (p.name for p in prompt_dir.iterdir() if p.is_dir() and p.name.startswith("v")),
            key=lambda v: int(v[1:]),
        )
        if not versions:
            raise FileNotFoundError(f"Prompt {name} has no versions")
        version = versions[-1]
    version_dir = prompt_dir / version
    system_text = (version_dir / "system.txt").read_text(encoding="utf-8")
    user_template = (version_dir / "user.txt").read_text(encoding="utf-8")
    meta, system = _parse_system_file(system_text)
    return Prompt(
        name=name,
        version=version,
        purpose=meta.get("purpose", ""),
        role=meta.get("role", ""),
        input_schema=meta.get("input_schema", ""),
        output_schema=meta.get("output_schema", ""),
        constraints=[c.strip() for c in meta.get("constraints", "").split("|") if c.strip()],
        system=system,
        user_template=user_template,
    )


def list_prompts() -> list[dict]:
    out = []
    if not PROMPTS_DIR.is_dir():
        return out
    for name_dir in sorted(PROMPTS_DIR.iterdir()):
        if not name_dir.is_dir():
            continue
        versions = sorted(
            (p.name for p in name_dir.iterdir() if p.is_dir() and p.name.startswith("v")),
            key=lambda v: int(v[1:]),
        )
        out.append({"name": name_dir.name, "versions": versions})
    return out
