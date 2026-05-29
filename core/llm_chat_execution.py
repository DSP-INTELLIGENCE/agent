"""Narrow provider adapter for safe LLM chat execution.

The front door resolves switch policy and active model state.  This module owns
the provider-specific chat call so parser/front-door code does not construct
provider payloads directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Protocol

from core.llm_open_webui_client import OpenWebUIClient, OpenWebUIClientError

DEFAULT_MAX_PROMPT_CHARS = 8000


class LlmChatExecutionError(RuntimeError):
    """Raised when a provider chat execution cannot complete safely."""


@dataclass(frozen=True)
class LlmChatPolicyResult:
    """Result of local chat prompt policy validation."""

    allowed: bool
    prompt: str = ""
    error: Optional[str] = None
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status": "allowed" if self.allowed else "blocked",
            "error": self.error,
            "max_prompt_chars": self.max_prompt_chars,
        }


class LlmChatExecutor(Protocol):
    """Provider adapter contract for one-shot chat execution."""

    def execute(self, *, model_id: str, prompt: str) -> Mapping[str, Any]:
        ...


OpenWebUIClientFactory = Callable[[], OpenWebUIClient]


def validate_chat_prompt(
    prompt: str,
    *,
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
) -> LlmChatPolicyResult:
    """Validate a one-shot chat prompt before provider adapter execution."""

    normalized = str(prompt or "").strip()
    if not normalized:
        return LlmChatPolicyResult(
            allowed=False,
            error="chat policy blocked: empty prompt",
            max_prompt_chars=max_prompt_chars,
        )
    if len(normalized) > max_prompt_chars:
        return LlmChatPolicyResult(
            allowed=False,
            error=f"chat policy blocked: prompt exceeds max length: {len(normalized)} > {max_prompt_chars}",
            max_prompt_chars=max_prompt_chars,
        )
    return LlmChatPolicyResult(allowed=True, prompt=normalized, max_prompt_chars=max_prompt_chars)


@dataclass(frozen=True)
class OpenWebUIChatExecutor:
    """Chat executor backed by Open WebUI's chat completions endpoint."""

    client_factory: Optional[OpenWebUIClientFactory] = None

    def execute(self, *, model_id: str, prompt: str) -> Mapping[str, Any]:
        client = self.client_factory() if self.client_factory else OpenWebUIClient.from_env()
        try:
            return client.chat_completions(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
        except OpenWebUIClientError as exc:
            raise LlmChatExecutionError(str(exc)) from exc


def build_chat_executor(
    provider: str,
    *,
    open_webui_client_factory: Optional[OpenWebUIClientFactory] = None,
) -> LlmChatExecutor:
    """Build the provider adapter for a selected chat provider."""

    if provider == "open_webui":
        return OpenWebUIChatExecutor(client_factory=open_webui_client_factory)
    raise LlmChatExecutionError(f"chat execution is not implemented for backend: {provider}")


def extract_assistant_text(payload: Mapping[str, Any]) -> str:
    """Extract assistant text from an OpenAI-compatible chat response."""

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, Mapping):
        return ""
    message = first.get("message")
    if not isinstance(message, Mapping):
        return ""
    content = message.get("content")
    if content is None:
        return ""
    return str(content)


def build_chat_response_envelope(
    *,
    provider: str = "",
    model_id: str = "",
    mode: str = "chat",
    response_text: str = "",
    error: Optional[str] = None,
    error_type: Optional[str] = None,
    policy: Optional[Mapping[str, Any]] = None,
    provider_call_made: bool = False,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the stable, secret-safe structured chat response envelope."""

    error_data = None
    if error:
        error_data = {
            "type": error_type or "execution_error",
            "message": error,
        }

    envelope = {
        "provider": provider,
        "model_id": model_id,
        "mode": mode,
        "status": "error" if error_data else "ok",
        "response_text": response_text,
        "error": error_data,
        "policy": dict(
            policy
            or {
                "allowed": None,
                "status": "not_evaluated",
                "error": None,
                "max_prompt_chars": DEFAULT_MAX_PROMPT_CHARS,
            }
        ),
        "provider_call_made": provider_call_made,
        "metadata": dict(metadata or {}),
    }

    # Preserve the original structured fields used by existing callers.
    envelope.update(envelope["metadata"])
    return envelope


def chat_result_payload(
    *,
    provider: str,
    model_id: str,
    payload: Mapping[str, Any],
    policy: Optional[Mapping[str, Any]] = None,
    provider_call_made: bool = True,
) -> Dict[str, Any]:
    """Return the stable, secret-safe structured chat result."""

    return build_chat_response_envelope(
        provider=provider,
        model_id=model_id,
        mode="chat",
        response_text=extract_assistant_text(payload),
        policy=policy,
        provider_call_made=provider_call_made,
        metadata={
            "message_count": 1,
        },
    )


def chat_error_payload(
    *,
    provider: str = "",
    model_id: str = "",
    mode: str = "chat",
    error: str,
    error_type: str,
    policy: Optional[Mapping[str, Any]] = None,
    provider_call_made: bool = False,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a stable chat response envelope for blocked or failed execution."""

    return build_chat_response_envelope(
        provider=provider,
        model_id=model_id,
        mode=mode,
        error=error,
        error_type=error_type,
        policy=policy,
        provider_call_made=provider_call_made,
        metadata=metadata,
    )
