"""LLM provider configuration loading and safe diagnostics.

This module is the first provider-config layer for the `/llm` front door.
It reads environment variables and reports provider readiness without making
network calls, listing live models, storing selections, or exposing secrets.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence


@dataclass(frozen=True)
class LlmProviderSpec:
    """Static provider config contract.

    The spec names environment variables only.  It does not contain model names,
    tokens, or runtime selections.
    """

    name: str
    kind: str
    base_url_env: Optional[str] = None
    api_key_env: Optional[str] = None
    requires_base_url: bool = False
    requires_api_key: bool = False
    notes: Sequence[str] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "base_url_env": self.base_url_env,
            "api_key_env": self.api_key_env,
            "requires_base_url": self.requires_base_url,
            "requires_api_key": self.requires_api_key,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class LlmProviderConfig:
    """Resolved provider config status with secret-safe fields only."""

    spec: LlmProviderSpec
    base_url: Optional[str] = None
    api_key_present: bool = False
    missing: Sequence[str] = field(default_factory=tuple)

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def kind(self) -> str:
        return self.spec.kind

    @property
    def configured(self) -> bool:
        return not self.missing

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "configured": self.configured,
            "base_url": self.base_url,
            "base_url_env": self.spec.base_url_env,
            "api_key_env": self.spec.api_key_env,
            "api_key_present": self.api_key_present,
            "missing": list(self.missing),
            "notes": list(self.spec.notes),
        }


PROVIDER_SPECS: Sequence[LlmProviderSpec] = (
    LlmProviderSpec(
        name="open_webui",
        kind="openai_compatible_proxy",
        base_url_env="OPEN_WEBUI_BASE_URL",
        api_key_env="OPEN_WEBUI_API_KEY",
        requires_base_url=True,
        requires_api_key=True,
        notes=("local Open WebUI server or compatible proxy",),
    ),
    LlmProviderSpec(
        name="ollama",
        kind="local_ollama",
        base_url_env="OLLAMA_BASE_URL",
        requires_base_url=True,
        requires_api_key=False,
        notes=("local Ollama server",),
    ),
    LlmProviderSpec(
        name="openai_compatible",
        kind="openai_compatible_endpoint",
        base_url_env="OPENAI_COMPATIBLE_BASE_URL",
        api_key_env="OPENAI_COMPATIBLE_API_KEY",
        requires_base_url=True,
        requires_api_key=True,
        notes=("generic OpenAI-compatible endpoint",),
    ),
    LlmProviderSpec(
        name="builtin",
        kind="fallback_builtin",
        requires_base_url=False,
        requires_api_key=False,
        notes=("local non-provider fallback path; no external service configured",),
    ),
)


def load_llm_provider_configs(
    env: Optional[Mapping[str, str]] = None,
    *,
    specs: Sequence[LlmProviderSpec] = PROVIDER_SPECS,
) -> Dict[str, LlmProviderConfig]:
    """Resolve provider config from environment variables.

    This function does not validate reachability and does not call providers.
    It only reports whether enough local configuration exists for each provider.
    """

    env_map: Mapping[str, str] = os.environ if env is None else env
    return {spec.name: _resolve_provider_config(spec, env_map) for spec in specs}


def provider_config_status(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Return secret-safe LLM provider diagnostics."""

    configs = load_llm_provider_configs(env)
    configured = [name for name, config in configs.items() if config.configured]
    return {
        "providers": {name: config.to_dict() for name, config in configs.items()},
        "configured_providers": configured,
        "notes": (
            "provider config diagnostics only; no provider/network call was made",
            "API key values are never included in diagnostics",
        ),
    }


def _resolve_provider_config(spec: LlmProviderSpec, env: Mapping[str, str]) -> LlmProviderConfig:
    base_url = _clean_env_value(env.get(spec.base_url_env)) if spec.base_url_env else None
    api_key_present = bool(_clean_env_value(env.get(spec.api_key_env))) if spec.api_key_env else False

    missing = []
    if spec.requires_base_url and not base_url:
        missing.append(spec.base_url_env or "base_url")
    if spec.requires_api_key and not api_key_present:
        missing.append(spec.api_key_env or "api_key")

    return LlmProviderConfig(
        spec=spec,
        base_url=base_url,
        api_key_present=api_key_present,
        missing=tuple(missing),
    )


def _clean_env_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Show secret-safe LLM provider config status.")
    parser.add_argument(
        "--provider",
        choices=[spec.name for spec in PROVIDER_SPECS],
        help="Limit output to one provider.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    status = provider_config_status()
    if args.provider:
        status = {
            "providers": {args.provider: status["providers"][args.provider]},
            "configured_providers": [name for name in status["configured_providers"] if name == args.provider],
            "notes": status["notes"],
        }
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
