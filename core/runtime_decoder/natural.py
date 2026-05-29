"""Deterministic natural-input classification into runtime InputSpec models."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .models import AgentTaskInputSpec, FactualAnswerSpec, InputSpec, UnknownInputSpec


_TASK_JSON_KEYS = {"kind", "task", "goal", "input", "agent", "spec", "version"}
_TASK_HEADINGS = {
    "task",
    "goal",
    "scope",
    "implement",
    "behavior",
    "tests",
    "docs",
    "verify",
    "patch flow",
}
_FACTUAL_STARTERS = (
    "who ",
    "what ",
    "when ",
    "where ",
    "why ",
    "how ",
    "which ",
    "whom ",
    "whose ",
)
_AMBIGUOUS_CONTEXT_WORDS = {
    "this",
    "that",
    "these",
    "those",
    "it",
    "they",
    "them",
    "something",
    "someone",
    "somebody",
    "here",
    "there",
}


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").split())


def classify_natural_input(text: str) -> InputSpec:
    raw_text = str(text or "")
    normalized_text = normalize_text(raw_text)

    if not normalized_text:
        return UnknownInputSpec(
            kind="unknown",
            raw_text=raw_text,
            normalized_text="",
            reason="empty input",
        )

    json_spec = _classify_json_like(raw_text, normalized_text)
    if json_spec is not None:
        return json_spec

    task_spec = _classify_heading_task(raw_text, normalized_text)
    if task_spec is not None:
        return task_spec

    factual_spec = _classify_factual_question(raw_text, normalized_text)
    if factual_spec is not None:
        return factual_spec

    return UnknownInputSpec(
        kind="unknown",
        raw_text=raw_text,
        normalized_text=normalized_text,
        reason="unrecognized input",
    )


def _classify_json_like(raw_text: str, normalized_text: str) -> InputSpec | None:
    stripped = raw_text.lstrip()
    if not stripped.startswith("{"):
        return None
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return UnknownInputSpec(
            kind="unknown",
            raw_text=raw_text,
            normalized_text=normalized_text,
            reason="invalid json input",
        )
    if not isinstance(parsed, Mapping):
        return UnknownInputSpec(
            kind="unknown",
            raw_text=raw_text,
            normalized_text=normalized_text,
            reason="unrecognized json input",
        )
    if not _TASK_JSON_KEYS.intersection(parsed.keys()):
        return UnknownInputSpec(
            kind="unknown",
            raw_text=raw_text,
            normalized_text=normalized_text,
            reason="unrecognized json input",
        )
    return _json_to_task_spec(raw_text, normalized_text, parsed)


def _json_to_task_spec(raw_text: str, normalized_text: str, payload: Mapping[str, Any]) -> AgentTaskInputSpec:
    title = _string_from_json_value(
        payload.get("task")
        or payload.get("agent")
        or payload.get("spec")
        or payload.get("kind")
        or payload.get("version")
        or "JSON task"
    )
    summary = _string_from_json_value(payload.get("goal") or payload.get("input") or "")
    notes = []
    for key in sorted(payload.keys()):
        if key in {"task", "goal", "input"}:
            continue
        notes.append(f"{key}={json.dumps(payload[key], sort_keys=True, separators=(',', ':'))}")
    metadata: dict[str, Any] = {"source": "json"}
    if "kind" in payload:
        metadata["kind"] = _string_from_json_value(payload.get("kind"))
    return AgentTaskInputSpec(
        kind="agent_task_input",
        raw_text=raw_text,
        normalized_text=normalized_text,
        metadata=metadata,
        title=title,
        summary=summary,
        notes=tuple(notes),
    )


def _classify_heading_task(raw_text: str, normalized_text: str) -> AgentTaskInputSpec | None:
    lines = [line.rstrip() for line in raw_text.splitlines()]
    if not any(_looks_like_heading(line) for line in lines):
        return None
    sections = _parse_headings(lines)
    if not sections:
        return None

    title = _first_nonempty(sections.get("task", ())) or "Task"
    summary = _first_nonempty(sections.get("goal", ()))
    notes: list[str] = []
    for heading in ("scope", "implement", "behavior", "tests", "docs", "verify", "patch flow"):
        for item in sections.get(heading, ()):
            notes.append(f"{heading}: {item}")
    for item in sections.get("_unmatched", ()):
        notes.append(item)
    return AgentTaskInputSpec(
        kind="agent_task_input",
        raw_text=raw_text,
        normalized_text=normalized_text,
        metadata={"source": "markdown"},
        title=title,
        summary=summary,
        notes=tuple(notes),
    )


def _parse_headings(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "_unmatched"
    for line in lines:
        match = re.match(r"^\s*([A-Za-z][A-Za-z ]*):\s*(.*)$", line)
        if match:
            heading = match.group(1).strip().lower()
            current = heading if heading in _TASK_HEADINGS else "_unmatched"
            sections.setdefault(current, [])
            if match.group(2).strip():
                sections[current].append(match.group(2).strip())
            continue
        if line.strip():
            sections.setdefault(current, []).append(line.strip())
    return sections


def _looks_like_heading(line: str) -> bool:
    return bool(re.match(r"^\s*([A-Za-z][A-Za-z ]*):\s*(.*)$", line))


def _first_nonempty(values: list[str] | tuple[str, ...] | None) -> str:
    if not values:
        return ""
    for value in values:
        cleaned = _string_from_json_value(value)
        if cleaned:
            return cleaned
    return ""


def _classify_factual_question(raw_text: str, normalized_text: str) -> FactualAnswerSpec | None:
    lower = normalized_text.lower()
    if not _looks_like_factual_question(lower):
        return None
    metadata: dict[str, Any] = {}
    if _requires_context(lower):
        metadata["requires_context"] = True
    topic = _guess_factual_topic(lower)
    return FactualAnswerSpec(
        kind="factual_answer",
        raw_text=raw_text,
        normalized_text=normalized_text,
        metadata=metadata,
        requires_grounding=True,
        requires_policy=True,
        topic=topic,
    )


def _looks_like_factual_question(lower_text: str) -> bool:
    if "?" in lower_text:
        return True
    return lower_text.startswith(_FACTUAL_STARTERS)


def _requires_context(lower_text: str) -> bool:
    words = set(re.findall(r"[a-z0-9']+", lower_text))
    return any(word in words for word in _AMBIGUOUS_CONTEXT_WORDS)


def _guess_factual_topic(lower_text: str) -> str:
    if "quantum" in lower_text:
        return "science"
    if "song" in lower_text or "lyrics" in lower_text or "wrote" in lower_text:
        return "music"
    return ""


def _string_from_json_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()
