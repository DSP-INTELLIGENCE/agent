"""Web search helpers for the core web engine."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable

from .models import WebSearchResult

DEFAULT_SEARCH_TIMEOUT_SECONDS = 20
DEFAULT_SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 10


class WebSearchError(ValueError):
    pass


def _load_ddgs_class():
    try:  # optional dependency
        from ddgs import DDGS as ddgs_class  # type: ignore
        return ddgs_class
    except Exception:
        repo_root = Path(__file__).resolve().parents[2]
        venv_site_packages = repo_root / ".venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
        if venv_site_packages.exists():
            venv_text = str(venv_site_packages)
            if venv_text not in sys.path:
                sys.path.insert(0, venv_text)
            try:
                from ddgs import DDGS as ddgs_class  # type: ignore
                return ddgs_class
            except Exception:
                return None
        return None


DDGS = _load_ddgs_class()


def search_web(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[WebSearchResult]:
    normalized_query = _normalize_query(query)
    bounded_limit = _normalize_limit(limit)
    client = _build_client(timeout_seconds=DEFAULT_SEARCH_TIMEOUT_SECONDS)

    try:
        raw_results = client.text(normalized_query, max_results=bounded_limit)
    except Exception as exc:  # pragma: no cover - provider failure path
        raise WebSearchError(f"search_web failed for {normalized_query}: {exc}") from exc

    results: list[WebSearchResult] = []
    seen_urls: set[str] = set()
    for item in raw_results:
        normalized = _normalize_result(item)
        if normalized is None:
            continue
        if normalized.url in seen_urls:
            continue
        seen_urls.add(normalized.url)
        results.append(normalized)
        if len(results) >= bounded_limit:
            break
    return results


def _build_client(*, timeout_seconds: int):
    if DDGS is None:
        raise WebSearchError("ddgs is unavailable")

    try:
        return DDGS(timeout=timeout_seconds)
    except TypeError:
        return DDGS()
    except Exception as exc:  # pragma: no cover - constructor failure path
        raise WebSearchError(f"unable to initialize ddgs: {exc}") from exc


def _normalize_query(query: str) -> str:
    text = " ".join(str(query or "").split())
    if not text:
        raise WebSearchError("search_web requires a non-empty query")
    return text


def _normalize_limit(limit: int) -> int:
    try:
        value = int(limit)
    except Exception as exc:  # pragma: no cover - defensive
        raise WebSearchError(f"invalid search limit: {limit}") from exc

    if value < 1:
        raise WebSearchError("search limit must be at least 1")
    return min(value, MAX_SEARCH_LIMIT)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _pick_field(item: Any, names: Iterable[str]) -> str:
    if isinstance(item, dict):
        for name in names:
            value = item.get(name)
            if value:
                text = _normalize_text(value)
                if text:
                    return text
        return ""

    for name in names:
        value = getattr(item, name, None)
        if value:
            text = _normalize_text(value)
            if text:
                return text
    return ""


def _normalize_result(item: Any) -> WebSearchResult | None:
    title = _pick_field(item, ("title", "name", "heading"))
    url = _pick_field(item, ("url", "href", "link", "uri"))
    snippet = _pick_field(item, ("snippet", "body", "description", "abstract", "text"))

    if not url:
        return None

    if not title:
        title = url

    return WebSearchResult(title=title, url=url, snippet=snippet, source="ddgs")
