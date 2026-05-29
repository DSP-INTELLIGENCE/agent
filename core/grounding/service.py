"""Provider-backed EvidencePacket service for `/ground`."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .evidence import EvidenceClaim, EvidencePacket, EvidenceSource
from .providers import GroundingProvider, ProviderResult


@dataclass
class GroundingService:
    """Collect evidence from registered providers into one EvidencePacket."""

    providers: list[GroundingProvider] = field(default_factory=list)

    def register(self, provider: GroundingProvider) -> None:
        self.providers.append(provider)

    def collect(
        self,
        query: str,
        *,
        normalized_query: str = "",
        profile: str = "general_reference",
        targets: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> EvidencePacket:
        provider_results: list[ProviderResult] = []
        sources: list[EvidenceSource] = []
        diagnostics: dict[str, Any] = {"providers": []}

        for provider in self.providers:
            try:
                result = provider.collect(normalized_query or query, targets=targets)
            except Exception as exc:  # provider adapters must not crash /ground
                diagnostics["providers"].append({"provider": getattr(provider, "name", type(provider).__name__), "ok": False, "error": str(exc)})
                continue
            provider_results.append(result)
            sources.extend(result.sources)
            diagnostics["providers"].append({"provider": result.provider, "ok": result.ok, "source_count": len(result.sources)})

        claims = tuple(
            EvidenceClaim.build(
                source.summary or source.text[:240],
                source_ids=(source.id,),
                confidence_score=source.confidence_score,
                metadata={"provider": source.provider},
            )
            for source in sources
            if source.accepted and (source.summary or source.text)
        )
        return EvidencePacket.build(
            query=query,
            normalized_query=normalized_query or query,
            profile=profile,
            targets=targets,
            sources=tuple(sources),
            claims=claims,
            status="ok" if sources else "empty",
            diagnostics=diagnostics,
            metadata=dict(metadata or {}) | {"provider_result_count": len(provider_results)},
        )
