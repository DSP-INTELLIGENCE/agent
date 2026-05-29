"""Grounding data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GroundedExcerpt:
    source_path: str
    start_line: int
    end_line: int
    text: str
    source_kind: str = "repo_file"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "text": self.text,
            "source_kind": self.source_kind,
        }


@dataclass(frozen=True)
class GroundedDocument:
    source_path: str
    title: str
    excerpts: tuple[GroundedExcerpt, ...] = field(default_factory=tuple)
    source_kind: str = "repo_file"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "title": self.title,
            "excerpts": [excerpt.to_dict() for excerpt in self.excerpts],
            "source_kind": self.source_kind,
        }
