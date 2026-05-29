"""Deterministic response policy data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EntityCandidate:
    kind: str
    name: str
    artist: str = ""
    confidence: float = 0.0
    source: str = "deterministic-fixture"
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "artist": self.artist,
            "confidence": self.confidence,
            "source": self.source,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class MusicEntityResolution:
    normalized_query: str
    song_title: str = ""
    artist_name: str = ""
    candidates: tuple[EntityCandidate, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    reversed_phrasing: bool = False
    ambiguous: bool = False
    requires_source_confirmation: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_query": self.normalized_query,
            "song_title": self.song_title,
            "artist_name": self.artist_name,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "confidence": self.confidence,
            "reversed_phrasing": self.reversed_phrasing,
            "ambiguous": self.ambiguous,
            "requires_source_confirmation": self.requires_source_confirmation,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ResponsePolicyDecision:
    action: str
    reason: str
    confidence: float
    normalized_query: str
    entity_candidates: tuple[EntityCandidate, ...] = field(default_factory=tuple)
    refusal_text: str = ""
    clarification_question: str = ""
    safety_notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "confidence": self.confidence,
            "normalized_query": self.normalized_query,
            "entity_candidates": [candidate.to_dict() for candidate in self.entity_candidates],
            "refusal_text": self.refusal_text,
            "clarification_question": self.clarification_question,
            "safety_notes": list(self.safety_notes),
        }
