"""LLM provider configuration helpers for the agent runtime.

This module is intentionally dependency-free and side-effect free. It defines
the stable config object and command parser that a later /llm runtime branch can
wire into core/agent_runtime.py.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, Tuple


VALID_LLM_PROVIDERS = (
    "ollama_native",
    "ollama_openai",
    "openai_responses",
)

DEFAULT_LLM_PROVIDER = "ollama_native"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL = "llama3:8b"
DEFAULT_LLM_TIMEOUT_SECONDS = 60


class LLMConfigError(ValueError):
    """Raised when an LLM config command is invalid."""


@dataclass(frozen=True)
class LLMConfig:
    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    timeout_seconds: int = DEFAULT_LLM_TIMEOUT_SECONDS
    streaming: bool = False

    def validate(self) -> "LLMConfig":
        validate_provider(self.provider)
        validate_model(self.model)
        validate_base_url(self.base_url)
        validate_timeout(self.timeout_seconds)
        return self

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "streaming": bool(self.streaming),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMConfig":
        if not isinstance(data, dict):
            raise LLMConfigError("LLM config must be a dictionary.")
        cfg = cls(
            provider=str(data.get("provider", DEFAULT_LLM_PROVIDER)).strip(),
            model=str(data.get("model", DEFAULT_LLM_MODEL)).strip(),
            base_url=str(data.get("base_url", DEFAULT_OLLAMA_BASE_URL)).strip(),
            timeout_seconds=int(data.get("timeout_seconds", DEFAULT_LLM_TIMEOUT_SECONDS)),
            streaming=bool(data.get("streaming", False)),
        )
        return cfg.validate()


def default_llm_config() -> LLMConfig:
    return LLMConfig()


def validate_provider(provider: str) -> str:
    value = str(provider or "").strip()
    if value not in VALID_LLM_PROVIDERS:
        raise LLMConfigError(
            "invalid LLM provider: "
            f"{provider!r}; expected one of {', '.join(VALID_LLM_PROVIDERS)}"
        )
    return value


def validate_model(model: str) -> str:
    value = str(model or "").strip()
    if not value:
        raise LLMConfigError("LLM model cannot be empty.")
    if any(ch.isspace() for ch in value):
        raise LLMConfigError("LLM model must not contain whitespace.")
    return value


def validate_base_url(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        raise LLMConfigError("LLM base URL cannot be empty.")
    if not (value.startswith("http://") or value.startswith("https://")):
        raise LLMConfigError("LLM base URL must start with http:// or https://.")
    return value


def validate_timeout(timeout_seconds: int) -> int:
    try:
        value = int(timeout_seconds)
    except Exception as exc:
        raise LLMConfigError("LLM timeout must be an integer.") from exc
    if value < 1 or value > 600:
        raise LLMConfigError("LLM timeout must be between 1 and 600 seconds.")
    return value


def describe_llm_config(config: LLMConfig) -> str:
    data = config.validate().to_dict()
    return "\n".join(
        [
            "LLM configuration:",
            f"provider: {data['provider']}",
            f"model: {data['model']}",
            f"base_url: {data['base_url']}",
            f"timeout_seconds: {data['timeout_seconds']}",
            f"streaming: {str(data['streaming']).lower()}",
        ]
    )


def parse_bool(value: str) -> bool:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise LLMConfigError(f"invalid boolean value: {value!r}")


def tokenize_llm_command(args_text: str) -> Tuple[str, str]:
    text = str(args_text or "").strip()
    if not text:
        return "status", ""
    command, _, rest = text.partition(" ")
    return command.strip().lower(), rest.strip()


def apply_llm_command(config: LLMConfig, args_text: str) -> Tuple[LLMConfig, str]:
    """Apply a /llm subcommand to a config object.

    This function performs no I/O and makes no network calls. It is safe for
    tests and future runtime command handling.
    """

    config = config.validate()
    command, rest = tokenize_llm_command(args_text)

    if command in {"status", "show"}:
        return config, describe_llm_config(config)

    if command == "reset":
        new_config = default_llm_config()
        return new_config, "LLM configuration reset to defaults.\n" + describe_llm_config(new_config)

    if command == "provider":
        if not rest:
            raise LLMConfigError("usage: /llm provider <provider>")
        provider = validate_provider(rest)
        base_url = config.base_url
        if provider == "ollama_native" and base_url == DEFAULT_OPENAI_BASE_URL:
            base_url = DEFAULT_OLLAMA_BASE_URL
        elif provider == "openai_responses" and base_url == DEFAULT_OLLAMA_BASE_URL:
            base_url = DEFAULT_OPENAI_BASE_URL
        new_config = replace(config, provider=provider, base_url=base_url).validate()
        return new_config, f"LLM provider set to {provider}."

    if command == "model":
        if not rest:
            raise LLMConfigError("usage: /llm model <model>")
        model = validate_model(rest)
        new_config = replace(config, model=model).validate()
        return new_config, f"LLM model set to {model}."

    if command in {"base-url", "base_url", "url"}:
        if not rest:
            raise LLMConfigError("usage: /llm base-url <url>")
        base_url = validate_base_url(rest)
        new_config = replace(config, base_url=base_url).validate()
        return new_config, f"LLM base_url set to {base_url}."

    if command == "timeout":
        if not rest:
            raise LLMConfigError("usage: /llm timeout <seconds>")
        timeout = validate_timeout(int(rest))
        new_config = replace(config, timeout_seconds=timeout).validate()
        return new_config, f"LLM timeout set to {timeout} seconds."

    if command == "streaming":
        if not rest:
            raise LLMConfigError("usage: /llm streaming <true|false>")
        streaming = parse_bool(rest)
        new_config = replace(config, streaming=streaming).validate()
        return new_config, f"LLM streaming set to {str(streaming).lower()}."

