"""Deterministic, non-executing route decisions for runtime InputSpec values."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .models import (
    AgentTaskInputSpec,
    FactualAnswerSpec,
    GroundCommandSpec,
    InputSpec,
    PatchCommandSpec,
    SearchCommandSpec,
    SlashCommandSpec,
    SwitchCommandSpec,
    ToolCommandSpec,
    UnknownInputSpec,
    WebCommandSpec,
)


def _copy_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    return dict(metadata)


@dataclass(frozen=True)
class RouteDecision:
    mode: str
    handler: str
    surface: str
    allowed: bool
    reason: str
    input_kind: str
    command: str = ""
    requires_policy: bool = False
    requires_grounding: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _copy_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "handler": self.handler,
            "surface": self.surface,
            "allowed": self.allowed,
            "reason": self.reason,
            "input_kind": self.input_kind,
            "command": self.command,
            "requires_policy": self.requires_policy,
            "requires_grounding": self.requires_grounding,
            "metadata": dict(self.metadata),
        }


def route_runtime_input(spec: InputSpec) -> RouteDecision:
    metadata = dict(spec.metadata)
    command = getattr(spec, "command", "")

    if isinstance(spec, GroundCommandSpec):
        return _decision(spec, mode="ground_front_door", handler="ground", surface="ground", command=command, metadata=metadata)
    if isinstance(spec, WebCommandSpec):
        return _decision(spec, mode="web_front_door", handler="web", surface="web", command=command, metadata=metadata)
    if isinstance(spec, SearchCommandSpec):
        return _decision(spec, mode="search_front_door", handler="search", surface="search", command=command, metadata=metadata)
    if isinstance(spec, PatchCommandSpec):
        return _decision(spec, mode="patch_front_door", handler="patch", surface="patch", command=command, metadata=metadata)
    if isinstance(spec, ToolCommandSpec):
        return _decision(spec, mode="tool_front_door", handler="tool", surface="tool", command=command, metadata=metadata)
    if isinstance(spec, SwitchCommandSpec):
        return _decision(spec, mode="switch_front_door", handler="switch", surface="switch", command=command, metadata=metadata)
    if isinstance(spec, SlashCommandSpec):
        if command.lower() in {"help", "commands"}:
            return _decision(spec, mode="help", handler="help", surface="help", command=command, metadata=metadata)
        return _decision(
            spec,
            mode="unsupported_slash",
            handler="unsupported_slash",
            surface=command or "slash",
            allowed=False,
            reason="unsupported slash command",
            command=command,
            metadata=metadata,
        )
    if isinstance(spec, AgentTaskInputSpec):
        return _decision(
            spec,
            mode="agent_task",
            handler="agent_task",
            surface="agent_task",
            requires_policy=True,
            metadata=metadata,
        )
    if isinstance(spec, FactualAnswerSpec):
        return _decision(
            spec,
            mode="factual_answer",
            handler="factual_answer",
            surface="natural",
            requires_policy=True,
            requires_grounding=True,
            metadata=metadata,
        )
    if isinstance(spec, UnknownInputSpec):
        return _decision(
            spec,
            mode="unknown_input",
            handler="unknown",
            surface="unknown",
            allowed=False,
            reason=spec.reason or "unknown input",
            metadata=metadata,
        )
    return _decision(
        spec,
        mode="unknown_input",
        handler="unknown",
        surface="unknown",
        allowed=False,
        reason="unknown input kind",
        metadata=metadata,
    )


def _decision(
    spec: InputSpec,
    *,
    mode: str,
    handler: str,
    surface: str,
    command: str = "",
    allowed: bool = True,
    reason: str = "typed route decision",
    requires_policy: bool = False,
    requires_grounding: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> RouteDecision:
    return RouteDecision(
        mode=mode,
        handler=handler,
        surface=surface,
        allowed=allowed,
        reason=reason,
        input_kind=spec.kind,
        command=command,
        requires_policy=requires_policy,
        requires_grounding=requires_grounding,
        metadata=metadata,
    )
