"""LLM domain front-door parsing and switch-spine resolution.

This module maps `/llm ...` user-facing commands to stable capability IDs and
resolves those capabilities through the switch spine.  Provider calls are
explicit: library callers must opt in with ``allow_provider_calls=True``.  The
module CLI opts in for `/llm models` by default so local manual checks can list
models through the selected provider without adding provider calls to normal
unit tests.
"""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from core.llm_chat_execution import (
    LlmChatExecutionError,
    LlmChatExecutor,
    build_chat_response_envelope,
    chat_error_payload,
    build_chat_executor,
    chat_result_payload,
    extract_assistant_text,
    validate_chat_prompt,
)
from core.llm_model_catalog import ModelCatalog, normalize_model_records
from core.llm_model_selection import (
    DEFAULT_SELECTION_PATH,
    LlmModelSelection,
    clear_selection,
    load_selection,
    parse_model_target,
    save_selection,
    selection_status,
)
from core.llm_open_webui_client import OpenWebUIClient, OpenWebUIClientError
from core.llm_provider_config import provider_config_status
from core.switch_spine import CapabilityResolution, load_capability_bindings, resolve_capability

DEFAULT_CATALOG_PATH = Path("data_agent/switches/capabilities.seed.json")

LLM_ACTION_CAPABILITIES: Mapping[str, str] = {
    "": "llm.enabled",
    "status": "llm.enabled",
    "current": "llm.chat",
    "chat": "llm.chat",
    "ask": "llm.chat",
    "models": "llm.models",
    "model": "llm.models",
    "list": "llm.models",
    "providers": "llm.models",
    "provider": "llm.models",
    "refresh": "llm.models",
    "choose": "llm.select",
    "select": "llm.select",
    "use": "llm.select",
    "clear": "llm.select",
    "test": "llm.chat",
}

STATUS_CAPABILITIES: Sequence[str] = (
    "llm.enabled",
    "llm.chat",
    "llm.models",
    "llm.select",
)

OpenWebUIClientFactory = Callable[[], OpenWebUIClient]
LlmChatExecutorFactory = Callable[[str], LlmChatExecutor]


@dataclass(frozen=True)
class LlmFrontDoorRequest:
    """Parsed `/llm` command before backend/provider execution."""

    raw_text: str
    front_door: str
    action: str
    capability_id: str
    args: Sequence[str] = field(default_factory=tuple)
    unknown_action: Optional[str] = None

    @property
    def is_unknown(self) -> bool:
        return self.unknown_action is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "front_door": self.front_door,
            "action": self.action,
            "capability_id": self.capability_id,
            "args": list(self.args),
            "unknown_action": self.unknown_action,
        }


@dataclass(frozen=True)
class LlmFrontDoorResult:
    """Switch-spine resolution result for an `/llm` front-door request."""

    request: LlmFrontDoorRequest
    primary: CapabilityResolution
    status: Mapping[str, CapabilityResolution] = field(default_factory=dict)
    provider_config: Mapping[str, Any] = field(default_factory=dict)
    model_catalog: Mapping[str, Any] = field(default_factory=dict)
    model_catalog_error: Optional[str] = None
    selection: Mapping[str, Any] = field(default_factory=dict)
    selection_error: Optional[str] = None
    selection_changed: bool = False
    chat_target: Mapping[str, Any] = field(default_factory=dict)
    chat_target_error: Optional[str] = None
    chat_result: Mapping[str, Any] = field(default_factory=dict)
    chat_result_error: Optional[str] = None
    provider_call_made: bool = False

    @property
    def plan_allowed(self) -> bool:
        return self.primary.plan_allowed

    @property
    def dispatch_allowed(self) -> bool:
        return self.primary.dispatch_allowed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "front_door": self.request.front_door,
            "request": self.request.to_dict(),
            "plan_allowed": self.plan_allowed,
            "dispatch_allowed": self.dispatch_allowed,
            "primary": self.primary.to_dict(),
            "status": {key: value.to_dict() for key, value in self.status.items()},
            "provider_config": dict(self.provider_config),
            "model_catalog": dict(self.model_catalog),
            "model_catalog_error": self.model_catalog_error,
            "selection": dict(self.selection),
            "selection_error": self.selection_error,
            "selection_changed": self.selection_changed,
            "chat_target": dict(self.chat_target),
            "chat_target_error": self.chat_target_error,
            "chat_result": dict(self.chat_result),
            "chat_result_error": self.chat_result_error,
            "provider_call_made": self.provider_call_made,
            "notes": _notes_for(self),
        }


def parse_llm_front_door(text: str) -> LlmFrontDoorRequest:
    """Parse a `/llm` command into an action and capability ID.

    Unknown subcommands are kept inspectable and mapped to `llm.enabled` so the
    caller can still explain `/llm` state without executing anything.
    """

    raw_text = text.strip()
    if not raw_text:
        raise ValueError("empty /llm command")

    parts = _split_command(raw_text)
    if not parts:
        raise ValueError("empty /llm command")

    front = parts[0].lower()
    if front in {"/ai", "ai"}:
        args = tuple(parts[1:]) if len(parts) > 1 else tuple()
        return LlmFrontDoorRequest(
            raw_text=raw_text,
            front_door="/ai",
            action="chat",
            capability_id="llm.chat",
            args=args,
        )

    if front not in {"/llm", "llm"}:
        raise ValueError("expected /llm front door")

    action = parts[1].lower() if len(parts) > 1 else "status"
    args = tuple(parts[2:]) if len(parts) > 2 else tuple()
    capability_id = LLM_ACTION_CAPABILITIES.get(action)

    if capability_id is None:
        return LlmFrontDoorRequest(
            raw_text=raw_text,
            front_door="/llm",
            action="unknown",
            capability_id="llm.enabled",
            args=tuple(parts[1:]),
            unknown_action=action,
        )

    return LlmFrontDoorRequest(
        raw_text=raw_text,
        front_door="/llm",
        action=action,
        capability_id=capability_id,
        args=args,
    )


def resolve_llm_front_door(
    text: str,
    *,
    catalog_path: Path | str = DEFAULT_CATALOG_PATH,
    selection_path: Path | str = DEFAULT_SELECTION_PATH,
    allow_provider_calls: bool = False,
    allow_chat_execution: Optional[bool] = None,
    chat_only_models: bool = True,
    open_webui_client_factory: Optional[OpenWebUIClientFactory] = None,
    chat_executor_factory: Optional[LlmChatExecutorFactory] = None,
) -> LlmFrontDoorResult:
    """Resolve a `/llm` command through the switch spine.

    By default this function does not call Open WebUI, Ollama,
    OpenAI-compatible endpoints, or any other provider.  Live model listing is
    opt-in via ``allow_provider_calls=True`` so normal tests stay offline and
    callers can decide when provider access is allowed.
    """

    request = parse_llm_front_door(text)
    chat_execution_allowed = allow_provider_calls if allow_chat_execution is None else allow_chat_execution
    bindings = load_capability_bindings(Path(catalog_path))
    primary = resolve_capability(request.capability_id, bindings)

    status: Dict[str, CapabilityResolution] = {}
    config_status: Dict[str, Any] = {}
    model_catalog: Dict[str, Any] = {}
    model_catalog_error: Optional[str] = None
    selection: Dict[str, Any] = {}
    selection_error: Optional[str] = None
    selection_changed = False
    chat_target: Dict[str, Any] = {}
    chat_target_error: Optional[str] = None
    chat_result: Dict[str, Any] = {}
    chat_result_error: Optional[str] = None
    provider_call_made = False

    if request.action in {"status", "unknown"}:
        for capability_id in STATUS_CAPABILITIES:
            status[capability_id] = resolve_capability(capability_id, bindings)
        config_status = provider_config_status()

    if request.action in {"models", "model", "list", "providers", "provider", "refresh"}:
        if allow_provider_calls:
            model_catalog, model_catalog_error, provider_call_made = _live_model_catalog(
                primary,
                chat_only=chat_only_models,
                open_webui_client_factory=open_webui_client_factory,
            )
        else:
            model_catalog_error = "provider calls disabled for this resolver call"

    if request.action == "current":
        selection = selection_status(selection_path)

    if request.action in {"current", "chat", "ask", "test"}:
        chat_target, chat_target_error, provider_call_made = _resolve_chat_target(
            primary,
            selection_path=selection_path,
            allow_provider_calls=allow_provider_calls,
            open_webui_client_factory=open_webui_client_factory,
            provider_call_made=provider_call_made,
        )
        if not selection:
            selection = selection_status(selection_path)
        chat_result, chat_result_error, provider_call_made = _maybe_execute_chat_request(
            request,
            chat_target=chat_target,
            chat_target_error=chat_target_error,
            allow_chat_execution=chat_execution_allowed,
            open_webui_client_factory=open_webui_client_factory,
            chat_executor_factory=chat_executor_factory,
            provider_call_made=provider_call_made,
        )

    if request.action in {"choose", "select", "use"}:
        selection, selection_error, selection_changed, provider_call_made = _select_model(
            request,
            primary,
            selection_path=selection_path,
            allow_provider_calls=allow_provider_calls,
            open_webui_client_factory=open_webui_client_factory,
            provider_call_made=provider_call_made,
        )

    if request.action == "clear":
        selection, selection_error, selection_changed = _clear_model_selection(
            primary,
            selection_path=selection_path,
        )

    return LlmFrontDoorResult(
        request=request,
        primary=primary,
        status=status,
        provider_config=config_status,
        model_catalog=model_catalog,
        model_catalog_error=model_catalog_error,
        selection=selection,
        selection_error=selection_error,
        selection_changed=selection_changed,
        chat_target=chat_target,
        chat_target_error=chat_target_error,
        chat_result=chat_result,
        chat_result_error=chat_result_error,
        provider_call_made=provider_call_made,
    )


def _live_model_catalog(
    resolution: CapabilityResolution,
    *,
    chat_only: bool,
    open_webui_client_factory: Optional[OpenWebUIClientFactory],
) -> tuple[Dict[str, Any], Optional[str], bool]:
    """List live provider models and normalize them through the catalog layer."""

    if not resolution.plan_allowed:
        return {}, resolution.plan_blocked_reason or resolution.blocked_reason, False
    if not resolution.dispatch_allowed:
        return {}, resolution.dispatch_blocked_reason or resolution.blocked_reason, False

    selected_backend = resolution.selected_backend or resolution.provider_hint
    if selected_backend != "open_webui":
        return {}, f"live model listing is not implemented for backend: {selected_backend}", False

    client = open_webui_client_factory() if open_webui_client_factory else OpenWebUIClient.from_env()
    try:
        models = client.list_models()
    except OpenWebUIClientError as exc:
        return {}, str(exc), True

    raw_records = []
    for model in models:
        raw_record = dict(model.raw)
        raw_record.setdefault("id", model.model_id)
        raw_record.setdefault("name", model.name)
        raw_records.append(raw_record)

    catalog: ModelCatalog = normalize_model_records("open_webui", raw_records)
    if chat_only:
        catalog = catalog.filter(chat_only=True)
    data = catalog.to_dict(include_raw=False)
    data["provider"] = "open_webui"
    data["chat_only"] = chat_only
    return data, None, True


def _split_command(text: str) -> Sequence[str]:
    try:
        return tuple(shlex.split(text))
    except ValueError:
        return tuple(text.split())


def _select_model(
    request: LlmFrontDoorRequest,
    resolution: CapabilityResolution,
    *,
    selection_path: Path | str,
    allow_provider_calls: bool,
    open_webui_client_factory: Optional[OpenWebUIClientFactory],
    provider_call_made: bool,
) -> tuple[Dict[str, Any], Optional[str], bool, bool]:
    if not resolution.dispatch_allowed:
        return selection_status(selection_path), _selection_block_reason(resolution), False, provider_call_made
    if len(request.args) != 1:
        return selection_status(selection_path), "usage: /llm choose <model>", False, provider_call_made

    known_providers = _known_selection_providers(resolution)
    default_provider = resolution.selected_backend or resolution.provider_hint or ""
    try:
        target = parse_model_target(
            request.args[0],
            default_provider=default_provider,
            known_providers=known_providers,
        )
    except ValueError as exc:
        return selection_status(selection_path), str(exc), False, provider_call_made

    if target.provider not in known_providers:
        return (
            selection_status(selection_path),
            f"provider is not allowed for llm.select: {target.provider}",
            False,
            provider_call_made,
        )

    validated = False
    validation_error = None
    if allow_provider_calls:
        validated, validation_error, provider_call_made = _validate_selected_model(
            target.provider,
            target.model_id,
            resolution=resolution,
            open_webui_client_factory=open_webui_client_factory,
            provider_call_made=provider_call_made,
        )
        if validation_error:
            return selection_status(selection_path), validation_error, False, provider_call_made

    saved = LlmModelSelection(provider=target.provider, model_id=target.model_id)
    save_selection(saved, selection_path)
    selection = selection_status(selection_path)
    selection.update(
        {
            "action": "selected",
            "requested": target.to_dict(),
            "validated": validated,
        }
    )
    return selection, None, True, provider_call_made


def _clear_model_selection(
    resolution: CapabilityResolution,
    *,
    selection_path: Path | str,
) -> tuple[Dict[str, Any], Optional[str], bool]:
    if not resolution.dispatch_allowed:
        return selection_status(selection_path), _selection_block_reason(resolution), False

    removed = clear_selection(selection_path)
    selection = selection_status(selection_path)
    selection.update({"action": "cleared", "cleared": removed})
    return selection, None, removed


def _resolve_chat_target(
    resolution: CapabilityResolution,
    *,
    selection_path: Path | str,
    allow_provider_calls: bool,
    open_webui_client_factory: Optional[OpenWebUIClientFactory],
    provider_call_made: bool,
) -> tuple[Dict[str, Any], Optional[str], bool]:
    if not resolution.dispatch_allowed:
        return {}, _selection_block_reason(resolution), provider_call_made

    selected = load_selection(selection_path)
    allowed_providers = _known_selection_providers(resolution)

    if selected is None:
        return {
            "provider": resolution.selected_backend or resolution.provider_hint,
            "model_id": None,
            "source": "llm.chat default backend",
            "selection_present": False,
        }, None, provider_call_made

    if selected.provider not in allowed_providers:
        return {}, f"saved selection provider is not allowed for llm.chat: {selected.provider}", provider_call_made

    if allow_provider_calls:
        validated, validation_error, provider_call_made = _validate_selected_model(
            selected.provider,
            selected.model_id,
            resolution=resolution,
            open_webui_client_factory=open_webui_client_factory,
            provider_call_made=provider_call_made,
        )
        if validation_error:
            return {}, validation_error, provider_call_made
    else:
        validated = False

    return {
        "provider": selected.provider,
        "model_id": selected.model_id,
        "source": "saved /llm selection",
        "selection_present": True,
        "validated": validated,
    }, None, provider_call_made


def _maybe_execute_chat_request(
    request: LlmFrontDoorRequest,
    *,
    chat_target: Mapping[str, Any],
    chat_target_error: Optional[str],
    allow_chat_execution: bool,
    open_webui_client_factory: Optional[OpenWebUIClientFactory],
    chat_executor_factory: Optional[LlmChatExecutorFactory],
    provider_call_made: bool,
) -> tuple[Dict[str, Any], Optional[str], bool]:
    if chat_target_error:
        return (
            chat_error_payload(
                error=chat_target_error,
                error_type="selection_error",
                provider_call_made=False,
            ),
            chat_target_error,
            provider_call_made,
        )

    if request.action not in {"chat", "ask", "test"}:
        return {}, None, provider_call_made

    if not allow_chat_execution:
        return {}, None, provider_call_made

    provider = str(chat_target.get("provider") or "").strip()
    model_id = str(chat_target.get("model_id") or "").strip()
    if not provider:
        error = "no active provider is available for llm.chat"
        return (
            chat_error_payload(
                error=error,
                error_type="selection_error",
                provider_call_made=False,
            ),
            error,
            provider_call_made,
        )
    if not model_id:
        error = "no active model is selected for llm.chat"
        return (
            chat_error_payload(
                provider=provider,
                error=error,
                error_type="selection_error",
                provider_call_made=False,
            ),
            error,
            provider_call_made,
        )

    if request.action == "test":
        client = open_webui_client_factory() if open_webui_client_factory else OpenWebUIClient.from_env()
        prompt = " ".join(request.args).strip() or "Reply with OK."
        result = client.test_chat(model_id, prompt=prompt)
        provider_call_made = True
        if not result.ok:
            error = result.error or "provider test failed"
            return (
                chat_error_payload(
                    provider=provider,
                    model_id=model_id,
                    mode="test",
                    error=error,
                    error_type="execution_error",
                    provider_call_made=True,
                ),
                error,
                provider_call_made,
            )
        response_text = _extract_assistant_text(result.response)
        return (
            build_chat_response_envelope(
                provider=provider,
                model_id=model_id,
                mode="test",
                response_text=response_text,
                provider_call_made=True,
                metadata={
                    "ok": True,
                    "elapsed_ms": result.elapsed_ms,
                },
            ),
            None,
            provider_call_made,
        )

    prompt = " ".join(request.args).strip()
    policy = validate_chat_prompt(prompt)
    if not policy.allowed:
        error = policy.error or "chat policy blocked"
        return (
            chat_error_payload(
                provider=provider,
                model_id=model_id,
                error=error,
                error_type="policy_error",
                policy=policy.to_dict(),
                provider_call_made=False,
                metadata={"message_count": 1},
            ),
            error,
            provider_call_made,
        )

    try:
        executor = (
            chat_executor_factory(provider)
            if chat_executor_factory
            else build_chat_executor(provider, open_webui_client_factory=open_webui_client_factory)
        )
    except LlmChatExecutionError as exc:
        error = str(exc)
        return (
            chat_error_payload(
                provider=provider,
                model_id=model_id,
                error=error,
                error_type="execution_error",
                policy=policy.to_dict(),
                provider_call_made=False,
                metadata={"message_count": 1},
            ),
            error,
            provider_call_made,
        )

    try:
        payload = executor.execute(model_id=model_id, prompt=policy.prompt)
    except LlmChatExecutionError as exc:
        error = str(exc)
        return (
            chat_error_payload(
                provider=provider,
                model_id=model_id,
                error=error,
                error_type="execution_error",
                policy=policy.to_dict(),
                provider_call_made=True,
                metadata={"message_count": 1},
            ),
            error,
            True,
        )

    provider_call_made = True
    return (
        chat_result_payload(
            provider=provider,
            model_id=model_id,
            payload=payload,
            policy=policy.to_dict(),
            provider_call_made=True,
        ),
        None,
        provider_call_made,
    )


def _validate_selected_model(
    provider: str,
    model_id: str,
    *,
    resolution: CapabilityResolution,
    open_webui_client_factory: Optional[OpenWebUIClientFactory],
    provider_call_made: bool,
) -> tuple[bool, Optional[str], bool]:
    if provider != "open_webui":
        return False, None, provider_call_made

    catalog, error, call_made = _live_model_catalog(
        resolution,
        chat_only=False,
        open_webui_client_factory=open_webui_client_factory,
    )
    provider_call_made = provider_call_made or call_made
    if error:
        return False, f"could not validate selected model: {error}", provider_call_made

    records = catalog.get("records")
    if not isinstance(records, list):
        return False, "could not validate selected model: model catalog unavailable", provider_call_made

    for record in records:
        if not isinstance(record, Mapping):
            continue
        if str(record.get("model_id")) != model_id:
            continue
        if record.get("is_chat_capable") is not True:
            return False, f"selected model is not chat-capable for llm.select: {model_id}", provider_call_made
        return True, None, provider_call_made

    return False, f"selected model was not found in the live catalog for provider: {provider}", provider_call_made


def _known_selection_providers(resolution: CapabilityResolution) -> set[str]:
    providers = set()
    if resolution.binding:
        providers.update(str(name).strip() for name in resolution.binding.allowed_backends if str(name).strip())
    if resolution.selected_backend:
        providers.add(resolution.selected_backend)
    if resolution.provider_hint:
        providers.add(resolution.provider_hint)
    return providers


def _selection_block_reason(resolution: CapabilityResolution) -> str:
    return resolution.dispatch_blocked_reason or resolution.plan_blocked_reason or resolution.blocked_reason or "llm.select is blocked"


def _extract_assistant_text(payload: Mapping[str, Any]) -> str:
    return extract_assistant_text(payload)


def _notes_for(result: LlmFrontDoorResult) -> Sequence[str]:
    notes = []
    if result.request.is_unknown:
        notes.append(f"unknown /llm action: {result.request.unknown_action}")
    notes.append("/llm resolved through core.switch_spine")
    if result.provider_call_made:
        notes.append("provider call was made for live model listing")
    else:
        notes.append("no provider call was made")
    if result.model_catalog_error:
        notes.append("model catalog unavailable: " + result.model_catalog_error)
    if result.selection_error:
        notes.append("selection error: " + result.selection_error)
    elif result.selection:
        action = result.selection.get("action")
        if action == "selected":
            notes.append("local model selection was updated")
        elif action == "cleared":
            notes.append("local model selection was cleared")
    if result.chat_target_error:
        notes.append("chat target error: " + result.chat_target_error)
    elif result.chat_target:
        notes.append("chat target resolved from active default selection")
    if result.chat_result_error:
        notes.append("chat execution error: " + result.chat_result_error)
    elif result.chat_result:
        notes.append("chat execution used the active chat target")
    if result.dispatch_allowed:
        notes.append("dispatch is allowed by the switch spine")
    elif result.primary.dispatch_blocked_reason:
        notes.append("dispatch blocked: " + result.primary.dispatch_blocked_reason)
    return tuple(notes)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve an /llm command through the switch spine.")
    parser.add_argument(
        "command",
        nargs="*",
        help="/llm command text, for example: /llm models or /llm choose open_webui:model",
    )
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG_PATH),
        help="Path to capability catalog JSON.",
    )
    parser.add_argument(
        "--no-live-models",
        action="store_true",
        help="Do not call providers for /llm models; return switch resolution only.",
    )
    parser.add_argument(
        "--all-models",
        action="store_true",
        help="Show all discovered model capabilities instead of chat-capable models only.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    command_text = " ".join(args.command).strip() or "/llm status"
    result = resolve_llm_front_door(
        command_text,
        catalog_path=args.catalog,
        allow_provider_calls=not args.no_live_models,
        chat_only_models=not args.all_models,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
