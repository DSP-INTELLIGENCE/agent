"""Open WebUI client for the agent LLM provider layer.

This module is intentionally small and dependency-free.  It provides a
secret-safe client for the local Open WebUI API without wiring provider calls
into the `/llm` front door yet.  Normal tests should mock the HTTP transport and
must not require a running Open WebUI server.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence
from urllib import error, request

DEFAULT_OPEN_WEBUI_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_TIMEOUT_SECONDS = 15.0

JsonMap = Dict[str, Any]
UrlOpen = Callable[..., Any]


class OpenWebUIClientError(RuntimeError):
    """Raised when the Open WebUI client cannot complete a request safely."""


@dataclass(frozen=True)
class OpenWebUIModel:
    """Provider-neutral record for a model discovered from Open WebUI."""

    model_id: str
    name: str
    raw: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> JsonMap:
        return {"id": self.model_id, "name": self.name, "raw": dict(self.raw)}


@dataclass(frozen=True)
class OpenWebUITestResult:
    """Result for a small provider test call."""

    ok: bool
    model: str
    elapsed_ms: int
    error: Optional[str] = None
    response: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> JsonMap:
        return {
            "ok": self.ok,
            "model": self.model,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "response": dict(self.response),
        }


@dataclass(frozen=True)
class OpenWebUIClient:
    """Small client for Open WebUI's API.

    The API key is never returned by public methods, printed by the CLI, or
    included in error messages.
    """

    base_url: str = DEFAULT_OPEN_WEBUI_BASE_URL
    api_key: Optional[str] = None
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    opener: UrlOpen = request.urlopen

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "OpenWebUIClient":
        values = os.environ if env is None else env
        return cls(
            base_url=values.get("OPEN_WEBUI_BASE_URL", DEFAULT_OPEN_WEBUI_BASE_URL),
            api_key=values.get("OPEN_WEBUI_API_KEY"),
        )

    def diagnostic_config(self) -> JsonMap:
        """Return secret-safe client configuration diagnostics."""

        return {
            "base_url": self.base_url,
            "api_key_present": bool(self.api_key),
            "timeout": self.timeout,
            "notes": ["Open WebUI API key value is never included in diagnostics"],
        }

    def list_models(self) -> Sequence[OpenWebUIModel]:
        """List models from Open WebUI without hardcoding model names."""

        payload = self._request_json("GET", "/api/models")
        return tuple(_extract_models(payload))

    def chat_completions(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        stream: bool = False,
    ) -> JsonMap:
        """Call Open WebUI chat completions for an explicit model."""

        if not model.strip():
            raise OpenWebUIClientError("model is required")
        if not messages:
            raise OpenWebUIClientError("at least one message is required")
        body = {"model": model, "messages": list(messages), "stream": stream}
        return self._request_json("POST", "/api/chat/completions", body)

    def test_chat(self, model: str, prompt: str = "Reply with OK.") -> OpenWebUITestResult:
        """Send a tiny explicit test request to the selected model."""

        started = time.monotonic()
        try:
            payload = self.chat_completions(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
        except OpenWebUIClientError as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return OpenWebUITestResult(ok=False, model=model, elapsed_ms=elapsed_ms, error=str(exc))
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return OpenWebUITestResult(ok=True, model=model, elapsed_ms=elapsed_ms, response=payload)

    def _request_json(self, method: str, path: str, body: Optional[Mapping[str, Any]] = None) -> JsonMap:
        url = _join_url(self.base_url, path)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = request.Request(url=url, data=data, headers=headers, method=method.upper())
        try:
            with self.opener(req, timeout=self.timeout) as response:
                raw = response.read()
        except error.HTTPError as exc:
            message = _safe_error_message(f"HTTP {exc.code}: {exc.reason}", self.api_key)
            raise OpenWebUIClientError(message) from exc
        except error.URLError as exc:
            message = _safe_error_message(f"connection error: {exc.reason}", self.api_key)
            raise OpenWebUIClientError(message) from exc
        except OSError as exc:
            message = _safe_error_message(f"connection error: {exc}", self.api_key)
            raise OpenWebUIClientError(message) from exc

        try:
            loaded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenWebUIClientError("Open WebUI returned invalid JSON") from exc
        if not isinstance(loaded, dict):
            raise OpenWebUIClientError("Open WebUI returned a non-object JSON response")
        return loaded


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _safe_error_message(message: str, secret: Optional[str]) -> str:
    if secret:
        return message.replace(secret, "<redacted>")
    return message


def _extract_models(payload: Mapping[str, Any]) -> Sequence[OpenWebUIModel]:
    """Normalize several common Open WebUI/OpenAI-compatible model shapes."""

    candidates: Iterable[Any]
    if isinstance(payload.get("data"), list):
        candidates = payload["data"]
    elif isinstance(payload.get("models"), list):
        candidates = payload["models"]
    else:
        candidates = []

    models = []
    for item in candidates:
        if isinstance(item, str):
            model_id = item
            raw: Mapping[str, Any] = {"id": item}
        elif isinstance(item, Mapping):
            value = item.get("id") or item.get("name") or item.get("model")
            if not isinstance(value, str):
                continue
            model_id = value
            raw = item
        else:
            continue
        model_id = model_id.strip()
        if not model_id:
            continue
        models.append(OpenWebUIModel(model_id=model_id, name=model_id, raw=raw))
    return tuple(models)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Open WebUI client diagnostics for agent")
    parser.add_argument("--base-url", default=os.environ.get("OPEN_WEBUI_BASE_URL", DEFAULT_OPEN_WEBUI_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("OPEN_WEBUI_API_KEY"))
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--list", action="store_true", help="list models from Open WebUI")
    parser.add_argument("--test-model", help="send a tiny chat completion test to this model")
    args = parser.parse_args(argv)

    client = OpenWebUIClient(base_url=args.base_url, api_key=args.api_key, timeout=args.timeout)
    try:
        if args.list:
            models = [model.to_dict() for model in client.list_models()]
            print(json.dumps({"ok": True, "models": models, "config": client.diagnostic_config()}, indent=2, sort_keys=True))
            return 0
        if args.test_model:
            result = client.test_chat(args.test_model)
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            return 0 if result.ok else 2
        print(json.dumps({"ok": True, "config": client.diagnostic_config()}, indent=2, sort_keys=True))
        return 0
    except OpenWebUIClientError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "config": client.diagnostic_config()}, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
