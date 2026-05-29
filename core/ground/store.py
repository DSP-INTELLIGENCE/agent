"""Read-only lookup helpers for deterministic grounding reports."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .report import DEFAULT_GROUND_REPORT_ROOT


GROUND_REPORT_KINDS = ("repo", "collect", "search")
GROUND_REPORT_LIST_LIMIT = 20


class GroundReportLookupError(ValueError):
    pass


@dataclass(frozen=True)
class GroundReportSummary:
    report_id: str
    kind: str
    command: str
    timestamp: str
    report_dir: Path
    report_path: Path
    metadata_path: Path
    report_sha256: str


@dataclass(frozen=True)
class GroundReportRecord(GroundReportSummary):
    report_text: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "kind": self.kind,
            "command": self.command,
            "timestamp": self.timestamp,
            "report_dir": str(self.report_dir),
            "report_path": str(self.report_path),
            "metadata_path": str(self.metadata_path),
            "report_sha256": self.report_sha256,
            "report_text": self.report_text,
            "metadata": dict(self.metadata),
        }


def list_ground_reports(
    report_root: Path | str = DEFAULT_GROUND_REPORT_ROOT,
    *,
    limit: int = GROUND_REPORT_LIST_LIMIT,
) -> list[GroundReportSummary]:
    root = Path(report_root).expanduser()
    if not root.exists():
        return []

    bounded_limit = _bound_limit(limit)
    summaries: list[GroundReportSummary] = []
    for kind in GROUND_REPORT_KINDS:
        kind_dir = root / kind
        if not kind_dir.is_dir():
            continue
        for report_dir in sorted((path for path in kind_dir.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True):
            summary = _read_summary(kind, report_dir)
            if summary is None:
                continue
            summaries.append(summary)

    summaries.sort(key=lambda item: (item.timestamp, item.report_id), reverse=True)
    return summaries[:bounded_limit]


def load_ground_report(report_root: Path | str, report_id: str) -> GroundReportRecord:
    normalized_report_id = _normalize_report_id(report_id)
    root = Path(report_root).expanduser()
    if not root.exists():
        raise GroundReportLookupError(f"unknown report id: {normalized_report_id}")

    for kind in GROUND_REPORT_KINDS:
        report_dir = root / kind / normalized_report_id
        if not report_dir.is_dir():
            continue
        summary = _read_summary(kind, report_dir)
        if summary is None:
            raise GroundReportLookupError(f"malformed report directory: {report_dir}")
        metadata_path = report_dir / "metadata.json"
        report_path = report_dir / "report.txt"
        metadata = _read_json(metadata_path)
        report_text = _read_text(report_path)
        if metadata is None or report_text is None:
            raise GroundReportLookupError(f"malformed report directory: {report_dir}")
        return GroundReportRecord(
            report_id=summary.report_id,
            kind=summary.kind,
            command=summary.command,
            timestamp=summary.timestamp,
            report_dir=summary.report_dir,
            report_path=summary.report_path,
            metadata_path=summary.metadata_path,
            report_sha256=summary.report_sha256,
            report_text=report_text,
            metadata=metadata,
        )

    raise GroundReportLookupError(f"unknown report id: {normalized_report_id}")


def _read_summary(kind: str, report_dir: Path) -> GroundReportSummary | None:
    metadata_path = report_dir / "metadata.json"
    report_path = report_dir / "report.txt"
    if not metadata_path.is_file() or not report_path.is_file():
        return None

    metadata = _read_json(metadata_path)
    if metadata is None:
        return None

    report_id = _normalize_text(metadata.get("report_id", ""))
    kind_text = _normalize_text(metadata.get("kind", ""))
    if not report_id or report_id != report_dir.name or kind_text != kind:
        return None

    return GroundReportSummary(
        report_id=report_id,
        kind=kind_text,
        command=_normalize_text(metadata.get("command", "")),
        timestamp=_normalize_text(metadata.get("timestamp", "")),
        report_dir=report_dir,
        report_path=report_path,
        metadata_path=metadata_path,
        report_sha256=_normalize_text(metadata.get("report_sha256", "")),
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _bound_limit(value: int) -> int:
    try:
        limit = int(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise GroundReportLookupError(f"invalid limit: {value}") from exc
    if limit < 1:
        raise GroundReportLookupError("limit must be at least 1")
    return min(limit, GROUND_REPORT_LIST_LIMIT)


def _normalize_report_id(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        raise GroundReportLookupError("report id is required")
    candidate = Path(text)
    if candidate.name != text or text in {".", ".."} or "/" in text or "\\" in text:
        raise GroundReportLookupError(f"invalid report id: {value}")
    return text


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())
