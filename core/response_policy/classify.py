"""Top-level deterministic response policy classification."""
from __future__ import annotations

from .guardrails import build_lyrics_refusal_decision, build_non_music_allow_decision, apply_response_guardrails
from .music import is_lyrics_request, is_music_reference_query, resolve_music_entity
from .models import ResponsePolicyDecision


def classify_response_policy(query: str) -> ResponsePolicyDecision:
    normalized_query = _normalize_query(query)
    if not normalized_query:
        return build_non_music_allow_decision("")

    if not is_music_reference_query(normalized_query):
        return build_non_music_allow_decision(normalized_query)

    resolution = resolve_music_entity(normalized_query)
    if resolution.reversed_phrasing:
        return apply_response_guardrails(normalized_query, resolution)

    if is_lyrics_request(normalized_query):
        return build_lyrics_refusal_decision(normalized_query, resolution=resolution)

    return apply_response_guardrails(normalized_query, resolution)


def _normalize_query(query: str) -> str:
    return " ".join(str(query or "").split())
