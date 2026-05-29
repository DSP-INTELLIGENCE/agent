"""Decision construction and guardrail enforcement for response policy."""
from __future__ import annotations

from .models import EntityCandidate, MusicEntityResolution, ResponsePolicyDecision


FULL_LYRICS_REFUSAL_TEXT = (
    "I can’t provide full copyrighted lyrics, but I can summarize the song or "
    "discuss a short excerpt."
)


def apply_response_guardrails(query: str, resolution: MusicEntityResolution | None = None) -> ResponsePolicyDecision:
    normalized_query = _normalize_query(query)
    resolved = resolution or MusicEntityResolution(normalized_query=normalized_query)

    if resolved.reversed_phrasing and resolved.candidates:
        candidate = resolved.candidates[0]
        question = _corrected_question(candidate)
        return ResponsePolicyDecision(
            action="correct_then_answer",
            reason="reversed song/artist phrasing",
            confidence=max(resolved.confidence, candidate.confidence),
            normalized_query=normalized_query,
            entity_candidates=resolved.candidates,
            clarification_question=question,
            safety_notes=("correct the song/artist order before answering",),
        )

    if resolved.requires_source_confirmation:
        return ResponsePolicyDecision(
            action="needs_source_confirmation",
            reason="music reference needs source confirmation",
            confidence=max(0.0, resolved.confidence),
            normalized_query=normalized_query,
            entity_candidates=resolved.candidates,
            safety_notes=("confirm the source before answering",),
        )

    if resolved.ambiguous or resolved.confidence < 0.7:
        question = _clarify_question(resolved)
        reason = "ambiguous or low-confidence music entity match" if resolved.candidates else "low-confidence or unresolved music entity"
        return ResponsePolicyDecision(
            action="clarify",
            reason=reason,
            confidence=max(0.0, resolved.confidence),
            normalized_query=normalized_query,
            entity_candidates=resolved.candidates,
            clarification_question=question,
            safety_notes=("ask for clarification instead of hallucinating a factual answer",),
        )

    return ResponsePolicyDecision(
        action="allow",
        reason="deterministic music entity resolution",
        confidence=max(0.0, resolved.confidence),
        normalized_query=normalized_query,
        entity_candidates=resolved.candidates,
        safety_notes=("source confirmation may still be needed before a final answer",) if resolved.candidates else (),
    )


def build_lyrics_refusal_decision(query: str, *, resolution: MusicEntityResolution | None = None) -> ResponsePolicyDecision:
    normalized_query = _normalize_query(query)
    resolved = resolution or MusicEntityResolution(normalized_query=normalized_query)
    return ResponsePolicyDecision(
        action="refuse",
        reason="full copyrighted lyrics request",
        confidence=max(0.0, resolved.confidence if resolution else 0.99),
        normalized_query=normalized_query,
        entity_candidates=resolved.candidates,
        refusal_text=FULL_LYRICS_REFUSAL_TEXT,
        safety_notes=("do not output full copyrighted lyrics",),
    )


def build_non_music_allow_decision(query: str) -> ResponsePolicyDecision:
    normalized_query = _normalize_query(query)
    return ResponsePolicyDecision(
        action="allow",
        reason="non-music prompt",
        confidence=1.0,
        normalized_query=normalized_query,
    )


def _clarify_question(resolution: MusicEntityResolution) -> str:
    if resolution.song_title and resolution.artist_name:
        return f"Did you mean '{resolution.song_title}' by {resolution.artist_name}?"
    if resolution.song_title:
        return f"Did you mean '{resolution.song_title}'?"
    return "Can you clarify which song or artist you mean?"


def _corrected_question(candidate: EntityCandidate) -> str:
    if candidate.artist:
        return f"Did you mean '{candidate.name}' by {candidate.artist}?"
    return f"Did you mean '{candidate.name}'?"


def _normalize_query(query: str) -> str:
    return " ".join(str(query or "").split())
