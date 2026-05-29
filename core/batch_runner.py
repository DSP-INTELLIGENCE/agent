"""Small non-interactive batch runner for agent-cli.py.

This module is intentionally narrow for the first CLI branch.

Boundaries:
- no /paste behavior
- no interactive prompt loop
- no shell=True
- no apply/rollback/sudo enablement
- no background jobs
- routes only known safe slash/tool surfaces
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from urllib import request as urlrequest
from typing import Callable, Iterable, List, Sequence

from core.search.repo import SearchRepoError, search_repo_paths
from core.ground.repo import GroundingError, ground_repo_file
from core.ground.report import GroundReportError, write_ground_report
from core.ground.store import GroundReportLookupError, list_ground_reports, load_ground_report
from core import execution_dispatch as _execution_dispatch
from core.web.cache import WebCacheError, write_extract_cache, write_fetch_cache, write_search_cache
from core.web.search import WebSearchError, search_web


ROOT = Path(__file__).resolve().parents[1]
WEB_CACHE_ROOT = ROOT / "reports" / "web-cache"
GROUND_REPORT_ROOT = ROOT / "reports" / "ground"
GROUND_OUTPUT_LIMIT = 12000
GROUND_REPORT_LIST_LIMIT = 20
_EXECUTION_DISPATCH_REGISTRY = _execution_dispatch.build_default_dispatch_registry()
RAW_PROMPT_ROOTS: tuple[str, ...] = (
    "/prompt",
)
QUESTION_ROOTS: tuple[str, ...] = ()
PROMPT_LANE_ROOTS: tuple[str, ...] = (
    "/prompt",
)
ROUTE_ROOTS: tuple[str, ...] = ()


@dataclass(frozen=True)
class BatchResult:
    input: str
    ok: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""
    mode: str = "batch_command"

    def to_dict(self) -> dict:
        return {
            "input": self.input,
            "ok": self.ok,
            "returncode": self.returncode,
            "mode": self.mode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class BatchHandler:
    key: str
    roots: tuple[str, ...]
    dispatch: Callable[[str, Sequence[str], str], BatchResult | None]


class RepoPathError(ValueError):
    pass


_IGNORED_TREE_NAMES = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}


def _resolve_repo_path(raw_path: str) -> Path:
    text = str(raw_path or "").strip()
    if not text:
        return ROOT

    candidate = Path(text).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
    else:
        resolved = (ROOT / candidate).resolve(strict=False)

    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise RepoPathError(f"path is outside repository: {raw_path}") from exc

    return resolved


def _repo_relative_path(path: Path) -> str:
    rel = path.relative_to(ROOT)
    return "." if not str(rel) else str(rel)


def _format_listing_entry(path: Path) -> str:
    rel = _repo_relative_path(path)
    if path.is_dir():
        return "." if rel == "." else rel.rstrip("/") + "/"
    return rel


def _should_skip_repo_path(path: Path) -> bool:
    rel = _repo_relative_path(path)
    parts = path.parts

    if any(part in _IGNORED_TREE_NAMES for part in parts):
        return True

    return False


def _walk_repo_paths(root: Path, *, max_depth: int | None = None, include_root: bool = False) -> list[Path]:
    entries: list[Path] = []

    if include_root:
        entries.append(root)

    def _recurse(current: Path, depth: int) -> None:
        if max_depth is not None and depth >= max_depth:
            return

        children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower(), p.name))
        for child in children:
            if _should_skip_repo_path(child):
                continue
            entries.append(child)
            if child.is_dir():
                _recurse(child, depth + 1)

    _recurse(root, 0)
    return entries


def _render_ls_output(path: Path) -> str:
    if path.is_dir():
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower(), p.name))
        lines = [_format_listing_entry(entry) for entry in entries]
    else:
        lines = [_format_listing_entry(path)]

    return "\n".join(lines) + ("\n" if lines else "")


def _run_read(args: Sequence[str], original: str) -> BatchResult:
    if len(args) != 1:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /read <path>",
            mode="repo_read",
        )

    try:
        target = _resolve_repo_path(args[0])
    except RepoPathError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path error: {exc}",
            mode="repo_read",
        )

    if not target.exists():
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path not found: {args[0]}",
            mode="repo_read",
        )

    if not target.is_file():
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path is not a file: {args[0]}",
            mode="repo_read",
        )

    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=target.read_text(encoding="utf-8"),
        mode="repo_read",
    )


def _run_ls(args: Sequence[str], original: str) -> BatchResult:
    if len(args) > 1:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /ls [path]",
            mode="repo_ls",
        )

    target_arg = args[0] if args else "."
    try:
        target = _resolve_repo_path(target_arg)
    except RepoPathError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path error: {exc}",
            mode="repo_ls",
        )

    if not target.exists():
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path not found: {target_arg}",
            mode="repo_ls",
        )

    if not target.is_dir() and not target.is_file():
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path is not listable: {target_arg}",
            mode="repo_ls",
        )

    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=_render_ls_output(target),
        mode="repo_ls",
    )


def _render_tree_output(path: Path) -> str:
    if path.is_file():
        return _format_listing_entry(path) + "\n"

    lines: list[str] = []
    if path != ROOT:
        lines.append(_format_listing_entry(path))
    for entry in _walk_repo_paths(path, max_depth=3, include_root=False):
        if entry == path:
            continue
        lines.append(_format_listing_entry(entry))
    return "\n".join(lines) + ("\n" if lines else "")


def _run_tree(args: Sequence[str], original: str) -> BatchResult:
    if len(args) > 1:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /tree [path]",
            mode="repo_tree",
        )

    target_arg = args[0] if args else "."
    try:
        target = _resolve_repo_path(target_arg)
    except RepoPathError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path error: {exc}",
            mode="repo_tree",
        )

    if not target.exists():
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path not found: {target_arg}",
            mode="repo_tree",
        )

    if not target.is_dir() and not target.is_file():
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path is not treeable: {target_arg}",
            mode="repo_tree",
        )

    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=_render_tree_output(target),
        mode="repo_tree",
    )


def _render_repo_search_output(results) -> str:
    if not results:
        return "no matches\n"
    return "\n".join(result.path for result in results) + "\n"


def _render_grounded_document(document, *, display_path: str | None = None) -> str:
    lines = [
        f"source_path: {display_path or document.source_path}",
        f"title: {document.title}",
        f"source_kind: {document.source_kind}",
    ]

    if not document.excerpts:
        lines.append("excerpts: none")
        return "\n".join(lines) + "\n"

    for index, excerpt in enumerate(document.excerpts, start=1):
        lines.append(f"excerpt {index}:")
        lines.append(f"  lines: {excerpt.start_line}-{excerpt.end_line}")
        lines.append(f"  source_kind: {excerpt.source_kind}")
        lines.append("  text:")
        lines.extend(_indent_block(excerpt.text or "", prefix="    ").splitlines())

    return "\n".join(lines) + "\n"


def _render_grounded_collection(documents: Sequence[tuple[object, str]]) -> str:
    lines = [
        "GROUND collection:",
        f"source_count: {len(documents)}",
    ]

    if not documents:
        lines.append("sources: none")
        return "\n".join(lines) + "\n"

    for index, (document, display_path) in enumerate(documents, start=1):
        lines.append(f"source {index}:")
        lines.append(f"  source_path: {display_path}")
        lines.append(f"  title: {document.title}")
        lines.append(f"  source_kind: {document.source_kind}")

        if not document.excerpts:
            lines.append("  excerpts: none")
            continue

        for excerpt_index, excerpt in enumerate(document.excerpts, start=1):
            lines.append(f"  excerpt {excerpt_index}:")
            lines.append(f"    lines: {excerpt.start_line}-{excerpt.end_line}")
            lines.append(f"    source_kind: {excerpt.source_kind}")
            lines.append("    text:")
            lines.extend(_indent_block(excerpt.text or "", prefix="      ").splitlines())

    return "\n".join(lines) + "\n"


def _render_grounded_search(query: str, results: Sequence[tuple[object, str]]) -> str:
    lines = [
        "GROUND search:",
        f"query: {query}",
        f"result_count: {len(results)}",
        f"source_count: {len(results)}",
    ]

    if not results:
        lines.append("no matches")
        return "\n".join(lines) + "\n"

    for index, (document, display_path) in enumerate(results, start=1):
        lines.append(f"source {index}:")
        lines.append(f"  source_path: {display_path}")
        lines.append(f"  title: {document.title}")
        lines.append(f"  source_kind: {document.source_kind}")

        if not document.excerpts:
            lines.append("  excerpts: none")
            continue

        for excerpt_index, excerpt in enumerate(document.excerpts, start=1):
            lines.append(f"  excerpt {excerpt_index}:")
            lines.append(f"    lines: {excerpt.start_line}-{excerpt.end_line}")
            lines.append(f"    source_kind: {excerpt.source_kind}")
            lines.append("    text:")
            lines.extend(_indent_block(excerpt.text or "", prefix="      ").splitlines())

    return "\n".join(lines) + "\n"


def _ground_report_summary_lines(write_result) -> list[str]:
    return [
        f"  report_id: {write_result.report_id}",
        f"  report_path: {write_result.report_path}",
        f"  metadata_path: {write_result.metadata_path}",
        "  ground report written",
    ]


def _clip_ground_output(text: str) -> str:
    return _clip_text(text, limit=GROUND_OUTPUT_LIMIT)


def _append_ground_summary(output: str, summary_lines: Sequence[str]) -> str:
    summary = "\n".join(summary_lines).rstrip("\n")
    if not summary:
        return _clip_ground_output(output)

    suffix = "\n\n" + summary + "\n"
    available = GROUND_OUTPUT_LIMIT - len(suffix)
    base = str(output or "")
    if available <= 0:
        return summary + "\n"
    if len(base) > available:
        base = base[:available].rstrip("\n")
    combined = base.rstrip("\n") + suffix
    return combined


def _display_ground_path(path: Path) -> str:
    try:
        return _repo_relative_path(path)
    except ValueError:
        return path.as_posix()


def _render_ground_report_list(summaries) -> str:
    lines = [
        "GROUND reports:",
        f"report_count: {len(summaries)}",
    ]

    if not summaries:
        lines.append("reports: none")
        return "\n".join(lines) + "\n"

    for index, summary in enumerate(summaries, start=1):
        lines.append(f"report {index}:")
        lines.append(f"  report_id: {summary.report_id}")
        lines.append(f"  kind: {summary.kind}")
        lines.append(f"  report_path: {_display_ground_path(summary.report_path)}")
        lines.append(f"  metadata_path: {_display_ground_path(summary.metadata_path)}")

    return "\n".join(lines) + "\n"


def _render_ground_report(record) -> str:
    lines = [
        "GROUND report:",
        f"report_id: {record.report_id}",
        f"kind: {record.kind}",
        f"command: {record.command}",
        f"sha256: {record.report_sha256}",
        f"report_path: {_display_ground_path(record.report_path)}",
        f"metadata_path: {_display_ground_path(record.metadata_path)}",
        "report_body:",
    ]

    body = _clip_text(record.report_text.rstrip("\n"), limit=GROUND_OUTPUT_LIMIT)
    lines.extend(_indent_block(body if body else "(empty)", prefix="  ").splitlines())
    return "\n".join(lines) + "\n"


def _run_find(args: Sequence[str], original: str) -> BatchResult:
    query = " ".join(args).strip()
    if not query:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /find <query>",
            mode="repo_find",
        )

    try:
        results = search_repo_paths(query, ROOT, limit=50)
    except SearchRepoError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo search error: {exc}",
            mode="repo_find",
        )

    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=_render_repo_search_output(results),
        mode="repo_find",
    )


def _run_ground_repo(args: Sequence[str], original: str) -> BatchResult:
    values = list(args)
    save_requested = False
    if "--save" in values[:-1]:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /ground repo <path> [--save]",
            mode="ground_repo",
        )
    if values and values[-1] == "--save":
        save_requested = True
        values = values[:-1]

    if len(values) != 1:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /ground repo <path> [--save]",
            mode="ground_repo",
        )

    target_arg = values[0]
    try:
        target = _resolve_repo_path(target_arg)
    except RepoPathError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path error: {exc}",
            mode="ground_repo",
        )

    if not target.exists():
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path not found: {target_arg}",
            mode="ground_repo",
        )

    if not target.is_file():
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo path is not a file: {target_arg}",
            mode="ground_repo",
        )

    try:
        document = ground_repo_file(target)
    except GroundingError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"grounding error: {exc}",
            mode="ground_repo",
        )

    display_path = _repo_relative_path(target)
    base_output = _clip_ground_output(_render_grounded_document(document, display_path=display_path))
    if not save_requested:
        return BatchResult(
            input=original,
            ok=True,
            returncode=0,
            stdout=base_output,
            mode="ground_repo",
        )

    try:
        write_result = write_ground_report(
            kind="repo",
            command=original,
            report_text=base_output,
            metadata={
                "source_path": display_path,
            },
            report_root=GROUND_REPORT_ROOT,
        )
    except GroundReportError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"ground report error: {exc}",
            mode="ground_repo",
        )

    stdout = _append_ground_summary(base_output, _ground_report_summary_lines(write_result))
    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=stdout,
        mode="ground_repo",
    )


def _run_ground_reports(args: Sequence[str], original: str) -> BatchResult:
    if args:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /ground reports",
            mode="ground_reports",
        )

    try:
        summaries = list_ground_reports(GROUND_REPORT_ROOT, limit=GROUND_REPORT_LIST_LIMIT)
    except GroundReportLookupError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"ground report lookup error: {exc}",
            mode="ground_reports",
        )

    stdout = _clip_ground_output(_render_ground_report_list(summaries))
    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=stdout,
        mode="ground_reports",
    )


def _run_ground_show(args: Sequence[str], original: str) -> BatchResult:
    if len(args) != 1 or not str(args[0] or "").strip():
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /ground show <report-id>",
            mode="ground_show",
        )

    report_id = str(args[0]).strip()
    try:
        record = load_ground_report(GROUND_REPORT_ROOT, report_id)
    except GroundReportLookupError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"ground report lookup error: {exc}",
            mode="ground_show",
        )

    stdout = _clip_ground_output(_render_ground_report(record))
    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=stdout,
        mode="ground_show",
    )


def _run_ground_collect(args: Sequence[str], original: str) -> BatchResult:
    values = list(args)
    save_requested = False
    if "--save" in values[:-1]:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /ground collect <path> [path ...] [--save]",
            mode="ground_collect",
        )
    if values and values[-1] == "--save":
        save_requested = True
        values = values[:-1]

    if not values:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /ground collect <path> [path ...] [--save]",
            mode="ground_collect",
        )

    documents: list[tuple[object, str]] = []
    seen: set[str] = set()

    for raw_path in values:
        try:
            target = _resolve_repo_path(raw_path)
        except RepoPathError as exc:
            return BatchResult(
                input=original,
                ok=False,
                returncode=2,
                stderr=f"repo path error: {exc}",
                mode="ground_collect",
            )

        rel_path = _repo_relative_path(target)
        if rel_path in seen:
            continue
        seen.add(rel_path)

        if not target.exists():
            return BatchResult(
                input=original,
                ok=False,
                returncode=2,
                stderr=f"repo path not found: {raw_path}",
                mode="ground_collect",
            )
        if not target.is_file():
            return BatchResult(
                input=original,
                ok=False,
                returncode=2,
                stderr=f"repo path is not a file: {raw_path}",
                mode="ground_collect",
            )

        try:
            documents.append((ground_repo_file(target), _repo_relative_path(target)))
        except GroundingError as exc:
            return BatchResult(
                input=original,
                ok=False,
                returncode=2,
                stderr=f"grounding error: {exc}",
                mode="ground_collect",
            )

    base_output = _clip_ground_output(_render_grounded_collection(documents))
    if not save_requested:
        return BatchResult(
            input=original,
            ok=True,
            returncode=0,
            stdout=base_output,
            mode="ground_collect",
        )

    try:
        write_result = write_ground_report(
            kind="collect",
            command=original,
            report_text=base_output,
            metadata={
                "source_paths": "\n".join(display_path for _, display_path in documents),
            },
            report_root=GROUND_REPORT_ROOT,
        )
    except GroundReportError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"ground report error: {exc}",
            mode="ground_collect",
        )

    stdout = _append_ground_summary(base_output, _ground_report_summary_lines(write_result))
    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=stdout,
        mode="ground_collect",
    )


def _run_ground_search(args: Sequence[str], original: str) -> BatchResult:
    values = list(args)
    save_requested = False
    if "--save" in values[:-1]:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /ground search <query> [--save]",
            mode="ground_search",
        )
    if values and values[-1] == "--save":
        save_requested = True
        values = values[:-1]

    query = " ".join(values).strip()
    if not query:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /ground search <query> [--save]",
            mode="ground_search",
        )

    try:
        search_results = search_repo_paths(query, ROOT, limit=5)
    except SearchRepoError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"repo search error: {exc}",
            mode="ground_search",
        )

    grounded: list[tuple[object, str]] = []
    seen: set[str] = set()
    for result in search_results:
        target = _resolve_repo_path(result.path)
        if not target.exists() or not target.is_file():
            continue
        display_path = _repo_relative_path(target)
        if display_path in seen:
            continue
        seen.add(display_path)
        try:
            grounded.append((ground_repo_file(target), display_path))
        except GroundingError:
            continue

    if not grounded:
        base_output = _clip_ground_output(
            "GROUND search:\n" f"query: {query}\n" f"result_count: {len(search_results)}\n" "no matches\n"
        )
    else:
        base_output = _clip_ground_output(_render_grounded_search(query, grounded))

    if not save_requested:
        return BatchResult(
            input=original,
            ok=True,
            returncode=0,
            stdout=base_output,
            mode="ground_search",
        )

    try:
        write_result = write_ground_report(
            kind="search",
            command=original,
            report_text=base_output,
            metadata={
                "query": query,
                "source_paths": "\n".join(display_path for _, display_path in grounded),
                "result_count": str(len(search_results)),
            },
            report_root=GROUND_REPORT_ROOT,
        )
    except GroundReportError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"ground report error: {exc}",
            mode="ground_search",
        )

    stdout = _append_ground_summary(base_output, _ground_report_summary_lines(write_result))
    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=stdout,
        mode="ground_search",
    )


def _clip_text(text: str, *, limit: int = 4000) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n[TRUNCATED]"


def _indent_block(text: str, *, prefix: str = "    ") -> str:
    lines = str(text or "").splitlines() or [""]
    return "\n".join(prefix + line for line in lines)


def _cache_summary_lines(cache_result) -> list[str]:
    lines = [
        f"  cache_id: {cache_result.cache_id}",
        f"  cache_dir: {cache_result.cache_dir}",
        f"  metadata: {cache_result.metadata_path}",
        f"  report: {cache_result.report_path}",
    ]
    for path in cache_result.artifact_paths:
        lines.append(f"  artifact: {path}")
    lines.append("  cache artifact written")
    return lines


def _run_search(args: Sequence[str], original: str) -> BatchResult:
    search_args = list(args)
    save = False
    if "--save" in search_args[:-1]:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /search web <query> [--save]",
            mode="web_search",
        )
    if search_args and search_args[-1] == "--save":
        save = True
        search_args = search_args[:-1]

    if not search_args:
        usage = "usage: /search web <query> [--save]" if surface == "web" else "usage: /search <web|repo> <query> [--save]"
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=usage,
            mode="web_search",
        )

    surface = search_args[0].lower()
    if surface not in {"web", "repo"}:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /search <web|repo> <query> [--save]",
            mode="web_search",
        )

    if len(search_args) < 2:
        usage = "usage: /search web <query> [--save]" if surface == "web" else "usage: /search <web|repo> <query> [--save]"
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=usage,
            mode="web_search" if surface == "web" else "repo_search",
        )

    query = " ".join(search_args[1:]).strip()
    if not query:
        usage = "usage: /search web <query> [--save]" if surface == "web" else "usage: /search <web|repo> <query> [--save]"
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=usage,
            mode="web_search" if surface == "web" else "repo_search",
        )

    if surface == "repo":
        try:
            results = search_repo_paths(query, ROOT, limit=50)
        except SearchRepoError as exc:
            return BatchResult(
                input=original,
                ok=False,
                returncode=2,
                stderr=f"repo search error: {exc}",
                mode="repo_search",
            )
        return BatchResult(
            input=original,
            ok=True,
            returncode=0,
            stdout=_render_repo_search_output(results),
            mode="repo_search",
        )

    try:
        results = search_web(query, limit=5)
    except WebSearchError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"search command error: {exc}",
            mode="web_search",
        )

    lines = [
        "WEB search:",
        f"  query: {query}",
        f"  results: {len(results)}",
    ]

    if not results:
        lines.append("  no results")
    else:
        for index, result in enumerate(results, start=1):
            title = _clip_text(result.title or result.url or "(untitled)", limit=180)
            snippet = _clip_text(result.snippet or "", limit=360)
            lines.append(f"  {index}. {title}")
            lines.append(f"     url: {result.url}")
            if snippet:
                lines.append(f"     snippet: {snippet}")

    if save:
        try:
            cache_result = write_search_cache(cache_root=WEB_CACHE_ROOT, query=query, results=results)
        except WebCacheError as exc:
            return BatchResult(
                input=original,
                ok=False,
                returncode=2,
                stderr=f"search cache error: {exc}",
                mode="web_search",
            )
        lines.extend(_cache_summary_lines(cache_result))

    stdout = _clip_text("\n".join(lines) + "\n", limit=4000)
    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=stdout,
        mode="web_search",
    )


def _run_web(args: Sequence[str], original: str) -> BatchResult:
    if not args:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /web <fetch|extract> <url> [--cache] | /web search <query> [--save]",
            mode="web_front_door",
        )

    action = args[0].lower()
    if action == "search":
        return _run_search(["web", *args[1:]], original)
    if action not in {"fetch", "extract"}:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /web <fetch|extract> <url> [--cache] | /web search <query> [--save]",
            mode="web_front_door",
        )

    if len(args) not in {2, 3} or (len(args) == 3 and args[2] != "--cache"):
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"usage: /web {action} <url> [--cache]",
            mode="web_front_door",
        )

    url = args[1].strip()
    cache_requested = len(args) == 3

    try:
        from core.web.extractor import extract_html
        from core.web.fetcher import WebFetchError, fetch_url
    except Exception as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"web command error: {exc}",
            mode="web_front_door",
        )

    try:
        result = fetch_url(url)
    except WebFetchError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"web command error: {exc}",
            mode="web_front_door",
        )

    if action == "fetch":
        title = _clip_text(result.extracted.title if result.extracted and result.extracted.title else result.title or "", limit=4000)
        lines = [
            "WEB fetch:",
            f"  url: {result.url}",
            f"  final_url: {result.final_url}",
            f"  status: {result.status_code}",
            f"  content_type: {result.content_type or 'unknown'}",
            f"  content_bytes: {len(result.content)}",
        ]
        if title:
            lines.append(f"  title: {title}")
        if cache_requested:
            try:
                cache_result = write_fetch_cache(
                    cache_root=WEB_CACHE_ROOT,
                    url=result.url,
                    final_url=result.final_url,
                    status_code=result.status_code,
                    content=result.content,
                    content_type=result.content_type,
                    title=result.extracted.title if result.extracted and result.extracted.title else result.title,
                )
            except WebCacheError as exc:
                return BatchResult(
                    input=original,
                    ok=False,
                    returncode=2,
                    stderr=f"web cache error: {exc}",
                    mode="web_front_door",
                )
            lines.extend(_cache_summary_lines(cache_result))
        return BatchResult(
            input=original,
            ok=True,
            returncode=0,
            stdout="\n".join(lines) + "\n",
            mode="web_front_door",
        )

    extracted = result.extracted
    if extracted is None:
        decoded = result.text if result.text else result.content.decode("utf-8", errors="replace")
        extracted = extract_html(decoded, url=result.final_url)

    snippet = _clip_text(extracted.text or result.text or "", limit=4000)
    lines = [
        "WEB extract:",
        f"  url: {result.url}",
        f"  final_url: {result.final_url}",
        f"  status: {result.status_code}",
        f"  title: {extracted.title or result.title or 'unknown'}",
        "  extracted_text:",
        _indent_block(snippet if snippet else "(empty)"),
    ]
    if cache_requested:
        try:
            cache_result = write_extract_cache(
                cache_root=WEB_CACHE_ROOT,
                url=result.url,
                normalized_url=result.final_url,
                extracted_text=extracted.text or result.text or "",
                source=extracted.source or "unknown",
                content_type=result.content_type,
                title=extracted.title or result.title,
            )
        except WebCacheError as exc:
            return BatchResult(
                input=original,
                ok=False,
                returncode=2,
                stderr=f"web cache error: {exc}",
                mode="web_front_door",
            )
        lines.extend(_cache_summary_lines(cache_result))
    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout="\n".join(lines) + "\n",
        mode="web_front_door",
    )


def _run_scrape(args: Sequence[str], original: str) -> BatchResult:
    if not args:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /scrape <url> | /scrape extract <url>",
            mode="scrape_frontdoor",
        )

    action = str(args[0]).lower().strip()
    if action in {"fetch", "extract"}:
        if len(args) != 2:
            return BatchResult(
                input=original,
                ok=False,
                returncode=2,
                stderr=f"usage: /scrape {action} <url>",
                mode="scrape_frontdoor",
            )
        url = str(args[1]).strip()
    else:
        if len(args) != 1:
            return BatchResult(
                input=original,
                ok=False,
                returncode=2,
                stderr="usage: /scrape <url> | /scrape extract <url>",
                mode="scrape_frontdoor",
            )
        url = str(args[0]).strip()

    try:
        from core.web.extractor import extract_html
        from core.web.fetcher import WebFetchError, fetch_url
    except Exception as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"scrape command error: {exc}",
            mode="scrape_frontdoor",
        )

    try:
        result = fetch_url(url)
    except WebFetchError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"scrape command error: {exc}",
            mode="scrape_frontdoor",
        )

    extracted = result.extracted
    if extracted is None:
        decoded = result.text if result.text else result.content.decode("utf-8", errors="replace")
        extracted = extract_html(decoded, url=result.final_url)

    snippet = _clip_text(extracted.text or result.text or "", limit=4000)
    lines = [
        "SCRAPE extract:",
        f"  url: {result.url}",
        f"  final_url: {result.final_url}",
        f"  status: {result.status_code}",
        f"  title: {extracted.title or result.title or 'unknown'}",
        "  extracted_text:",
        _indent_block(snippet if snippet else "(empty)"),
    ]
    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout="\n".join(lines) + "\n",
        mode="scrape_frontdoor",
    )


def _run_python_script(script: str, args: Sequence[str], original: str) -> BatchResult:
    cmd = [sys.executable, script, *args]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
        timeout=45,
    )
    return BatchResult(
        input=original,
        ok=(proc.returncode == 0),
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _run_llm(args: Sequence[str], original: str) -> BatchResult:
    from core.llm_frontdoor import (
        LlmFrontdoorError,
        build_llm_apply_plan,
        build_llm_apply_write,
        build_llm_preset,
        build_llm_status,
        llm_help_text,
        parse_llm_command,
    )

    args_text = " ".join(args).strip()
    if args_text in {"help", "--help", "-h"}:
        return BatchResult(
            input=original,
            ok=True,
            returncode=0,
            stdout=llm_help_text() + "\n",
            mode="llm_front_door",
        )

    try:
        parsed = parse_llm_command("/llm" if not args_text else "/llm " + args_text)
        if parsed.action == "status":
            stdout = build_llm_status()
        elif parsed.action == "preset":
            stdout = build_llm_preset(parsed.preset or "")
        elif parsed.action == "apply":
            if parsed.write and parsed.confirm:
                stdout = build_llm_apply_write(parsed.preset or "")
            else:
                stdout = build_llm_apply_plan(parsed.preset or "")
        else:
            raise LlmFrontdoorError(f"unsupported /llm action: {parsed.action}")
    except LlmFrontdoorError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"llm command error: {exc}",
            mode="llm_front_door",
        )

    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=stdout + ("\n" if stdout and not stdout.endswith("\n") else ""),
        mode="llm_front_door",
    )


def _run_codex(args: Sequence[str], original: str) -> BatchResult:
    from core.codex_frontdoor import CodexFrontdoorError, build_codex_command, build_codex_package_prompt, parse_codex_command

    try:
        parsed = parse_codex_command("/codex " + " ".join(shlex.quote(str(arg)) for arg in args))
        command = build_codex_command(parsed, repo_root=ROOT)
    except CodexFrontdoorError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"codex command error: {exc}",
            mode="codex_frontdoor",
        )

    if parsed.action == "package":
        stdout = build_codex_package_prompt(parsed.task or "")
    else:
        stdout = shlex.join(command)

    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=stdout + ("\n" if stdout and not stdout.endswith("\n") else ""),
        mode="codex_frontdoor",
    )



def _run_patch(args: Sequence[str], original: str) -> BatchResult:
    from core.patch_frontdoor import PatchFrontdoorError, run_patch_command

    try:
        result = run_patch_command("/patch " + " ".join(shlex.quote(str(arg)) for arg in args), repo_root=ROOT)
    except PatchFrontdoorError as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"patch command error: {exc}",
            mode="patch_frontdoor",
        )

    return BatchResult(
        input=original,
        ok=result.ok,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        mode="patch_frontdoor",
    )


def _dispatch_registry_backed_repo_surface(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    plan = _execution_dispatch.build_dispatch_plan(root, args=args, registry=_EXECUTION_DISPATCH_REGISTRY)
    if not plan.allowed or plan.registry_name not in {"read", "ls", "tree", "find"}:
        return None

    if plan.registry_name == "read":
        if root == "read" and len(args) == 1:
            target_text = args[0]
            try:
                target = _resolve_repo_path(target_text)
            except RepoPathError:
                return _run_read(args, original)

            if target.exists() and target.is_dir():
                return _run_ls([args[0]], original)

            if target_text.endswith("/"):
                return _run_ls([args[0]], original)

        return _run_read(args, original)

    if plan.registry_name == "ls":
        return _run_ls(args, original)

    if plan.registry_name == "tree":
        return _run_tree(args, original)

    if plan.registry_name == "find":
        return _run_find(args, original)

    return None


def _run_repo_frontdoor(tokens: Sequence[str], original: str) -> BatchResult | None:
    if not tokens:
        return None

    registry_result = _dispatch_registry_backed_repo_surface(tokens[0], tokens[1:], original)
    if registry_result is not None:
        return registry_result

    if tokens[0] == "/ground" and len(tokens) >= 2 and tokens[1] == "repo":
        return _run_ground_repo(tokens[2:], original)

    if tokens[0] == "/ground" and len(tokens) >= 2 and tokens[1] == "reports":
        return _run_ground_reports(tokens[2:], original)

    if tokens[0] == "/ground" and len(tokens) >= 2 and tokens[1] == "show":
        return _run_ground_show(tokens[2:], original)

    if tokens[0] == "/ground" and len(tokens) >= 2 and tokens[1] == "collect":
        return _run_ground_collect(tokens[2:], original)

    if tokens[0] == "/ground" and len(tokens) >= 2 and tokens[1] == "search":
        return _run_ground_search(tokens[2:], original)

    if tokens[0] == "ls":
        return _run_ls(tokens[1:], original)

    if tokens[0] == "read":
        if len(tokens) == 2:
            target_text = tokens[1]
            try:
                target = _resolve_repo_path(target_text)
            except RepoPathError:
                return _run_read(tokens[1:], original)

            if target.exists() and target.is_dir():
                return _run_ls([tokens[1]], original)

            if target_text.endswith("/"):
                return _run_ls([tokens[1]], original)

        return _run_read(tokens[1:], original)

    if tokens[0] == "tree":
        return _run_tree(tokens[1:], original)

    if tokens[0] == "find":
        return _run_find(tokens[1:], original)

    if tokens[0] == "ground" and len(tokens) >= 2 and tokens[1] == "repo":
        return _run_ground_repo(tokens[2:], original)

    if tokens[0] == "ground" and len(tokens) >= 2 and tokens[1] == "reports":
        return _run_ground_reports(tokens[2:], original)

    if tokens[0] == "ground" and len(tokens) >= 2 and tokens[1] == "show":
        return _run_ground_show(tokens[2:], original)

    if tokens[0] == "ground" and len(tokens) >= 2 and tokens[1] == "collect":
        return _run_ground_collect(tokens[2:], original)

    if tokens[0] == "ground" and len(tokens) >= 2 and tokens[1] == "search":
        return _run_ground_search(tokens[2:], original)

    return None


def _fake_chat_response(original: str) -> BatchResult | None:
    fake = os.environ.get("AGENT_CLI_FAKE_CHAT_RESPONSE")
    if not fake:
        return None
    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=fake + ("\n" if fake and not fake.endswith("\n") else ""),
        stderr="",
        mode="chat",
    )


def _run_chat(original: str) -> BatchResult:
    fake = _fake_chat_response(original)
    if fake is not None:
        return fake

    try:
        from core.llm_config import default_llm_config

        config = default_llm_config()
        base_url = str(
            os.environ.get(
                "AGENT_CLI_CHAT_BASE_URL",
                getattr(config, "base_url", "http://127.0.0.1:11434"),
            )
        ).rstrip("/")
        model = str(os.environ.get("AGENT_CLI_CHAT_MODEL", getattr(config, "model", "llama3:8b")))
        timeout_value = os.environ.get("AGENT_CLI_CHAT_TIMEOUT_SECONDS")
        timeout = int(timeout_value) if timeout_value else None
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": original}],
            "stream": False,
        }
        req = urlrequest.Request(
            base_url + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urlrequest.urlopen(req, timeout=timeout) if timeout is not None else urlrequest.urlopen(req)
        with opener as response:
            data = json.loads(response.read().decode("utf-8"))

        message = data.get("message") if isinstance(data, dict) else None
        if isinstance(message, dict):
            content = str(message.get("content", ""))
        else:
            content = str(data.get("response", "")) if isinstance(data, dict) else ""

        return BatchResult(
            input=original,
            ok=True,
            returncode=0,
            stdout=content + ("\n" if content and not content.endswith("\n") else ""),
            stderr="",
            mode="chat",
        )
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=1,
            stderr=f"chat error: {exc}",
            mode="chat",
        )


def _run_prompt(args: Sequence[str], original: str) -> BatchResult:
    message = " ".join(str(arg) for arg in args).strip()
    if not message:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /prompt <message>",
            mode="chat",
        )
    result = _run_chat(message)
    return BatchResult(
        input=original,
        ok=result.ok,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        mode=result.mode,
    )


def _run_raw_prompt(args: Sequence[str], original: str) -> BatchResult:
    message = " ".join(str(arg) for arg in args).strip()
    if not message:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /prompt <message>",
            mode="chat",
        )
    result = _run_chat(message)
    return BatchResult(
        input=original,
        ok=result.ok,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        mode=result.mode,
    )


def _run_question(args: Sequence[str], original: str) -> BatchResult:
    message = " ".join(str(arg) for arg in args).strip()
    if not message:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: /question <message>",
            mode="grounded_answer",
        )

    try:
        from core.agent_runtime import AgentCore
    except Exception as exc:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=f"question command error: {exc}",
            mode="grounded_answer",
        )

    core = AgentCore(event_sink=None)
    result = core.grounded_llm_reply(user_text=message, query=message, allow_web_fallback=True)
    response = str(result.get("response") or "")
    ok = bool(result.get("ok"))
    return BatchResult(
        input=original,
        ok=ok,
        returncode=0 if ok else 2,
        stdout=(response + ("\n" if response and ok and not response.endswith("\n") else "")) if ok else "",
        stderr="" if ok else response,
        mode="grounded_answer",
    )


def _run_route_dry_run(args: Sequence[str], original: str) -> BatchResult:
    if not args:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: inspect <input> [--format json|markdown]",
            mode="semantic_route_dry_run",
        )

    action = str(args[0]).strip().lower()
    if action not in {"inspect", "dry-run"}:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: inspect <input> [--format json|markdown]",
            mode="semantic_route_dry_run",
        )

    remaining = list(args[1:])
    output_format = "json"
    cleaned: list[str] = []
    index = 0
    while index < len(remaining):
        token = remaining[index]
        if token == "--format":
            if index + 1 >= len(remaining):
                return BatchResult(
                    input=original,
                    ok=False,
                    returncode=2,
                    stderr="usage: inspect <input> [--format json|markdown]",
                    mode="semantic_route_dry_run",
                )
            output_format = str(remaining[index + 1]).strip().lower()
            index += 2
            continue
        cleaned.append(token)
        index += 1

    input_text = " ".join(cleaned).strip()
    if not input_text:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: inspect <input> [--format json|markdown]",
            mode="semantic_route_dry_run",
        )

    if output_format not in {"json", "markdown"}:
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr="usage: inspect <input> [--format json|markdown]",
            mode="semantic_route_dry_run",
        )

    from core.semantic_route_dry_run import (
        build_semantic_route_dry_run_artifact,
        render_semantic_route_audit_json,
        render_semantic_route_audit_markdown,
    )

    artifact = build_semantic_route_dry_run_artifact(input_text)
    if output_format == "markdown":
        stdout = render_semantic_route_audit_markdown(artifact)
    else:
        stdout = render_semantic_route_audit_json(artifact)

    return BatchResult(
        input=original,
        ok=True,
        returncode=0,
        stdout=stdout,
        mode="semantic_route_dry_run",
    )


def _dispatch_switch_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    if len(args) >= 2 and args[0] == "profile":
        return _run_python_script(
            "external CLI payloads/switch_profiles_tool.py",
            args[1:],
            original,
        )
    return _run_python_script(
        "external CLI payloads/switch_matrix_tool.py",
        args,
        original,
    )


def _dispatch_tool_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    if len(args) < 2:
        return None
    tool_id = args[0]
    tool_args = args[1:]
    if tool_id == "switch.matrix":
        return _run_python_script("external CLI payloads/switch_matrix_tool.py", tool_args, original)
    if tool_id == "switch.profiles":
        return _run_python_script("external CLI payloads/switch_profiles_tool.py", tool_args, original)
    return None


def _dispatch_llm_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_llm(args, original)


def _dispatch_codex_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_codex(args, original)


def _dispatch_search_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_search(args, original)


def _dispatch_web_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_web(args, original)


def _dispatch_scrape_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_scrape(args, original)


def _dispatch_ground_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_repo_frontdoor((root, *args), original)


def _dispatch_repo_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_repo_frontdoor((root, *args), original)


def _dispatch_patch_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_patch(args, original)


def _dispatch_prompt_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_prompt(args, original)


def _dispatch_raw_prompt_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_raw_prompt(args, original)


def _dispatch_question_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_question(args, original)


def _dispatch_route_frontdoor(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    return _run_route_dry_run(args, original)


_BATCH_HANDLER_REGISTRY: dict[str, BatchHandler] = {
    "switch_frontdoor": BatchHandler(
        key="switch_frontdoor",
        roots=("/switch",),
        dispatch=_dispatch_switch_frontdoor,
    ),
    "tool_frontdoor": BatchHandler(
        key="tool_frontdoor",
        roots=("/tool",),
        dispatch=_dispatch_tool_frontdoor,
    ),
    "llm_frontdoor": BatchHandler(
        key="llm_frontdoor",
        roots=("/llm", "llm"),
        dispatch=_dispatch_llm_frontdoor,
    ),
    "codex_frontdoor": BatchHandler(
        key="codex_frontdoor",
        roots=("/codex",),
        dispatch=_dispatch_codex_frontdoor,
    ),
    "search_frontdoor": BatchHandler(
        key="search_frontdoor",
        roots=("/search",),
        dispatch=_dispatch_search_frontdoor,
    ),
    "web_frontdoor": BatchHandler(
        key="web_frontdoor",
        roots=("/web",),
        dispatch=_dispatch_web_frontdoor,
    ),
    "scrape_frontdoor": BatchHandler(
        key="scrape_frontdoor",
        roots=("/scrape",),
        dispatch=_dispatch_scrape_frontdoor,
    ),
    "ground_frontdoor": BatchHandler(
        key="ground_frontdoor",
        roots=("/ground",),
        dispatch=_dispatch_ground_frontdoor,
    ),
    "repo_frontdoor": BatchHandler(
        key="repo_frontdoor",
        roots=("/read", "/ls", "/tree", "/find", "read", "ls", "tree", "find", "ground"),
        dispatch=_dispatch_repo_frontdoor,
    ),
    "patch_frontdoor": BatchHandler(
        key="patch_frontdoor",
        roots=("/patch",),
        dispatch=_dispatch_patch_frontdoor,
    ),
    "prompt_frontdoor": BatchHandler(
        key="prompt_frontdoor",
        roots=PROMPT_LANE_ROOTS,
        dispatch=_dispatch_prompt_frontdoor,
    ),
    "raw_prompt_frontdoor": BatchHandler(
        key="raw_prompt_frontdoor",
        roots=RAW_PROMPT_ROOTS,
        dispatch=_dispatch_raw_prompt_frontdoor,
    ),
    "question_frontdoor": BatchHandler(
        key="question_frontdoor",
        roots=QUESTION_ROOTS,
        dispatch=_dispatch_question_frontdoor,
    ),
    "route_frontdoor": BatchHandler(
        key="route_frontdoor",
        roots=ROUTE_ROOTS,
        dispatch=_dispatch_route_frontdoor,
    ),
}

_BATCH_HANDLER_ROOT_MAP = {
    root: handler_key
    for handler_key, handler in _BATCH_HANDLER_REGISTRY.items()
    for root in handler.roots
}


def _dispatch_registered_handler(root: str, args: Sequence[str], original: str) -> BatchResult | None:
    handler_key = _BATCH_HANDLER_ROOT_MAP.get(root)
    if handler_key is None:
        return None
    handler = _BATCH_HANDLER_REGISTRY[handler_key]
    return handler.dispatch(root, args, original)


def run_command(command: str) -> BatchResult:
    """Run one non-interactive command through a narrow safe route.

    This function is not a general command executor. It supports only explicitly
    handled agent surfaces and does not call the interactive agent.py loop.
    """

    original = str(command or "").strip()
    if not original:
        return BatchResult(input="", ok=True, returncode=0, stdout="", mode="empty")

    try:
        tokens = shlex.split(original)
    except ValueError as exc:
        return BatchResult(input=original, ok=False, returncode=2, stderr=f"parse error: {exc}")

    if not tokens:
        return BatchResult(input=original, ok=True, returncode=0, stdout="", mode="empty")

    registered = _dispatch_registered_handler(tokens[0], tokens[1:], original)
    if registered is not None:
        return registered

    if tokens[0].startswith("/"):
        return BatchResult(
            input=original,
            ok=False,
            returncode=2,
            stderr=(
                "unsupported agent-cli command; supported surfaces: "
                "/switch, /switch profile, /tool switch.matrix, /tool switch.profiles, "
                "/prompt, /ground, "
                "/llm, /codex, /search, /web, /scrape, /read, /ls, /tree, /find, /patch, "
            ),
        )

    return BatchResult(
        input=original,
        ok=False,
        returncode=2,
        stderr=(
            "plain text input is not sent to the LLM; use /prompt for direct model work or /ground / /question for grounded answers. "
            "Other prompt-template commands are legacy/experimental compatibility surfaces"
        ),
        mode="validation_error",
    )


def run_commands(commands: Iterable[str]) -> List[BatchResult]:
    results: List[BatchResult] = []
    for command in commands:
        text = str(command or "").strip()
        if not text:
            continue
        results.append(run_command(text))
    return results


def format_result(result: BatchResult, fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps(result.to_dict(), sort_keys=True)
    if result.stdout:
        return result.stdout
    if result.stderr:
        return result.stderr + ("\n" if not result.stderr.endswith("\n") else "")
    return ""


def format_results(results: Sequence[BatchResult], fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps([result.to_dict() for result in results], sort_keys=True)
    if fmt == "jsonl":
        return "\n".join(json.dumps(result.to_dict(), sort_keys=True) for result in results)
    return "".join(format_result(result, "text") for result in results)


def exit_code(results: Sequence[BatchResult]) -> int:
    for result in results:
        if not result.ok:
            return result.returncode or 1
    return 0
