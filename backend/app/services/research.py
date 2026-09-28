"""Research plumbing: pluggable web search + snippet building (§12-14, §44).

A SearchProvider interface keeps web search swappable. The default provider
uses DuckDuckGo's public HTML endpoint (no API key). Every fetch goes through
the SSRF-protected, caching ResearchFetcher. When research is disabled or the
network is unreachable, the pipeline continues with 'Research unavailable'
(§54).
"""
from __future__ import annotations

import logging
import re
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy.orm import Session

from ..agents.research import ResearchFetcher, classify_source
from ..config import get_settings
from ..security.ssrf import SSRFError, validate_url

logger = logging.getLogger(__name__)

_RESULT_RE = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_DDG_REDIRECT_RE = re.compile(r"uddg=([^&]+)")


class SearchProvider:
    def search(self, query: str, max_results: int = 5) -> list[dict]:  # pragma: no cover
        raise NotImplementedError


class DuckDuckGoSearchProvider(SearchProvider):
    URLS = (
        "https://html.duckduckgo.com/html/",
        "https://duckduckgo.com/html/",
    )

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        last_error: Exception | None = None
        for url in self.URLS:
            try:
                resp = httpx.post(
                    url,
                    data={"q": query},
                    timeout=get_settings().research_timeout_seconds,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; Serah/1.0)"},
                    follow_redirects=True,
                )
                resp.raise_for_status()
                last_error = None
                html = resp.text
                break
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                continue
        else:
            logger.warning("Search failed for %r: %s", query, last_error)
            return []
        results = []
        for m in _RESULT_RE.finditer(html):
            href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
            redirect = _DDG_REDIRECT_RE.search(href)
            if redirect:
                href = unquote(redirect.group(1))
            results.append({"url": href, "title": title.strip()})
            if len(results) >= max_results:
                break
        return results


def get_search_provider() -> SearchProvider:
    return DuckDuckGoSearchProvider()


def gather_snippets(
    db: Session,
    queries: list[str],
    *,
    extra_urls: list[str] | None = None,
    max_pages: int | None = None,
) -> list[dict]:
    """Search + fetch + cache; returns snippets for the research agents."""
    settings = get_settings()
    if not settings.research_enabled:
        return []
    max_pages = max_pages or settings.research_max_pages
    fetcher = ResearchFetcher(db)
    search = get_search_provider()

    urls: list[str] = list(extra_urls or [])
    for query in queries:
        for hit in search.search(query, max_results=3):
            urls.append(hit["url"])

    snippets: list[dict] = []
    seen: set[str] = set()
    for url in urls:
        if len(snippets) >= max_pages:
            break
        if url in seen:
            continue
        seen.add(url)
        try:
            validate_url(url, resolve_dns=settings.app_env == "production")
        except SSRFError:
            continue
        source = fetcher.fetch(url)
        if source is None or not source.content_excerpt:
            continue
        source_type, credibility = classify_source(url)
        snippets.append(
            {
                "url": source.url,
                "title": source.title,
                "text": source.content_excerpt,
                "source_type": source.source_type or source_type,
                "credibility": source.credibility_score or credibility,
                "published_at": source.published_at,
            }
        )
    return snippets


def extract_urls(text: str) -> list[str]:
    """URLs explicitly present in user-provided text (e.g. the JD)."""
    found = re.findall(r"https?://[^\s)\]>'\"]+", text or "")
    clean = []
    for url in found:
        host = urlparse(url).hostname or ""
        if host:
            clean.append(url.rstrip(".,;"))
    return clean[:5]
