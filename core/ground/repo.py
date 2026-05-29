"""Deterministic repo-grounding helpers."""
from __future__ import annotations

from pathlib import Path

from core.scrape.normalize import normalize_text

from .models import GroundedDocument, GroundedExcerpt


DEFAULT_EXCERPT_WINDOW = 40
DEFAULT_MAX_EXCERPTS = 3
DEFAULT_EXCERPT_LIMIT = 4000
_CACHE_ARTIFACT_MARKER = "reports/web-cache"


class GroundingError(ValueError):
    pass


def build_excerpt(
    text: str,
    *,
    source_path: str,
    start_line: int = 1,
    window: int = DEFAULT_EXCERPT_WINDOW,
    limit: int = DEFAULT_EXCERPT_LIMIT,
    source_kind: str = "repo_file",
) -> GroundedExcerpt:
    lines = str(text or "").splitlines()
    start_line = max(1, int(start_line))
    window = max(1, int(window))
    limit = max(0, int(limit))

    if not lines or start_line > len(lines):
        return GroundedExcerpt(
            source_path=_normalize_source_path(source_path),
            start_line=start_line,
            end_line=start_line,
            text="",
            source_kind=source_kind,
        )

    start_index = start_line - 1
    end_index = min(len(lines), start_index + window)
    excerpt_lines = [_format_excerpt_line(line_no, lines[line_no - 1]) for line_no in range(start_line, end_index + 1)]
    excerpt_text = _bound_text("\n".join(excerpt_lines), limit=limit)

    return GroundedExcerpt(
        source_path=_normalize_source_path(source_path),
        start_line=start_line,
        end_line=end_index,
        text=excerpt_text,
        source_kind=source_kind,
    )


def ground_repo_file(
    path: str | Path,
    *,
    window: int = DEFAULT_EXCERPT_WINDOW,
    max_excerpts: int = DEFAULT_MAX_EXCERPTS,
    limit: int = DEFAULT_EXCERPT_LIMIT,
) -> GroundedDocument:
    source_path = _normalize_source_path(path)
    file_path = Path(path).expanduser()
    if not file_path.exists():
        raise GroundingError(f"file not found: {source_path}")
    if not file_path.is_file():
        raise GroundingError(f"not a file: {source_path}")

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise GroundingError(f"unable to read file: {source_path}") from exc

    lines = text.splitlines()
    source_kind = "cache_artifact" if _is_cache_artifact(source_path) else "repo_file"
    title = _derive_title(lines, file_path.name)

    excerpts: list[GroundedExcerpt] = []
    window = max(1, int(window))
    max_excerpts = max(1, int(max_excerpts))
    for excerpt_index, start_line in enumerate(range(1, len(lines) + 1, window), start=1):
        if excerpt_index > max_excerpts:
            break
        excerpts.append(
            build_excerpt(
                text,
                source_path=source_path,
                start_line=start_line,
                window=window,
                limit=limit,
                source_kind=source_kind,
            )
        )

    return GroundedDocument(
        source_path=source_path,
        title=title,
        excerpts=tuple(excerpts),
        source_kind=source_kind,
    )


def _normalize_source_path(path: str | Path) -> str:
    return Path(path).expanduser().as_posix()


def _is_cache_artifact(source_path: str) -> bool:
    return _CACHE_ARTIFACT_MARKER in source_path.replace("\\", "/")


def _derive_title(lines: list[str], fallback: str) -> str:
    for raw_line in lines:
        cleaned = normalize_text(raw_line)
        if not cleaned:
            continue
        if cleaned.startswith("#"):
            heading = cleaned.lstrip("#").strip()
            if heading:
                return heading
        break
    return fallback


def _format_excerpt_line(line_no: int, raw_line: str) -> str:
    cleaned = normalize_text(raw_line)
    return f"{line_no}: {cleaned}" if cleaned else f"{line_no}:"


def _bound_text(text: str, *, limit: int) -> str:
    value = str(text or "")
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    suffix = "\n[TRUNCATED]"
    if limit <= len(suffix):
        return suffix[:limit]
    return value[: limit - len(suffix)].rstrip() + suffix
