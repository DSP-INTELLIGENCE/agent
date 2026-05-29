"""Deterministic local grounding report artifacts."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_GROUND_REPORT_ROOT = Path("reports/ground")
GROUND_REPORT_TIMESTAMP = "1970-01-01T00:00:00Z"


class GroundReportError(ValueError):
    pass


@dataclass(frozen=True)
class GroundReportWriteResult:
    report_id: str
    report_dir: Path
    report_path: Path
    metadata_path: Path
    artifact_paths: tuple[Path, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "report_dir": str(self.report_dir),
            "report_path": str(self.report_path),
            "metadata_path": str(self.metadata_path),
            "artifact_paths": [str(path) for path in self.artifact_paths],
            "metadata": dict(self.metadata),
        }


def build_ground_report_id(value: str) -> str:
    normalized = _normalize_text(value)
    digest = hashlib.sha256(f"ground-report:v1:{normalized}".encode("utf-8")).hexdigest()
    return digest[:16]


def write_ground_report(
    *,
    kind: str,
    command: str,
    report_text: str,
    metadata: dict[str, str],
    report_root: Path | str = DEFAULT_GROUND_REPORT_ROOT,
) -> GroundReportWriteResult:
    kind_text = _normalize_text(kind).lower()
    if kind_text not in {"repo", "collect", "search"}:
        raise GroundReportError(f"unsupported report kind: {kind}")

    normalized_command = _normalize_text(command)
    normalized_metadata = {str(key): _normalize_text(value) for key, value in metadata.items()}
    seed_payload = {
        "command": normalized_command,
        "kind": kind_text,
        **normalized_metadata,
    }
    report_id = build_ground_report_id(json.dumps(seed_payload, sort_keys=True, separators=(",", ":")))

    report_dir = Path(report_root).expanduser() / kind_text / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    report_path = report_dir / "report.txt"
    metadata_path = report_dir / "metadata.json"

    report_body = _ensure_trailing_newline(str(report_text or ""))
    report_bytes = report_body.encode("utf-8")
    report_metadata: dict[str, Any] = {
        "report_id": report_id,
        "kind": kind_text,
        "command": normalized_command,
        "timestamp": GROUND_REPORT_TIMESTAMP,
        "report_bytes": str(len(report_bytes)),
        "report_sha256": _sha256_bytes(report_bytes),
    }
    report_metadata.update(normalized_metadata)

    _write_text(report_path, report_body)
    _write_json(metadata_path, report_metadata)

    return GroundReportWriteResult(
        report_id=report_id,
        report_dir=report_dir,
        report_path=report_path,
        metadata_path=metadata_path,
        artifact_paths=(metadata_path, report_path),
        metadata=report_metadata,
    )


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
