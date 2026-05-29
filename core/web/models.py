"""Web engine data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WebExtractResult:
    url: str | None = None
    title: str = ""
    text: str = ""
    source: str = "unknown"
    links: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "source": self.source,
            "links": list(self.links),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str = ""
    source: str = "ddgs"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
        }


@dataclass(frozen=True)
class WebFetchResult:
    url: str
    final_url: str
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    content: bytes = b""
    content_type: str = ""
    title: str = ""
    text: str = ""
    extracted: WebExtractResult | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= int(self.status_code) < 300 and not self.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "status_code": self.status_code,
            "headers": dict(self.headers),
            "content_bytes": len(self.content),
            "content_type": self.content_type,
            "title": self.title,
            "text": self.text,
            "extracted": self.extracted.to_dict() if self.extracted else None,
            "error": self.error,
            "ok": self.ok,
        }
