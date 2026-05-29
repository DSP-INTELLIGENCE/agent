"""HTML extraction primitives for the core web engine."""
from __future__ import annotations

from core.scrape.html import scrape_html
from core.scrape.normalize import normalize_text
from .models import WebExtractResult


def extract_html(html: str, url: str | None = None) -> WebExtractResult:
    scraped = scrape_html(html, url=url)
    metadata = {"title": scraped.title} if scraped.title else {}
    return WebExtractResult(
        url=scraped.url or url,
        title=normalize_text(scraped.title),
        text=normalize_text(scraped.text),
        source=scraped.source,
        links=scraped.links,
        metadata=metadata,
    )
