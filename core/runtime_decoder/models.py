"""Deterministic runtime input spec models.

These models are non-executing containers only. They do not parse, route,
or invoke any runtime behavior by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, TypeVar


def _text(value: Any, *, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _copy_metadata(metadata: Any) -> dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping")
    return dict(metadata)


def _tuple_texts(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        return (_text(values),)
    return tuple(_text(item) for item in values)


def _args_to_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        return (_text(values),)
    if isinstance(values, Mapping):
        return tuple(f"{_text(key)}={_text(value)}" for key, value in values.items())
    return tuple(_text(item) for item in values)


def _command_spec_from_dict(
    cls: type["SlashCommandSpec"],
    data: Mapping[str, Any] | None,
    *,
    default_kind: str,
) -> "SlashCommandSpec":
    payload = dict(data or {})
    return cls(
        kind=_text(payload.get("kind", default_kind)),
        raw_text=_text(payload.get("raw_text", "")),
        normalized_text=_text(payload.get("normalized_text", "")),
        metadata=_copy_metadata(payload.get("metadata", {})),
        command=_text(payload.get("command", "")),
        args=_args_to_tuple(payload.get("args", ())),
    )


@dataclass(frozen=True)
class InputSpec:
    kind: str
    raw_text: str = ""
    normalized_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _copy_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "InputSpec":
        payload = dict(data or {})
        kind = _text(payload.get("kind"))
        if not kind:
            raise ValueError("input spec requires kind")
        spec_cls = _SPEC_KIND_MAP.get(kind, cls)
        if spec_cls is cls:
            return cls(
                kind=kind,
                raw_text=_text(payload.get("raw_text", "")),
                normalized_text=_text(payload.get("normalized_text", "")),
                metadata=_copy_metadata(payload.get("metadata", {})),
            )
        return spec_cls.from_dict(payload)


@dataclass(frozen=True)
class SlashCommandSpec(InputSpec):
    command: str = ""
    args: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "args", tuple(_text(item) for item in self.args))

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "command": self.command,
                "args": list(self.args),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SlashCommandSpec":
        return _command_spec_from_dict(cls, data, default_kind="slash_command")


@dataclass(frozen=True)
class SystemCommandSpec(SlashCommandSpec):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SystemCommandSpec":
        return _command_spec_from_dict(cls, data, default_kind="system_command")


@dataclass(frozen=True)
class FsCommandSpec(SlashCommandSpec):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "FsCommandSpec":
        return _command_spec_from_dict(cls, data, default_kind="fs_command")


@dataclass(frozen=True)
class PythonCommandSpec(SlashCommandSpec):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "PythonCommandSpec":
        return _command_spec_from_dict(cls, data, default_kind="python_command")


@dataclass(frozen=True)
class ShellCommandSpec(SlashCommandSpec):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ShellCommandSpec":
        return _command_spec_from_dict(cls, data, default_kind="shell_command")


@dataclass(frozen=True)
class MemoryCommandSpec(SlashCommandSpec):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "MemoryCommandSpec":
        return _command_spec_from_dict(cls, data, default_kind="memory_command")


@dataclass(frozen=True)
class PluginCommandSpec(SlashCommandSpec):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "PluginCommandSpec":
        return _command_spec_from_dict(cls, data, default_kind="plugin_command")


@dataclass(frozen=True)
class SwitchCommandSpec(SlashCommandSpec):
    def __post_init__(self) -> None:
        if not self.kind:
            object.__setattr__(self, "kind", "switch_command")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SwitchCommandSpec":
        payload = dict(data or {})
        payload.setdefault("kind", "switch_command")
        return cls(
            kind=_text(payload.get("kind", "switch_command")),
            raw_text=_text(payload.get("raw_text", "")),
            normalized_text=_text(payload.get("normalized_text", "")),
            metadata=_copy_metadata(payload.get("metadata", {})),
            command=_text(payload.get("command", "")),
            args=_args_to_tuple(payload.get("args", ())),
        )


@dataclass(frozen=True)
class GroundCommandSpec(SlashCommandSpec):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "GroundCommandSpec":
        payload = dict(data or {})
        payload.setdefault("kind", "ground_command")
        return cls(
            kind=_text(payload.get("kind", "ground_command")),
            raw_text=_text(payload.get("raw_text", "")),
            normalized_text=_text(payload.get("normalized_text", "")),
            metadata=_copy_metadata(payload.get("metadata", {})),
            command=_text(payload.get("command", "")),
            args=_args_to_tuple(payload.get("args", ())),
        )


@dataclass(frozen=True)
class WebCommandSpec(SlashCommandSpec):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "WebCommandSpec":
        payload = dict(data or {})
        payload.setdefault("kind", "web_command")
        return cls(
            kind=_text(payload.get("kind", "web_command")),
            raw_text=_text(payload.get("raw_text", "")),
            normalized_text=_text(payload.get("normalized_text", "")),
            metadata=_copy_metadata(payload.get("metadata", {})),
            command=_text(payload.get("command", "")),
            args=_args_to_tuple(payload.get("args", ())),
        )


@dataclass(frozen=True)
class SearchCommandSpec(SlashCommandSpec):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SearchCommandSpec":
        payload = dict(data or {})
        payload.setdefault("kind", "search_command")
        return cls(
            kind=_text(payload.get("kind", "search_command")),
            raw_text=_text(payload.get("raw_text", "")),
            normalized_text=_text(payload.get("normalized_text", "")),
            metadata=_copy_metadata(payload.get("metadata", {})),
            command=_text(payload.get("command", "")),
            args=_args_to_tuple(payload.get("args", ())),
        )


@dataclass(frozen=True)
class PatchCommandSpec(SlashCommandSpec):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "PatchCommandSpec":
        payload = dict(data or {})
        payload.setdefault("kind", "patch_command")
        return cls(
            kind=_text(payload.get("kind", "patch_command")),
            raw_text=_text(payload.get("raw_text", "")),
            normalized_text=_text(payload.get("normalized_text", "")),
            metadata=_copy_metadata(payload.get("metadata", {})),
            command=_text(payload.get("command", "")),
            args=_args_to_tuple(payload.get("args", ())),
        )


@dataclass(frozen=True)
class ToolCommandSpec(SlashCommandSpec):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ToolCommandSpec":
        payload = dict(data or {})
        payload.setdefault("kind", "tool_command")
        return cls(
            kind=_text(payload.get("kind", "tool_command")),
            raw_text=_text(payload.get("raw_text", "")),
            normalized_text=_text(payload.get("normalized_text", "")),
            metadata=_copy_metadata(payload.get("metadata", {})),
            command=_text(payload.get("command", "")),
            args=_args_to_tuple(payload.get("args", ())),
        )


@dataclass(frozen=True)
class AgentTaskInputSpec(InputSpec):
    title: str = ""
    summary: str = ""
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "notes", tuple(_text(item) for item in self.notes))

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "title": self.title,
                "summary": self.summary,
                "notes": list(self.notes),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "AgentTaskInputSpec":
        payload = dict(data or {})
        return cls(
            kind=_text(payload.get("kind", "agent_task_input")),
            raw_text=_text(payload.get("raw_text", "")),
            normalized_text=_text(payload.get("normalized_text", "")),
            metadata=_copy_metadata(payload.get("metadata", {})),
            title=_text(payload.get("title", "")),
            summary=_text(payload.get("summary", "")),
            notes=_tuple_texts(payload.get("notes", ())),
        )


@dataclass(frozen=True)
class FactualAnswerSpec(InputSpec):
    requires_grounding: bool = True
    requires_policy: bool = True
    topic: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "requires_grounding": self.requires_grounding,
                "requires_policy": self.requires_policy,
                "topic": self.topic,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "FactualAnswerSpec":
        payload = dict(data or {})
        return cls(
            kind=_text(payload.get("kind", "factual_answer")),
            raw_text=_text(payload.get("raw_text", "")),
            normalized_text=_text(payload.get("normalized_text", "")),
            metadata=_copy_metadata(payload.get("metadata", {})),
            requires_grounding=bool(payload.get("requires_grounding", True)),
            requires_policy=bool(payload.get("requires_policy", True)),
            topic=_text(payload.get("topic", "")),
        )


@dataclass(frozen=True)
class UnknownInputSpec(InputSpec):
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"reason": self.reason})
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "UnknownInputSpec":
        payload = dict(data or {})
        return cls(
            kind=_text(payload.get("kind", "unknown")),
            raw_text=_text(payload.get("raw_text", "")),
            normalized_text=_text(payload.get("normalized_text", "")),
            metadata=_copy_metadata(payload.get("metadata", {})),
            reason=_text(payload.get("reason", "")),
        )


_SPEC_KIND_MAP: dict[str, type[InputSpec]] = {
    "slash_command": SlashCommandSpec,
    "system_command": SystemCommandSpec,
    "fs_command": FsCommandSpec,
    "python_command": PythonCommandSpec,
    "shell_command": ShellCommandSpec,
    "memory_command": MemoryCommandSpec,
    "plugin_command": PluginCommandSpec,
    "switch_command": SwitchCommandSpec,
    "ground_command": GroundCommandSpec,
    "web_command": WebCommandSpec,
    "search_command": SearchCommandSpec,
    "patch_command": PatchCommandSpec,
    "tool_command": ToolCommandSpec,
    "agent_task_input": AgentTaskInputSpec,
    "factual_answer": FactualAnswerSpec,
    "unknown": UnknownInputSpec,
}
