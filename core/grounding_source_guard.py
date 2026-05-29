"""Deterministic guardrails for source-backed factual answers."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping


PRIVATE_DETAIL_REFUSAL = (
    "I can’t help find or infer private contact or location details. "
    "Use official public channels if you need to contact someone."
)


@dataclass(frozen=True)
class GroundingSourceGuard:
    """Policy result for a factual grounding request."""

    allowed: bool
    status: str
    reason: str = ""
    refusal: str = ""
    categories: tuple[str, ...] = field(default_factory=tuple)
    min_accepted_sources: int = 1
    allow_snippet_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_grounding_request(text: str) -> GroundingSourceGuard:
    """Classify grounding risk before source collection or answer synthesis."""

    normalized = _normalize(text)
    categories: list[str] = []

    if _asks_private_contact_or_location(normalized):
        categories.append("private_contact_or_location")
        return GroundingSourceGuard(
            allowed=False,
            status="blocked",
            reason="private contact/location request",
            refusal=PRIVATE_DETAIL_REFUSAL,
            categories=tuple(categories),
            min_accepted_sources=2,
            allow_snippet_only=False,
        )

    min_sources = 1
    if _asks_workplace_claim(normalized):
        categories.append("workplace_claim")
        min_sources = 2
    if _looks_like_vague_person_identity(normalized):
        categories.append("vague_person_identity")
        min_sources = max(min_sources, 2)

    return GroundingSourceGuard(
        allowed=True,
        status="strict" if categories else "standard",
        reason=", ".join(categories),
        categories=tuple(categories),
        min_accepted_sources=min_sources,
        allow_snippet_only=False,
    )


def count_accepted_sources(grounding_payload: Mapping[str, Any]) -> int:
    """Count accepted source pages/search results in a grounding payload."""

    count = 0
    seen_urls: set[str] = set()

    wikipedia = grounding_payload.get("wikipedia")
    if isinstance(wikipedia, Mapping) and wikipedia.get("ok"):
        confidence = wikipedia.get("source_confidence")
        if not isinstance(confidence, Mapping) or confidence.get("accepted", True):
            count += 1
            summary = wikipedia.get("summary")
            if isinstance(summary, Mapping):
                url = str(summary.get("url") or "").strip()
                if url:
                    seen_urls.add(url)

    page = grounding_payload.get("page")
    if isinstance(page, Mapping) and _accepted_page(page):
        url = str(page.get("url") or "").strip()
        if not url or url not in seen_urls:
            count += 1
            if url:
                seen_urls.add(url)

    multi = grounding_payload.get("multi_source")
    if isinstance(multi, Mapping):
        for item in multi.get("pages") or []:
            if isinstance(item, Mapping) and _accepted_page(item):
                url = str(item.get("url") or "").strip()
                if not url or url not in seen_urls:
                    count += 1
                    if url:
                        seen_urls.add(url)

    return count


def grounding_supports_answer(
    guard: GroundingSourceGuard,
    grounding_payload: Mapping[str, Any],
    *,
    strong_grounding: bool,
    weak_grounding: bool,
) -> bool:
    """Return whether collected evidence is strong enough for this request."""

    if not guard.allowed:
        return False
    if strong_grounding and count_accepted_sources(grounding_payload) >= guard.min_accepted_sources:
        return True
    return bool(guard.allow_snippet_only and weak_grounding)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _asks_private_contact_or_location(text: str) -> bool:
    contact_patterns = (
        r"\b(?:phone|phone number|mobile|cell|cellphone|email|e-mail|personal email|contact info|contact information)\b",
        r"\b(?:home address|address|street address|where does .+ live|where is .+ house|where is .+ home)\b",
    )
    return any(re.search(pattern, text) for pattern in contact_patterns)


def _asks_workplace_claim(text: str) -> bool:
    return bool(
        re.search(r"\bwhere does .+ work\b", text)
        or re.search(r"\b(?:who employs|employer of|workplace of|current employer)\b", text)
        or re.search(r"\b(?:does|did|is|was) .+ work (?:at|for|with)\b", text)
    )


def _looks_like_vague_person_identity(text: str) -> bool:
    match = re.search(r"^\s*(?:who is|who was|tell me about|identify)\s+([a-z][a-z.'-]+(?:\s+[a-z][a-z.'-]+){1,3})\??$", text)
    if not match:
        return False
    subject = match.group(1)
    if any(marker in subject for marker in (" company", " university", " band", " movie", " film", " book")):
        return False
    if re.search(r"\b(?:wikipedia|imdb|official|github|linkedin|profile)\b", text):
        return False
    return True


def _accepted_page(page: Mapping[str, Any]) -> bool:
    if page.get("fetch_error"):
        return False
    confidence = page.get("source_confidence")
    return not isinstance(confidence, Mapping) or confidence.get("accepted", True)
