"""Inspect-only `/llm` front-door helpers.

This module keeps `/llm` in the batch runner on a safe, deterministic path.
It reports local configuration and preset guidance only. It does not download
models, restart services, mutate runtime state, or call the switch-backed
runtime resolver.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
import shlex
from pathlib import Path
from typing import Mapping
from urllib import error, request

from core.llm_config import default_llm_config
from core.llm_provider_config import provider_config_status


VALID_LLM_PRESETS = {"coding", "general", "vision"}
DEFAULT_OLLAMA_HEALTH_TIMEOUT_SECONDS = 2.0
DEFAULT_LLM_PRESET_CONFIG_PATH = Path("data_agent/runtime/llm_preset_config.json")
LLM_PRESET_SCHEMA_VERSION = "llm-preset-config-v1"
_LLM_PRESET_DETAILS = {
    "coding": {
        "recommended_models": ("qwen2.5-coder", "deepseek-coder"),
        "apply_model": "qwen2.5-coder:14b",
        "settings": (
            ("provider", "ollama_native"),
            ("temperature", 0.2),
            ("top_p", 0.9),
            ("repeat_penalty", 1.05),
        ),
        "notes": (
            "inspect-only guidance for code-focused local models",
            "no automatic model downloads or runtime mutation",
        ),
    },
    "general": {
        "recommended_models": ("llama3", "qwen2.5"),
        "apply_model": "llama3:8b",
        "settings": (
            ("provider", "ollama_native"),
            ("temperature", 0.7),
            ("top_p", 0.9),
        ),
        "notes": (
            "general-purpose local chat and reasoning lane",
            "no automatic model downloads or runtime mutation",
        ),
    },
    "vision": {
        "recommended_models": ("llava", "bakllava"),
        "apply_model": "qwen2.5vl:7b",
        "settings": (
            ("provider", "ollama_native"),
            ("temperature", 0.2),
            ("top_p", 0.9),
        ),
        "notes": (
            "vision-capable local models only",
            "no automatic model downloads or runtime mutation",
        ),
    },
}


@dataclass(frozen=True)
class LlmFrontdoorCommand:
    action: str
    preset: str | None = None
    dry_run: bool = False
    write: bool = False
    confirm: bool = False


class LlmFrontdoorError(ValueError):
    pass


def parse_llm_command(text: str) -> LlmFrontdoorCommand:
    parts = shlex.split(str(text or "").strip())

    if not parts:
        raise LlmFrontdoorError("empty /llm command")

    front = parts[0].lower()
    if front not in {"/llm", "llm"}:
        raise LlmFrontdoorError("expected /llm front door")

    action = parts[1].lower() if len(parts) > 1 else "status"
    if action in {"help", "--help", "-h"}:
        raise LlmFrontdoorError("usage: /llm <status|preset|apply> [name]")

    if action == "status":
        if len(parts) != 2 and len(parts) != 1:
            raise LlmFrontdoorError("usage: /llm status")
        return LlmFrontdoorCommand(action="status")

    if action == "preset":
        if len(parts) != 3:
            raise LlmFrontdoorError("usage: /llm preset <coding|general|vision>")
        return LlmFrontdoorCommand(action="preset", preset=parts[2].strip().lower())

    if action == "apply":
        if len(parts) < 3:
            raise LlmFrontdoorError("usage: /llm apply <coding|general|vision> [--dry-run|--write --confirm]")

        preset = parts[2].strip().lower()
        flag_texts = [part.strip().lower() for part in parts[3:]]
        if not flag_texts:
            raise LlmFrontdoorError("safety error: /llm apply requires --dry-run or --write --confirm")

        allowed_flags = {"--dry-run", "--write", "--confirm"}
        unknown_flags = [flag for flag in flag_texts if flag not in allowed_flags]
        if unknown_flags:
            raise LlmFrontdoorError("usage: /llm apply <coding|general|vision> [--dry-run|--write --confirm]")

        flag_set = set(flag_texts)
        if "--dry-run" in flag_set:
            if flag_set != {"--dry-run"}:
                raise LlmFrontdoorError("safety error: /llm apply --dry-run cannot be combined with --write or --confirm")
            return LlmFrontdoorCommand(action="apply", preset=preset, dry_run=True)

        if flag_set == {"--write", "--confirm"}:
            return LlmFrontdoorCommand(action="apply", preset=preset, write=True, confirm=True)

        raise LlmFrontdoorError("safety error: /llm apply requires --dry-run or --write --confirm")

    raise LlmFrontdoorError(f"unknown /llm action: {action}")


def build_llm_status() -> str:
    config = default_llm_config()
    provider_status = provider_config_status()
    reachable = _ollama_reachable(config.base_url, timeout_seconds=DEFAULT_OLLAMA_HEALTH_TIMEOUT_SECONDS)
    configured = provider_status.get("configured_providers") if isinstance(provider_status, Mapping) else []
    configured_text = ", ".join(str(item) for item in configured) if configured else "none"

    lines = [
        "LLM status:",
        "  mode: inspect-only",
        f"  default_provider: {config.provider}",
        f"  default_model: {config.model}",
        f"  default_base_url: {config.base_url}",
        f"  default_timeout_seconds: {config.timeout_seconds}",
        f"  streaming: {str(config.streaming).lower()}",
        f"  configured_providers: {configured_text}",
        f"  ollama_reachable: {_bool_text(reachable)}",
        f"  ollama_health_check: GET {config.base_url.rstrip('/')}/api/tags",
        f"  ollama_health_timeout_seconds: {int(DEFAULT_OLLAMA_HEALTH_TIMEOUT_SECONDS)}",
        "  notes:",
        "    - no model downloads are performed",
        "    - no Ollama restarts are performed",
        "    - no runtime state is mutated automatically",
    ]
    return "\n".join(lines)


def build_llm_preset(name: str) -> str:
    spec = _get_preset_spec(name)
    lines = [f"LLM preset: {str(name).strip().lower()}", "  mode: inspect-only", "  recommended_models:"]
    for model in spec["recommended_models"]:
        lines.append(f"    - {model}")
    lines.append("  recommended_settings:")
    for key, value in spec["settings"]:
        lines.append(f"    - {key}: {value}")
    lines.append("  notes:")
    for note in spec["notes"]:
        lines.append(f"    - {note}")
    return "\n".join(lines)


def build_llm_apply_plan(preset: str) -> str:
    spec = _get_preset_spec(preset)
    lines = [
        "LLM apply plan:",
        f"  selected_preset: {str(preset).strip().lower()}",
        "  mode: dry-run planning only",
        f"  recommended_model: {spec['apply_model']}",
        "  provider: ollama_native",
        "  settings_that_would_change:",
    ]
    for key, value in spec["settings"]:
        if key == "provider":
            continue
        lines.append(f"    - {key}: {value}")
    lines.append("  safety_notes:")
    lines.extend(
        [
            "    - no changes applied",
            "    - no config files are written",
            "    - no model downloads are performed",
            "    - no Ollama restarts are performed",
        ]
    )
    lines.append("  exact_statement: no changes applied")
    return "\n".join(lines)


def build_llm_apply_write(preset: str, *, path: Path | str | None = None) -> str:
    spec = _get_preset_spec(preset)
    preset_name = str(preset).strip().lower()
    config_path = Path(path) if path is not None else DEFAULT_LLM_PRESET_CONFIG_PATH
    config_payload = {
        "schema_version": LLM_PRESET_SCHEMA_VERSION,
        "preset": preset_name,
        "provider": "ollama_native",
        "model": spec["apply_model"],
        "base_url": default_llm_config().base_url,
        "timeout_seconds": default_llm_config().timeout_seconds,
        "streaming": default_llm_config().streaming,
        "settings": {key: value for key, value in spec["settings"] if key != "provider"},
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "LLM apply write:",
        f"  selected_preset: {preset_name}",
        "  mode: confirmed config write",
        f"  config_file_written: {config_path}",
        f"  provider: {config_payload['provider']}",
        f"  model: {config_payload['model']}",
        "  settings_written:",
    ]
    for key, value in spec["settings"]:
        if key == "provider":
            continue
        lines.append(f"    - {key}: {value}")
    lines.extend(
        [
            "  safety_notes:",
            "    - no model download was performed",
            "    - no Ollama restart was performed",
            "    - no running session was mutated",
            "  exact_statement: config file written",
        ]
    )
    return "\n".join(lines)


def llm_help_text() -> str:
    return "\n".join(
        [
            "LLM inspect commands:",
            "  /llm status",
            "  /llm preset coding",
            "  /llm preset general",
            "  /llm preset vision",
            "  /llm apply coding --dry-run",
            "  /llm apply general --dry-run",
            "  /llm apply vision --dry-run",
            "  /llm apply coding --write --confirm",
            "  /llm apply general --write --confirm",
            "  /llm apply vision --write --confirm",
            "",
            "This lane is inspect/planning only until both --write and --confirm are supplied.",
        ]
    )


def _get_preset_spec(name: str) -> dict[str, tuple[str, ...] | str]:
    preset_name = str(name or "").strip().lower()
    if preset_name not in VALID_LLM_PRESETS:
        raise LlmFrontdoorError(f"unknown /llm preset: {name}")
    return _LLM_PRESET_DETAILS[preset_name]


def _ollama_reachable(base_url: str, *, timeout_seconds: float) -> bool:
    url = base_url.rstrip("/") + "/api/tags"
    req = request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            return 200 <= int(getattr(response, "status", 0)) < 300
    except (error.URLError, error.HTTPError, TimeoutError, OSError, ValueError):
        return False


def _bool_text(value: bool) -> str:
    return "yes" if bool(value) else "no"
