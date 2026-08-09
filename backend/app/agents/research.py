"""Organization & hiring-team research agents (§12-14, §43-44).

Fetching is done by the ResearchFetcher (SSRF-protected, cached). The agents
only synthesize claims from the retrieved snippets — webpage content is always
treated as untrusted DATA (§43).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ResearchSource
from ..schemas.agents import HiringContextResult, OrganizationResearchResult
from ..security.injection import sanitize_untrusted
from ..security.ssrf import SSRFError, validate_url
from .base import BaseAgent

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)


def classify_source(url: str) -> tuple[str, float]:
    """Map a URL to the §12 source hierarchy -> (source_type, credibility)."""
    host = (urlparse(url).hostname or "").lower()
    if any(host.endswith(sfx) for sfx in (".gov", ".un.org", ".unicef.org", ".undp.org", ".who.int", ".worldbank.org")):
        return "institutional", 0.85
    if any(host.endswith(sfx) for sfx in (".edu", ".ac.uk")):
        return "institutional", 0.7
    if any(h in host for h in ("reuters.", "bbc.", "ft.com", "economist.", "bloomberg.")):
        return "news", 0.6
    return "other", 0.4


def html_to_text(html: str, limit: int = 4000) -> str:
    text = _SCRIPT_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


class ResearchFetcher:
    """SSRF-safe, cached fetcher for public pages (§42, §44)."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def fetch(self, url: str) -> ResearchSource | None:
        try:
            validate_url(url, resolve_dns=self.settings.app_env == "production")
        except SSRFError as exc:
            logger.warning("SSRF blocked: %s (%s)", url, exc)
            return None

        cached = (
            self.db.query(ResearchSource).filter(ResearchSource.url == url).first()
        )
        if cached:
            return cached

        try:
            resp = httpx.get(
                url,
                timeout=self.settings.research_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "ApplicantCompanion-Research/1.0"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Research fetch failed: %s (%s)", url, exc)
            return None

        text = html_to_text(resp.text)
        source_type, credibility = classify_source(url)
        source = ResearchSource(
            url=url,
            title=url,
            domain=urlparse(url).hostname or "",
            source_type=source_type,
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
            credibility_score=credibility,
            content_excerpt=sanitize_untrusted(text[:2000]),
        )
        self.db.add(source)
        self.db.flush()
        return source


class OrganizationResearchAgent(BaseAgent):
    name = "organization_research"
    task = "research"
    prompt_name = "organization_research"
    output_model = OrganizationResearchResult

    def build_user_message(self, *, organization: str, job_title: str = "", snippets: list[dict] | None = None, **_) -> str:
        payload = {
            "organization": organization,
            "job_title": job_title,
            "snippets": snippets or [],
        }
        return self.prompt.render_user(
            organization=organization,
            job_title=job_title,
            payload_json=json.dumps(payload),
        )


class HiringTeamResearchAgent(BaseAgent):
    name = "hiring_team_research"
    task = "research"
    prompt_name = "hiring_manager_research"
    output_model = HiringContextResult

    def build_user_message(self, *, organization: str, department: str = "", job_title: str = "", snippets: list[dict] | None = None, **_) -> str:
        payload = {
            "organization": organization,
            "department": department,
            "job_title": job_title,
            "snippets": snippets or [],
        }
        return self.prompt.render_user(
            organization=organization,
            department=department,
            job_title=job_title,
            payload_json=json.dumps(payload),
        )
