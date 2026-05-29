"""Safe local runtime state for `/llm` model selection.

This module stores only the selected provider and model ID in a local runtime
JSON file. It does not store secrets, prompts, provider payloads, or API keys.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


DEFAULT_SELECTION_PATH = Path("data_agent/runtime/llm_model_selection.json")
SELECTION_SCHEMA_VERSION = "llm-model-selection-v1"


@dataclass(frozen=True)
class LlmModelSelection:
    provider: str
    model_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
        }


@dataclass(frozen=True)
class ParsedModelTarget:
    provider: str
    model_id: str
    provider_explicit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "provider_explicit": self.provider_explicit,
        }


def parse_model_target(
    raw_text: str,
    *,
    default_provider: str,
    known_providers: Sequence[str],
) -> ParsedModelTarget:
    """Parse a model selector while preserving local IDs that contain colons."""

    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("usage: /llm choose <model>")

    provider = str(default_provider or "").strip()
    model_id = text
    provider_explicit = False

    if ":" in text:
        prefix, remainder = text.split(":", 1)
        prefix = prefix.strip()
        remainder = remainder.strip()
        if prefix and remainder and prefix in set(known_providers):
            provider = prefix
            model_id = remainder
            provider_explicit = True

    if not provider:
        raise ValueError("no provider is available for model selection")
    if not model_id:
        raise ValueError("usage: /llm choose <model>")

    return ParsedModelTarget(
        provider=provider,
        model_id=model_id,
        provider_explicit=provider_explicit,
    )


def load_selection(path: Path | str = DEFAULT_SELECTION_PATH) -> Optional[LlmModelSelection]:
    """Load the current local selection from disk."""

    selection_path = Path(path)
    if not selection_path.is_file():
        return None
    try:
        raw = json.loads(selection_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, Mapping):
        return None
    provider = str(raw.get("provider") or "").strip()
    model_id = str(raw.get("model_id") or "").strip()
    if not provider or not model_id:
        return None
    return LlmModelSelection(provider=provider, model_id=model_id)


def save_selection(selection: LlmModelSelection, path: Path | str = DEFAULT_SELECTION_PATH) -> Path:
    """Persist the current selection to disk in a small safe JSON shape."""

    selection_path = Path(path)
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SELECTION_SCHEMA_VERSION,
        "provider": selection.provider,
        "model_id": selection.model_id,
    }
    selection_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return selection_path


def clear_selection(path: Path | str = DEFAULT_SELECTION_PATH) -> bool:
    """Remove the current selection file if it exists."""

    selection_path = Path(path)
    if not selection_path.exists():
        return False
    selection_path.unlink()
    return True


def selection_status(path: Path | str = DEFAULT_SELECTION_PATH) -> Dict[str, Any]:
    """Return a JSON-friendly view of the current selection state."""

    selection_path = Path(path)
    selection = load_selection(selection_path)
    return {
        "path": str(selection_path),
        "exists": selection is not None,
        "selected": selection.to_dict() if selection else None,
    }

