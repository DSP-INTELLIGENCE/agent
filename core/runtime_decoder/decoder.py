"""Deterministic runtime input decoding entrypoints."""
from __future__ import annotations

from dataclasses import replace

from .models import InputSpec
from .natural import classify_natural_input
from .slash import decode_slash_command, is_slash_command


_DECODER_NAME = "runtime_decoder"
_DECODER_VERSION = "runtime_decoder.v1"


def decode_runtime_input(text: str) -> InputSpec:
    if is_slash_command(text):
        spec = decode_slash_command(text)
        return _with_trace_metadata(
            spec,
            input_family="slash",
            classification_reason="slash_command",
        )
    spec = classify_natural_input(text)
    return _with_trace_metadata(
        spec,
        input_family="natural",
        classification_reason=_classification_reason_for_natural(spec),
    )


def _with_trace_metadata(spec: InputSpec, *, input_family: str, classification_reason: str) -> InputSpec:
    metadata = dict(spec.metadata)
    metadata.update(
        {
            "decoder": _DECODER_NAME,
            "decoder_version": _DECODER_VERSION,
            "input_family": input_family,
            "classification_reason": classification_reason,
        }
    )
    return replace(spec, metadata=metadata)


def _classification_reason_for_natural(spec: InputSpec) -> str:
    reason = str(spec.metadata.get("classification_reason", "")).strip()
    if reason:
        return reason
    if spec.kind == "agent_task_input":
        source = str(spec.metadata.get("source", "")).strip().lower()
        if source == "json":
            return "json_task_like"
        if source == "markdown":
            return "markdown_task_like"
        return "markdown_task_like"
    if spec.kind == "factual_answer":
        return "factual_question_like"
    if spec.kind == "unknown":
        existing = str(spec.reason).strip().lower()
        if existing == "empty input":
            return "empty_input"
        if existing == "invalid json input":
            return "invalid_json"
        return "unrecognized_input"
    return "unrecognized_input"
