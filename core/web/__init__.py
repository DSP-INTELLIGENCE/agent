"""Core web fetch and extract primitives."""

from .extractor import extract_html
from .fetcher import fetch_url
from .models import WebExtractResult, WebFetchResult, WebSearchResult
from .search import search_web

__all__ = [
    "WebExtractResult",
    "WebFetchResult",
    "WebSearchResult",
    "extract_html",
    "fetch_url",
    "search_web",
]
