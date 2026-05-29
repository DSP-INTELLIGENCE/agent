"""Provider-neutral LLM model catalog helpers.

This module normalizes model records returned by providers such as Open WebUI
into small, provider-neutral records that front doors and selectors can reason
about.  It intentionally does not contain a hardcoded list of available models;
providers remain the source of truth for what exists at runtime.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


CHAT_CAPABILITY = "chat"
UNKNOWN_CAPABILITY = "unknown"

_NON_CHAT_PATTERNS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("image", ("image", "vision-generate")),
    ("audio", ("audio", "tts", "speech")),
    ("transcription", ("transcribe", "transcription", "stt", "diarize")),
    ("realtime", ("realtime", "real-time")),
    ("moderation", ("moderation", "moderate")),
    ("computer_use", ("computer-use", "computer_use")),
    ("search", ("search",)),
    ("video", ("sora", "video")),
    ("embedding", ("embedding", "embed")),
)

_CHAT_HINT_PATTERNS: Tuple[str, ...] = (
    "chat",
    "gpt-",
    "o1",
    "o3",
    "o4",
    "qwen",
    "llama",
    "mistral",
    "gemma",
    "codellama",
)

_CODE_HINT_PATTERNS: Tuple[str, ...] = (
    "codex",
    "code",
    "coder",
    "codellama",
)


@dataclass(frozen=True)
class ModelRecord:
    """Normalized provider-neutral model record."""

    provider: str
    model_id: str
    display_name: str
    capabilities: Tuple[str, ...] = field(default_factory=tuple)
    family: str = UNKNOWN_CAPABILITY
    source_kind: Optional[str] = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_chat_capable(self) -> bool:
        return CHAT_CAPABILITY in self.capabilities

    def to_dict(self, *, include_raw: bool = False) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "provider": self.provider,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "capabilities": list(self.capabilities),
            "family": self.family,
            "source_kind": self.source_kind,
            "is_chat_capable": self.is_chat_capable,
        }
        if include_raw:
            data["raw"] = dict(self.raw)
        return data


@dataclass(frozen=True)
class ModelCatalog:
    """A normalized model catalog from one or more providers."""

    records: Tuple[ModelRecord, ...]

    def filter(
        self,
        *,
        provider: Optional[str] = None,
        capability: Optional[str] = None,
        chat_only: bool = False,
    ) -> "ModelCatalog":
        records: Iterable[ModelRecord] = self.records
        if provider:
            records = (record for record in records if record.provider == provider)
        if capability:
            records = (record for record in records if capability in record.capabilities)
        if chat_only:
            records = (record for record in records if record.is_chat_capable)
        return ModelCatalog(tuple(records))

    def to_dict(self, *, include_raw: bool = False) -> Dict[str, Any]:
        return {
            "count": len(self.records),
            "records": [record.to_dict(include_raw=include_raw) for record in self.records],
        }


def normalize_model_record(provider: str, raw_record: Mapping[str, Any]) -> ModelRecord:
    """Normalize one provider-specific model object.

    The provider remains the source of truth.  This function only extracts a
    stable identifier/display name and classifies likely capabilities from
    provider metadata and naming patterns.
    """

    model_id = _coerce_text(raw_record.get("id") or raw_record.get("model") or raw_record.get("name"))
    display_name = _coerce_text(raw_record.get("name") or model_id)
    if not model_id:
        model_id = display_name or "unknown"
    if not display_name:
        display_name = model_id

    source_kind = _coerce_text(
        raw_record.get("connection_type")
        or raw_record.get("object")
        or _nested_get(raw_record, ("openai", "connection_type"))
    ) or None

    capabilities = classify_model_capabilities(model_id, raw_record)
    family = _primary_family(capabilities)

    return ModelRecord(
        provider=provider,
        model_id=model_id,
        display_name=display_name,
        capabilities=capabilities,
        family=family,
        source_kind=source_kind,
        raw=dict(raw_record),
    )


def normalize_model_records(provider: str, raw_records: Sequence[Mapping[str, Any]]) -> ModelCatalog:
    """Normalize provider model records into a catalog."""

    records = [normalize_model_record(provider, raw_record) for raw_record in raw_records]
    records.sort(key=lambda record: (record.provider, record.family, record.model_id))
    return ModelCatalog(tuple(records))


def normalize_open_webui_models(payload: Mapping[str, Any], *, provider: str = "open_webui") -> ModelCatalog:
    """Normalize an Open WebUI/OpenAI-compatible model-list payload.

    Accepts either an OpenAI-style object with ``data`` or a direct list under
    ``models`` for compatibility with local probes and tests.
    """

    raw_records = payload.get("data")
    if raw_records is None:
        raw_records = payload.get("models")
    if raw_records is None:
        raw_records = []
    if not isinstance(raw_records, list):
        raise ValueError("model payload must contain a list under 'data' or 'models'")
    return normalize_model_records(provider, raw_records)


def classify_model_capabilities(model_id: str, raw_record: Optional[Mapping[str, Any]] = None) -> Tuple[str, ...]:
    """Classify likely model capabilities from metadata and naming patterns.

    This is intentionally heuristic.  It does not decide whether a model exists
    or is usable; it only helps `/llm models` and selectors group discovered
    provider records.
    """

    raw_record = raw_record or {}
    tokens = _classification_text(model_id, raw_record)
    capabilities: List[str] = []

    for capability, patterns in _NON_CHAT_PATTERNS:
        if any(pattern in tokens for pattern in patterns):
            capabilities.append(capability)

    if any(pattern in tokens for pattern in _CODE_HINT_PATTERNS):
        capabilities.append("code")

    if not capabilities and any(pattern in tokens for pattern in _CHAT_HINT_PATTERNS):
        capabilities.append(CHAT_CAPABILITY)

    if "chat" in tokens and CHAT_CAPABILITY not in capabilities:
        capabilities.append(CHAT_CAPABILITY)

    if not capabilities:
        capabilities.append(UNKNOWN_CAPABILITY)

    return tuple(_dedupe_preserve_order(capabilities))


def _primary_family(capabilities: Sequence[str]) -> str:
    if not capabilities:
        return UNKNOWN_CAPABILITY
    if CHAT_CAPABILITY in capabilities:
        return CHAT_CAPABILITY
    return capabilities[0]


def _classification_text(model_id: str, raw_record: Mapping[str, Any]) -> str:
    fields: List[str] = [model_id]
    for key in ("name", "object", "owned_by", "connection_type"):
        value = raw_record.get(key)
        if isinstance(value, str):
            fields.append(value)
    tags = raw_record.get("tags")
    if isinstance(tags, list):
        fields.extend(str(tag) for tag in tags)
    openai = raw_record.get("openai")
    if isinstance(openai, Mapping):
        for key in ("id", "object", "owned_by"):
            value = openai.get(key)
            if isinstance(value, str):
                fields.append(value)
    return " ".join(fields).lower()


def _dedupe_preserve_order(items: Sequence[str]) -> Tuple[str, ...]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _nested_get(mapping: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize LLM model records into a provider-neutral catalog.")
    parser.add_argument("--provider", default="open_webui", help="Provider name for records read from stdin")
    parser.add_argument("--include-raw", action="store_true", help="Include raw provider model records in output")
    parser.add_argument("--chat-only", action="store_true", help="Show only chat-capable records")
    args = parser.parse_args(argv)

    payload = json.load(__import__("sys").stdin)
    catalog = normalize_open_webui_models(payload, provider=args.provider)
    if args.chat_only:
        catalog = catalog.filter(chat_only=True)
    print(json.dumps(catalog.to_dict(include_raw=args.include_raw), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
