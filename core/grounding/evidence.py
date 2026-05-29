"""Stable grounding evidence packet models.

These models are intentionally dependency-free. Provider-specific packages should
adapt into this schema instead of leaking package objects into `/ground`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
import hashlib
import json
import re

EVIDENCE_PACKET_SCHEMA_VERSION = "evidence_packet.v1"


def _clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text).strip()


def _stable_id(*parts: Any, prefix: str = "src") -> str:
    raw = "\x1f".join(_clean_text(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class EvidenceSource:
    """One source of evidence accepted or inspected by grounding."""

    id: str
    provider: str
    title: str = ""
    url: str = ""
    text: str = ""
    summary: str = ""
    source_type: str = "web_page"
    confidence_score: float = 0.0
    accepted: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        provider: str,
        title: str = "",
        url: str = "",
        text: str = "",
        summary: str = "",
        source_type: str = "web_page",
        confidence_score: float = 0.0,
        accepted: bool = True,
        metadata: Mapping[str, Any] | None = None,
        id: str | None = None,
    ) -> "EvidenceSource":
        title = _clean_text(title)
        url = _clean_text(url)
        text = _clean_text(text)
        summary = _clean_text(summary)
        provider = _clean_text(provider) or "unknown"
        source_type = _clean_text(source_type) or "web_page"
        source_id = id or _stable_id(provider, title, url, text[:512])
        return cls(
            id=source_id,
            provider=provider,
            title=title,
            url=url,
            text=text,
            summary=summary,
            source_type=source_type,
            confidence_score=float(confidence_score or 0.0),
            accepted=bool(accepted),
            metadata=dict(metadata or {}),
        )

    def display_text(self) -> str:
        return self.summary or self.text

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "title": self.title,
            "url": self.url,
            "text": self.text,
            "summary": self.summary,
            "source_type": self.source_type,
            "confidence_score": self.confidence_score,
            "accepted": self.accepted,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceSource":
        return cls.build(
            id=_clean_text(data.get("id")) or None,
            provider=_clean_text(data.get("provider")) or "unknown",
            title=_clean_text(data.get("title")),
            url=_clean_text(data.get("url")),
            text=_clean_text(data.get("text")),
            summary=_clean_text(data.get("summary")),
            source_type=_clean_text(data.get("source_type")) or "web_page",
            confidence_score=float(data.get("confidence_score") or 0.0),
            accepted=bool(data.get("accepted", True)),
            metadata=_as_dict(data.get("metadata")),
        )


@dataclass(frozen=True)
class EvidenceClaim:
    """A concise claim supported by one or more evidence sources."""

    text: str
    source_ids: tuple[str, ...] = ()
    confidence_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        text: str,
        *,
        source_ids: Sequence[str] = (),
        confidence_score: float = 0.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> "EvidenceClaim":
        return cls(
            text=_clean_text(text),
            source_ids=tuple(_clean_text(item) for item in source_ids if _clean_text(item)),
            confidence_score=float(confidence_score or 0.0),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source_ids": list(self.source_ids),
            "confidence_score": self.confidence_score,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceClaim":
        return cls.build(
            _clean_text(data.get("text")),
            source_ids=[str(item) for item in data.get("source_ids") or []],
            confidence_score=float(data.get("confidence_score") or 0.0),
            metadata=_as_dict(data.get("metadata")),
        )


@dataclass(frozen=True)
class EvidencePacket:
    """Stable `/ground` evidence packet.

    Runtime code may render this packet for diagnostics or pass its answer context
    to the LLM. Providers must adapt into this shape.
    """

    query: str
    normalized_query: str = ""
    profile: str = "general_reference"
    targets: tuple[str, ...] = ()
    sources: tuple[EvidenceSource, ...] = ()
    claims: tuple[EvidenceClaim, ...] = ()
    status: str = "empty"
    diagnostics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = EVIDENCE_PACKET_SCHEMA_VERSION

    @property
    def ok(self) -> bool:
        return self.status == "ok" and any(source.accepted and source.display_text() for source in self.sources)

    @classmethod
    def build(
        cls,
        *,
        query: str,
        normalized_query: str = "",
        profile: str = "general_reference",
        targets: Sequence[str] = (),
        sources: Sequence[EvidenceSource] = (),
        claims: Sequence[EvidenceClaim] = (),
        status: str | None = None,
        diagnostics: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "EvidencePacket":
        cleaned_sources = tuple(sources)
        resolved_status = status or ("ok" if any(source.accepted and source.display_text() for source in cleaned_sources) else "empty")
        return cls(
            query=_clean_text(query),
            normalized_query=_clean_text(normalized_query) or _clean_text(query),
            profile=_clean_text(profile) or "general_reference",
            targets=tuple(_clean_text(target) for target in targets if _clean_text(target)),
            sources=cleaned_sources,
            claims=tuple(claims),
            status=_clean_text(resolved_status) or "empty",
            diagnostics=dict(diagnostics or {}),
            metadata=dict(metadata or {}),
        )

    def accepted_sources(self) -> tuple[EvidenceSource, ...]:
        return tuple(source for source in self.sources if source.accepted and source.display_text())

    def render_answer_context(self, *, max_chars_per_source: int = 1800) -> str:
        lines = [
            "Grounded evidence packet:",
            f"Schema: {self.schema_version}",
            f"Query: {self.query}",
            f"Normalized query: {self.normalized_query}",
            f"Profile: {self.profile}",
        ]
        if self.targets:
            lines.append(f"Targets: {', '.join(self.targets)}")
        lines.append("")
        for idx, source in enumerate(self.accepted_sources(), 1):
            text = source.display_text()
            if len(text) > max_chars_per_source:
                text = text[:max_chars_per_source].rstrip() + "…"
            lines.extend(
                [
                    f"Source {idx}: {source.title or source.provider}",
                    f"Provider: {source.provider}",
                    f"URL: {source.url}",
                    f"Evidence: {text}",
                    "",
                ]
            )
        if self.claims:
            lines.append("Claims:")
            for claim in self.claims:
                lines.append(f"- {claim.text} [{', '.join(claim.source_ids)}]")
        return "\n".join(lines).rstrip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "query": self.query,
            "normalized_query": self.normalized_query,
            "profile": self.profile,
            "targets": list(self.targets),
            "sources": [source.to_dict() for source in self.sources],
            "claims": [claim.to_dict() for claim in self.claims],
            "status": self.status,
            "diagnostics": dict(self.diagnostics),
            "metadata": dict(self.metadata),
            "ok": self.ok,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidencePacket":
        return cls.build(
            query=_clean_text(data.get("query")),
            normalized_query=_clean_text(data.get("normalized_query")),
            profile=_clean_text(data.get("profile")) or "general_reference",
            targets=[str(item) for item in data.get("targets") or []],
            sources=[EvidenceSource.from_dict(item) for item in data.get("sources") or [] if isinstance(item, Mapping)],
            claims=[EvidenceClaim.from_dict(item) for item in data.get("claims") or [] if isinstance(item, Mapping)],
            status=_clean_text(data.get("status")) or None,
            diagnostics=_as_dict(data.get("diagnostics")),
            metadata=_as_dict(data.get("metadata")),
        )

    @classmethod
    def from_legacy_grounding_payload(cls, payload: Mapping[str, Any]) -> "EvidencePacket":
        """Adapt the current dict-based grounding payload into EvidencePacket v1."""
        grounding_query = _as_dict(payload.get("grounding_query"))
        query = _clean_text(grounding_query.get("original") or grounding_query.get("query") or payload.get("query"))
        normalized_query = _clean_text(grounding_query.get("wikipedia_query") or grounding_query.get("web_query") or query)
        profile = _clean_text(grounding_query.get("profile")) or "general_reference"
        sources: list[EvidenceSource] = []

        wiki = _as_dict(payload.get("wikipedia"))
        if wiki.get("ok"):
            summary = wiki.get("summary")
            summary_dict = _as_dict(summary)
            title = _clean_text(summary_dict.get("title") or wiki.get("title") or "Wikipedia")
            url = _clean_text(summary_dict.get("url") or wiki.get("url"))
            extract = _clean_text(summary_dict.get("extract") or summary_dict.get("summary") or wiki.get("extract") or (summary if isinstance(summary, str) else ""))
            if extract:
                sources.append(
                    EvidenceSource.build(
                        provider=_clean_text(wiki.get("source")) or "wikipedia",
                        title=title,
                        url=url,
                        text=extract,
                        source_type="encyclopedia",
                        confidence_score=float(_as_dict(wiki.get("source_confidence")).get("score") or 1.0),
                        accepted=True,
                        metadata={"legacy_key": "wikipedia"},
                    )
                )

        page = _as_dict(payload.get("page"))
        if page and not page.get("fetch_error"):
            text = _clean_text(page.get("text") or page.get("extract"))
            if text:
                sources.append(
                    EvidenceSource.build(
                        provider=_clean_text(page.get("provider")) or "page_fetch",
                        title=_clean_text(page.get("title")),
                        url=_clean_text(page.get("url")),
                        text=text,
                        source_type="web_page",
                        confidence_score=float(_as_dict(page.get("source_confidence")).get("score") or 0.5),
                        accepted=True,
                        metadata={"legacy_key": "page"},
                    )
                )

        multi = _as_dict(payload.get("multi_source"))
        targets = tuple(_clean_text(item) for item in multi.get("conjunction_targets") or [] if _clean_text(item))
        for item in multi.get("pages") or []:
            if not isinstance(item, Mapping) or item.get("fetch_error"):
                continue
            text = _clean_text(item.get("text") or item.get("extract"))
            if text:
                sources.append(
                    EvidenceSource.build(
                        provider=_clean_text(item.get("provider")) or "multi_source",
                        title=_clean_text(item.get("title")),
                        url=_clean_text(item.get("url")),
                        text=text,
                        source_type="web_page",
                        confidence_score=float(_as_dict(item.get("source_confidence")).get("score") or 0.5),
                        accepted=True,
                        metadata={"legacy_key": "multi_source.pages"},
                    )
                )

        status = "ok" if payload.get("ok") and sources else "empty"
        return cls.build(
            query=query,
            normalized_query=normalized_query,
            profile=profile,
            targets=targets,
            sources=sources,
            status=status,
            diagnostics={"legacy_ok": bool(payload.get("ok")), "legacy_response": _clean_text(payload.get("response"))},
            metadata={"source": "legacy_grounding_payload"},
        )
