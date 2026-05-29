"""Deterministic text normalization helpers for scraping."""
from __future__ import annotations


DEFAULT_TRUNCATE_LIMIT = 4000
TRUNCATED_SUFFIX = "\n[TRUNCATED]"


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").split())


def truncate_text(text: str, limit: int = DEFAULT_TRUNCATE_LIMIT) -> str:
    normalized = normalize_text(text)
    try:
        bounded_limit = int(limit)
    except Exception:
        bounded_limit = DEFAULT_TRUNCATE_LIMIT
    if bounded_limit < 0:
        bounded_limit = 0
    if len(normalized) <= bounded_limit:
        return normalized
    if bounded_limit <= len(TRUNCATED_SUFFIX):
        return TRUNCATED_SUFFIX[:bounded_limit]
    content_limit = bounded_limit - len(TRUNCATED_SUFFIX)
    return normalized[:content_limit].rstrip() + TRUNCATED_SUFFIX
