"""Deterministic response policy gate helpers.

This package returns policy decisions only. It does not answer questions,
fetch sources, call models, or execute tools.
"""
from __future__ import annotations

from .classify import classify_response_policy
from .guardrails import FULL_LYRICS_REFUSAL_TEXT, apply_response_guardrails
from .models import EntityCandidate, MusicEntityResolution, ResponsePolicyDecision
from .music import is_lyrics_request, is_music_reference_query, resolve_music_entity

__all__ = [
    "EntityCandidate",
    "FULL_LYRICS_REFUSAL_TEXT",
    "MusicEntityResolution",
    "ResponsePolicyDecision",
    "apply_response_guardrails",
    "classify_response_policy",
    "is_lyrics_request",
    "is_music_reference_query",
    "resolve_music_entity",
]
