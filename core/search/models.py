"""Search data models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchResult:
    path: str
    kind: str
    score: int = 0
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "score": self.score,
            "snippet": self.snippet,
        }
