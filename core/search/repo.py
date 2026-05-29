"""Deterministic repo-local search helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .models import SearchResult


IGNORED_SEARCH_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "reports/patch-runs",
    "reports/web-cache",
}
DEFAULT_SEARCH_LIMIT = 50


class SearchRepoError(ValueError):
    pass


def search_repo_paths(query: str, repo_root: Path, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchResult]:
    normalized_query = _normalize_query(query)
    repo_root = Path(repo_root).expanduser().resolve(strict=False)
    if not repo_root.exists():
        raise SearchRepoError(f"repo root not found: {repo_root}")
    try:
        bounded_limit = int(limit)
    except Exception as exc:  # pragma: no cover - defensive
        raise SearchRepoError(f"invalid limit: {limit}") from exc
    if bounded_limit < 1:
        raise SearchRepoError("limit must be at least 1")
    bounded_limit = min(bounded_limit, DEFAULT_SEARCH_LIMIT)
    needle = normalized_query.lower()
    entries = list(_iter_repo_entries(repo_root, repo_root))

    filename_matches: list[SearchResult] = []
    path_matches: list[SearchResult] = []
    seen: set[str] = set()

    for index, entry in enumerate(entries):
        rel = _repo_relative_path(repo_root, entry)
        name_lower = entry.name.lower()

        if needle in name_lower:
            if rel not in seen:
                seen.add(rel)
                filename_matches.append(
                    SearchResult(
                        path=rel,
                        kind="filename",
                        score=max(1, 1000 - index),
                        snippet=entry.name,
                    )
                )

    for index, entry in enumerate(entries):
        rel = _repo_relative_path(repo_root, entry)
        rel_lower = rel.lower()
        name_lower = entry.name.lower()

        if rel in seen:
            continue
        if needle in rel_lower and needle not in name_lower:
            seen.add(rel)
            path_matches.append(
                SearchResult(
                    path=rel,
                    kind="path",
                    score=max(1, 500 - index),
                    snippet=rel,
                )
            )

    ordered = sorted(filename_matches, key=lambda item: (item.path.count("/"), item.path.lower(), item.path))
    ordered.extend(sorted(path_matches, key=lambda item: (item.path.count("/"), item.path.lower(), item.path)))
    return ordered[:bounded_limit]


def _normalize_query(query: str) -> str:
    text = " ".join(str(query or "").split())
    if not text:
        raise SearchRepoError("search_repo_paths requires a non-empty query")
    return text


def _iter_repo_entries(current: Path, repo_root: Path) -> Iterable[Path]:
    try:
        entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower(), p.name))
    except Exception:
        return

    for entry in entries:
        if _should_skip(entry, repo_root):
            continue
        yield entry
        if entry.is_dir():
            yield from _iter_repo_entries(entry, repo_root)


def _should_skip(path: Path, repo_root: Path) -> bool:
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        return True

    rel_text = str(rel)
    parts = path.parts
    if any(part in IGNORED_SEARCH_DIRS for part in parts):
        return True
    if any(rel_text == prefix or rel_text.startswith(prefix + "/") for prefix in IGNORED_SEARCH_DIRS):
        return True
    return False


def _repo_relative_path(repo_root: Path, path: Path) -> str:
    rel = path.relative_to(repo_root)
    return "." if not str(rel) else str(rel)
