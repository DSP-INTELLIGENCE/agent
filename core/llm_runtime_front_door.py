"""Runtime helpers for presenting the switch-backed `/llm` front door."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


LLM_CONFIG_COMPAT_COMMANDS = {
    "base-url",
    "base_url",
    "model",
    "provider",
    "reset",
    "streaming",
    "timeout",
    "url",
}


def is_llm_help_command(args_text: str) -> bool:
    command = _first_token(args_text)
    return command in {"help", "--help", "-h"}


def is_llm_config_command(args_text: str) -> bool:
    command = _first_token(args_text)
    return command == "config" or command in LLM_CONFIG_COMPAT_COMMANDS


def llm_config_args(args_text: str) -> str:
    text = str(args_text or "").strip()
    if _first_token(text) != "config":
        return text
    _command, _sep, rest = text.partition(" ")
    return rest.strip() or "status"


def llm_help_text() -> str:
    return "\n".join(
        [
            "LLM front door commands:",
            "  /llm",
            "  /llm status",
            "  /llm models",
            "  /llm list",
            "  /llm choose <model>",
            "  /llm use <model>",
            "  /llm select <model>",
            "  /llm current",
            "  /llm clear",
            "  /llm chat <message>",
            "  /llm ask <message>",
            "  /llm test [prompt]",
            "",
            "Compatibility config commands:",
            "  /llm config [status|provider|model|base-url|timeout|streaming|reset]",
            "  /llm provider <provider>",
            "  /llm model <model>",
            "  /llm base-url <url>",
            "  /llm timeout <seconds>",
            "  /llm streaming <true|false>",
            "  /llm reset",
            "",
            "/llm resolves capabilities through /switch. Provider calls are disabled unless the caller explicitly opts in.",
        ]
    )


def format_llm_front_door_result(result: Any) -> str:
    data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    request = _mapping(data.get("request"))
    primary = _mapping(data.get("primary"))
    action = str(request.get("action") or "status")

    lines = [
        "LLM front door:",
        f"  action: {action}",
        f"  capability: {request.get('capability_id') or primary.get('capability_id') or ''}",
        f"  plan_allowed: {_bool_text(data.get('plan_allowed'))}",
        f"  dispatch_allowed: {_bool_text(data.get('dispatch_allowed'))}",
        f"  provider_call_made: {_bool_text(data.get('provider_call_made'))}",
    ]

    backend = primary.get("selected_backend") or primary.get("provider_hint")
    if backend:
        lines.append(f"  backend: {backend}")

    if action in {"status", "unknown"}:
        _append_status(lines, _mapping(data.get("status")))
        _append_provider_config(lines, _mapping(data.get("provider_config")))

    if data.get("model_catalog_error"):
        lines.append(f"  model_catalog_error: {data.get('model_catalog_error')}")
    _append_model_catalog(lines, _mapping(data.get("model_catalog")))

    if data.get("selection_error"):
        lines.append(f"  selection_error: {data.get('selection_error')}")
    _append_selection(lines, _mapping(data.get("selection")))

    if data.get("chat_target_error"):
        lines.append(f"  chat_target_error: {data.get('chat_target_error')}")
    _append_chat_target(lines, _mapping(data.get("chat_target")))

    if data.get("chat_result_error"):
        lines.append(f"  chat_result_error: {data.get('chat_result_error')}")
    _append_chat_result(lines, _mapping(data.get("chat_result")))

    notes = data.get("notes")
    if isinstance(notes, Sequence) and not isinstance(notes, (str, bytes)):
        lines.append("  notes:")
        for note in notes:
            lines.append(f"    - {note}")

    return "\n".join(lines)


def _append_status(lines: list[str], status: Mapping[str, Any]) -> None:
    if not status:
        return
    lines.append("  switch_status:")
    for capability_id in sorted(status):
        item = _mapping(status.get(capability_id))
        lines.append(
            "    - "
            + str(capability_id)
            + f": plan={_bool_text(item.get('plan_allowed'))} dispatch={_bool_text(item.get('dispatch_allowed'))}"
        )


def _append_provider_config(lines: list[str], provider_config: Mapping[str, Any]) -> None:
    providers = provider_config.get("providers")
    if not isinstance(providers, list) or not providers:
        return
    lines.append("  provider_config:")
    for provider in providers:
        item = _mapping(provider)
        provider_id = item.get("provider") or item.get("name") or item.get("id") or ""
        configured = item.get("configured")
        enabled = item.get("enabled")
        parts = [str(provider_id)]
        if configured is not None:
            parts.append(f"configured={_bool_text(configured)}")
        if enabled is not None:
            parts.append(f"enabled={_bool_text(enabled)}")
        lines.append("    - " + " ".join(parts))


def _append_model_catalog(lines: list[str], catalog: Mapping[str, Any]) -> None:
    records = catalog.get("records")
    if not isinstance(records, list) or not records:
        return
    lines.append("  models:")
    for record in records[:20]:
        item = _mapping(record)
        label = item.get("model_id") or item.get("id") or item.get("name") or ""
        provider = item.get("provider") or catalog.get("provider")
        suffix = f" ({provider})" if provider else ""
        lines.append(f"    - {label}{suffix}")
    if len(records) > 20:
        lines.append(f"    - ... {len(records) - 20} more")


def _append_selection(lines: list[str], selection: Mapping[str, Any]) -> None:
    if not selection:
        return
    present = selection.get("selected") if "selected" in selection else selection.get("selection_present")
    provider = selection.get("provider")
    model_id = selection.get("model_id")
    action = selection.get("action")
    lines.append("  selection:")
    if action:
        lines.append(f"    action: {action}")
    lines.append(f"    selected: {_bool_text(present)}")
    if provider:
        lines.append(f"    provider: {provider}")
    if model_id:
        lines.append(f"    model_id: {model_id}")


def _append_chat_target(lines: list[str], target: Mapping[str, Any]) -> None:
    if not target:
        return
    lines.append("  chat_target:")
    for key in ("provider", "model_id", "source", "selection_present", "validated"):
        if key in target:
            value = target.get(key)
            lines.append(f"    {key}: {_bool_text(value) if isinstance(value, bool) else value}")


def _append_chat_result(lines: list[str], chat_result: Mapping[str, Any]) -> None:
    if not chat_result:
        return
    lines.append("  chat_result:")
    for key in ("provider", "model_id", "mode", "status", "provider_call_made"):
        if key in chat_result:
            value = chat_result.get(key)
            lines.append(f"    {key}: {_bool_text(value) if isinstance(value, bool) else value}")
    response_text = str(chat_result.get("response_text") or "")
    if response_text:
        lines.append("    response_text:")
        lines.append(_indent(response_text, "      "))
    error = chat_result.get("error")
    if error:
        lines.append(f"    error: {error}")


def _first_token(text: str) -> str:
    return str(text or "").strip().split(maxsplit=1)[0].lower() if str(text or "").strip() else "status"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())
