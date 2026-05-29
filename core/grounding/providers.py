"""Grounding provider adapter interfaces.

Adapters for packages such as wikipedia-api, trafilatura, crawl4ai, or other
retrievers should implement these protocols and return EvidenceSource objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .evidence import EvidenceSource


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    query: str
    sources: tuple[EvidenceSource, ...] = ()
    ok: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        provider: str,
        query: str,
        sources: Sequence[EvidenceSource] = (),
        ok: bool | None = None,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> "ProviderResult":
        cleaned_sources = tuple(sources)
        return cls(
            provider=str(provider or "unknown"),
            query=str(query or ""),
            sources=cleaned_sources,
            ok=bool(cleaned_sources) if ok is None else bool(ok),
            diagnostics=dict(diagnostics or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "query": self.query,
            "sources": [source.to_dict() for source in self.sources],
            "ok": self.ok,
            "diagnostics": dict(self.diagnostics),
        }


@runtime_checkable
class GroundingProvider(Protocol):
    """Protocol implemented by optional grounding providers."""

    name: str

    def collect(self, query: str, *, targets: Sequence[str] = ()) -> ProviderResult:
        """Return sources for query without calling the LLM."""
        ...


class StaticGroundingProvider:
    """Small deterministic provider useful for tests and local fixtures."""

    name = "static"

    def __init__(self, sources: Sequence[EvidenceSource] = ()) -> None:
        self._sources = tuple(sources)

    def collect(self, query: str, *, targets: Sequence[str] = ()) -> ProviderResult:
        return ProviderResult.build(provider=self.name, query=query, sources=self._sources, diagnostics={"targets": list(targets)})
