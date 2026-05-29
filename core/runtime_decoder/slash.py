"""Deterministic slash-command decoding into runtime InputSpec models."""
from __future__ import annotations

from .models import (
    FsCommandSpec,
    GroundCommandSpec,
    InputSpec,
    MemoryCommandSpec,
    PatchCommandSpec,
    PluginCommandSpec,
    PythonCommandSpec,
    SearchCommandSpec,
    SlashCommandSpec,
    ShellCommandSpec,
    SystemCommandSpec,
    SwitchCommandSpec,
    ToolCommandSpec,
    UnknownInputSpec,
    WebCommandSpec,
)


_SPEC_CLASS_BY_ROOT: dict[str, type[SlashCommandSpec]] = {
    "help": SystemCommandSpec,
    "commands": SystemCommandSpec,
    "state": SystemCommandSpec,
    "config": SystemCommandSpec,
    "fs": FsCommandSpec,
    "python": PythonCommandSpec,
    "shell": ShellCommandSpec,
    "remember": MemoryCommandSpec,
    "memory": MemoryCommandSpec,
    "plugins": PluginCommandSpec,
    "plugin": PluginCommandSpec,
    "plugin_json": PluginCommandSpec,
    "switch": SwitchCommandSpec,
    "ground": GroundCommandSpec,
    "web": WebCommandSpec,
    "search": SearchCommandSpec,
    "patch": PatchCommandSpec,
    "tool": ToolCommandSpec,
}


def is_slash_command(text: str) -> bool:
    return str(text or "").lstrip().startswith("/")


def decode_slash_command(text: str) -> InputSpec:
    raw_text = str(text or "")
    normalized_text = " ".join(raw_text.split())

    if not normalized_text:
        return UnknownInputSpec(
            kind="unknown",
            raw_text=raw_text,
            normalized_text="",
            reason="empty input",
        )

    if not is_slash_command(raw_text):
        return UnknownInputSpec(
            kind="unknown",
            raw_text=raw_text,
            normalized_text=normalized_text,
            reason="non-slash input",
        )

    tokenized = normalized_text.split()
    first = tokenized[0]
    root = first[1:] if first.startswith("/") else first
    args = tuple(tokenized[1:])

    spec_cls = _SPEC_CLASS_BY_ROOT.get(root.lower(), SlashCommandSpec)
    return spec_cls(
        kind=_kind_for_class(spec_cls),
        raw_text=raw_text,
        normalized_text=normalized_text,
        command=root,
        args=args,
    )


def _kind_for_class(spec_cls: type[SlashCommandSpec]) -> str:
    if spec_cls is SystemCommandSpec:
        return "system_command"
    if spec_cls is FsCommandSpec:
        return "fs_command"
    if spec_cls is PythonCommandSpec:
        return "python_command"
    if spec_cls is ShellCommandSpec:
        return "shell_command"
    if spec_cls is MemoryCommandSpec:
        return "memory_command"
    if spec_cls is PluginCommandSpec:
        return "plugin_command"
    if spec_cls is SwitchCommandSpec:
        return "switch_command"
    if spec_cls is GroundCommandSpec:
        return "ground_command"
    if spec_cls is WebCommandSpec:
        return "web_command"
    if spec_cls is SearchCommandSpec:
        return "search_command"
    if spec_cls is PatchCommandSpec:
        return "patch_command"
    if spec_cls is ToolCommandSpec:
        return "tool_command"
    return "slash_command"
