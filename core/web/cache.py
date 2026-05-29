"""Deterministic cache/report helpers for the core web engine."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from .models import WebSearchResult


DEFAULT_WEB_CACHE_ROOT = Path("reports/web-cache")
CACHE_TIMESTAMP = "1970-01-01T00:00:00Z"
MAX_CACHE_TEXT_CHARS = 100_000


class WebCacheError(ValueError):
    pass


@dataclass(frozen=True)
class WebCacheWriteResult:
    cache_id: str
    cache_dir: Path
    metadata_path: Path
    report_path: Path
    artifact_paths: tuple[Path, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cache_id": self.cache_id,
            "cache_dir": str(self.cache_dir),
            "metadata_path": str(self.metadata_path),
            "report_path": str(self.report_path),
            "artifact_paths": [str(path) for path in self.artifact_paths],
            "metadata": dict(self.metadata),
        }


def build_cache_id(value: str) -> str:
    normalized = _normalize_text(value)
    digest = hashlib.sha256(f"web-cache:v1:{normalized}".encode("utf-8")).hexdigest()
    return digest[:16]


def write_fetch_cache(
    *,
    cache_root: Path | str = DEFAULT_WEB_CACHE_ROOT,
    url: str,
    final_url: str,
    status_code: int,
    content: bytes,
    content_type: str = "",
    title: str = "",
) -> WebCacheWriteResult:
    cache_id = build_cache_id(final_url or url)
    cache_dir = _build_cache_dir(cache_root, "fetch", cache_id)
    metadata_path = cache_dir / "metadata.json"
    report_path = cache_dir / "report.txt"
    body_path = cache_dir / "body.bin"
    title_path = cache_dir / "extracted-title.txt"

    title_text = _normalize_text(title)
    metadata = {
        "cache_id": cache_id,
        "kind": "fetch",
        "timestamp": CACHE_TIMESTAMP,
        "url": _normalize_text(url),
        "normalized_url": _normalize_text(final_url or url),
        "final_url": _normalize_text(final_url or url),
        "status_code": int(status_code),
        "content_type": _normalize_text(content_type),
        "content_bytes": len(content),
        "content_sha256": _sha256_bytes(content),
        "title": title_text,
    }

    _write_json(metadata_path, metadata)
    _write_bytes(body_path, content)
    artifact_paths = [metadata_path, body_path]
    if title_text:
        _write_text(title_path, title_text + "\n")
        artifact_paths.append(title_path)
    _write_text(report_path, _render_report("fetch", metadata, artifact_paths))
    artifact_paths.append(report_path)

    return WebCacheWriteResult(
        cache_id=cache_id,
        cache_dir=cache_dir,
        metadata_path=metadata_path,
        report_path=report_path,
        artifact_paths=tuple(artifact_paths),
        metadata=metadata,
    )


def write_extract_cache(
    *,
    cache_root: Path | str = DEFAULT_WEB_CACHE_ROOT,
    url: str,
    normalized_url: str,
    extracted_text: str,
    source: str,
    content_type: str = "",
    title: str = "",
) -> WebCacheWriteResult:
    cache_id = build_cache_id(normalized_url or url)
    cache_dir = _build_cache_dir(cache_root, "extract", cache_id)
    metadata_path = cache_dir / "metadata.json"
    report_path = cache_dir / "report.txt"
    extracted_path = cache_dir / "extracted.txt"
    normalized_url_path = cache_dir / "normalized-url.txt"
    source_path = cache_dir / "source.txt"
    title_path = cache_dir / "title.txt"

    bounded_text, truncated = _bound_text(extracted_text)
    text_bytes = bounded_text.encode("utf-8")
    metadata = {
        "cache_id": cache_id,
        "kind": "extract",
        "timestamp": CACHE_TIMESTAMP,
        "url": _normalize_text(url),
        "normalized_url": _normalize_text(normalized_url or url),
        "source": _normalize_text(source),
        "content_type": _normalize_text(content_type),
        "title": _normalize_text(title),
        "text_bytes": len(text_bytes),
        "text_sha256": _sha256_bytes(text_bytes),
        "text_truncated": truncated,
    }

    _write_json(metadata_path, metadata)
    _write_text(extracted_path, bounded_text)
    _write_text(normalized_url_path, metadata["normalized_url"] + "\n")
    _write_text(source_path, metadata["source"] + "\n")
    artifact_paths = [metadata_path, extracted_path, normalized_url_path, source_path]
    if metadata["title"]:
        _write_text(title_path, metadata["title"] + "\n")
        artifact_paths.append(title_path)
    _write_text(report_path, _render_report("extract", metadata, artifact_paths))
    artifact_paths.append(report_path)

    return WebCacheWriteResult(
        cache_id=cache_id,
        cache_dir=cache_dir,
        metadata_path=metadata_path,
        report_path=report_path,
        artifact_paths=tuple(artifact_paths),
        metadata=metadata,
    )


def write_search_cache(
    *,
    cache_root: Path | str = DEFAULT_WEB_CACHE_ROOT,
    query: str,
    results: Sequence[WebSearchResult] | Iterable[WebSearchResult],
) -> WebCacheWriteResult:
    normalized_query = _normalize_text(query)
    cache_id = build_cache_id(normalized_query)
    cache_dir = _build_cache_dir(cache_root, "search", cache_id)
    metadata_path = cache_dir / "metadata.json"
    report_path = cache_dir / "report.txt"
    snapshot_path = cache_dir / "snapshot.json"

    result_list = [result.to_dict() for result in list(results)]
    snapshot = {
        "cache_id": cache_id,
        "kind": "search",
        "query": normalized_query,
        "timestamp": CACHE_TIMESTAMP,
        "result_count": len(result_list),
        "results": result_list,
    }
    snapshot_bytes = json.dumps(snapshot, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    metadata = {
        "cache_id": cache_id,
        "kind": "search",
        "timestamp": CACHE_TIMESTAMP,
        "query": normalized_query,
        "result_count": len(result_list),
        "snapshot_bytes": len(snapshot_bytes),
        "snapshot_sha256": _sha256_bytes(snapshot_bytes),
    }

    _write_json(metadata_path, metadata)
    _write_text(snapshot_path, snapshot_bytes.decode("utf-8"))
    _write_text(report_path, _render_report("search", metadata, [metadata_path, snapshot_path]))

    return WebCacheWriteResult(
        cache_id=cache_id,
        cache_dir=cache_dir,
        metadata_path=metadata_path,
        report_path=report_path,
        artifact_paths=(metadata_path, snapshot_path, report_path),
        metadata=metadata,
    )


def _build_cache_dir(cache_root: Path | str, kind: str, cache_id: str) -> Path:
    root = Path(cache_root).expanduser()
    cache_dir = root / kind / cache_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _bound_text(text: str, *, limit: int = MAX_CACHE_TEXT_CHARS) -> tuple[str, bool]:
    value = str(text or "")
    if len(value) <= limit:
        return value, False
    return value[:limit].rstrip() + "\n[TRUNCATED]", True


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(str(text), encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(bytes(data))


def _render_report(kind: str, metadata: dict[str, Any], artifact_paths: Sequence[Path]) -> str:
    lines = [
        f"cache kind: {kind}",
        f"cache id: {metadata.get('cache_id', '')}",
        f"timestamp: {metadata.get('timestamp', '')}",
    ]
    if kind == "fetch":
        lines.extend(
            [
                f"url: {metadata.get('url', '')}",
                f"normalized_url: {metadata.get('normalized_url', '')}",
                f"status_code: {metadata.get('status_code', '')}",
                f"content_type: {metadata.get('content_type', '') or 'unknown'}",
                f"content_bytes: {metadata.get('content_bytes', '')}",
                f"title: {metadata.get('title', '') or 'unknown'}",
            ]
        )
    elif kind == "extract":
        lines.extend(
            [
                f"url: {metadata.get('url', '')}",
                f"normalized_url: {metadata.get('normalized_url', '')}",
                f"source: {metadata.get('source', '')}",
                f"content_type: {metadata.get('content_type', '') or 'unknown'}",
                f"text_bytes: {metadata.get('text_bytes', '')}",
                f"text_truncated: {metadata.get('text_truncated', False)}",
            ]
        )
    elif kind == "search":
        lines.extend(
            [
                f"query: {metadata.get('query', '')}",
                f"result_count: {metadata.get('result_count', '')}",
                f"snapshot_bytes: {metadata.get('snapshot_bytes', '')}",
            ]
        )

    lines.append("artifacts:")
    for path in artifact_paths:
        lines.append(f"  - {path}")
    return "\n".join(lines) + "\n"
