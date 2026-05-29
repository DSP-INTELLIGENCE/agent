"""Scrape data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScrapeResult:
    url: str
    title: str
    text: str
    links: tuple[str, ...] = field(default_factory=tuple)
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "links": list(self.links),
            "source": self.source,
        }
