"""Dependency-free command registry schema and fixtures.

This module is metadata only. It does not execute handlers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


VALID_PARSER_FAMILIES = (
    "runtime_decoder_simple",
    "batch_runner_shlex",
    "internal_only",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _copy_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    return dict(metadata)


def _copy_aliases(aliases: Iterable[str] | None) -> tuple[str, ...]:
    if aliases is None:
        return ()
    values = []
    for alias in aliases:
        text = _text(alias)
        if text:
            values.append(text)
    return tuple(values)


def _registration_sort_key(registration: "CommandRegistration") -> tuple[str, str, str, str]:
    return (
        registration.surface.lower(),
        registration.name.lower(),
        registration.mode.lower(),
        registration.handler_name.lower(),
    )


@dataclass(frozen=True)
class CommandRegistration:
    name: str
    surface: str
    mode: str
    handler_name: str
    description: str
    input_kind: str
    allowed_in_batch: bool
    requires_policy: bool
    requires_grounding: bool
    requires_approval: bool
    mutates_state: bool
    inspect_only: bool
    parser_family: str
    lane_type: str = ""
    uses_llm: bool = False
    requires_web: bool = False
    requires_scrape: bool = False
    output_contract: str = ""
    response_template: str = ""
    context_mode: str = ""
    may_use_grounding: bool = False
    may_use_web: bool = False
    may_use_search: bool = False
    may_use_scrape: bool = False
    default_requires_grounding: bool = False
    aliases: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name))
        object.__setattr__(self, "surface", _text(self.surface))
        object.__setattr__(self, "mode", _text(self.mode))
        object.__setattr__(self, "handler_name", _text(self.handler_name))
        object.__setattr__(self, "description", _text(self.description))
        object.__setattr__(self, "input_kind", _text(self.input_kind))
        object.__setattr__(self, "lane_type", _text(self.lane_type))
        object.__setattr__(self, "parser_family", _text(self.parser_family))
        object.__setattr__(self, "output_contract", _text(self.output_contract))
        object.__setattr__(self, "response_template", _text(self.response_template))
        object.__setattr__(self, "context_mode", _text(self.context_mode))
        object.__setattr__(self, "aliases", _copy_aliases(self.aliases))
        object.__setattr__(self, "metadata", _copy_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_in_batch": self.allowed_in_batch,
            "aliases": list(self.aliases),
            "description": self.description,
            "handler_name": self.handler_name,
            "input_kind": self.input_kind,
            "inspect_only": self.inspect_only,
            "lane_type": self.lane_type,
            "metadata": dict(self.metadata),
            "mode": self.mode,
            "mutates_state": self.mutates_state,
            "name": self.name,
            "parser_family": self.parser_family,
            "output_contract": self.output_contract,
            "response_template": self.response_template,
            "context_mode": self.context_mode,
            "may_use_grounding": self.may_use_grounding,
            "may_use_web": self.may_use_web,
            "may_use_search": self.may_use_search,
            "may_use_scrape": self.may_use_scrape,
            "default_requires_grounding": self.default_requires_grounding,
            "requires_web": self.requires_web,
            "requires_approval": self.requires_approval,
            "requires_grounding": self.requires_grounding,
            "requires_policy": self.requires_policy,
            "requires_scrape": self.requires_scrape,
            "uses_llm": self.uses_llm,
            "surface": self.surface,
        }


@dataclass(frozen=True)
class CommandRegistry:
    registrations: tuple[CommandRegistration, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "commands": [registration.to_dict() for registration in self.list_commands()],
        }

    def register_command(self, registration: CommandRegistration) -> "CommandRegistry":
        return CommandRegistry(self.registrations + (registration,))

    def get_command(self, key: str) -> CommandRegistration | None:
        needle = _text(key)
        if not needle:
            return None

        ordered = self.list_commands()
        for registration in ordered:
            if registration.name == needle:
                return registration
        for registration in ordered:
            if needle in registration.aliases:
                return registration
        return None

    def list_commands(self) -> tuple[CommandRegistration, ...]:
        return tuple(sorted(self.registrations, key=_registration_sort_key))

    def validate(self) -> None:
        validate_registry(self)


def register_command(registry: CommandRegistry, registration: CommandRegistration) -> CommandRegistry:
    return registry.register_command(registration)


def get_command(registry: CommandRegistry, key: str) -> CommandRegistration | None:
    return registry.get_command(key)


def list_commands(registry: CommandRegistry) -> tuple[CommandRegistration, ...]:
    return registry.list_commands()


def validate_registry(registry: CommandRegistry) -> None:
    seen_names: set[str] = set()
    seen_aliases: set[str] = set()

    for registration in registry.list_commands():
        if registration.parser_family not in VALID_PARSER_FAMILIES:
            raise ValueError(
                f"invalid parser family for {registration.name}: {registration.parser_family}"
            )

        if registration.name in seen_names:
            raise ValueError(f"duplicate command registration name: {registration.name}")
        seen_names.add(registration.name)

        if registration.uses_llm and not registration.output_contract:
            raise ValueError(f"uses_llm command missing output_contract: {registration.name}")

        for alias in registration.aliases:
            if alias in seen_names:
                raise ValueError(f"duplicate command alias/name collision: {alias}")
            if alias in seen_aliases:
                raise ValueError(f"duplicate command alias: {alias}")
            seen_aliases.add(alias)


def build_default_command_registry() -> CommandRegistry:
    registry = CommandRegistry(
        registrations=(
            CommandRegistration(
                name="help",
                surface="system",
                mode="help",
                handler_name="help",
                description="Show general help for command surfaces.",
                input_kind="system_command",
                allowed_in_batch=True,
                requires_policy=False,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=True,
                parser_family="internal_only",
                metadata={
                    "surface_classification": "system",
                    "registry_role": "inspect_only",
                },
            ),
            CommandRegistration(
                name="commands",
                surface="system",
                mode="help",
                handler_name="help",
                description="List available command surfaces.",
                input_kind="system_command",
                allowed_in_batch=True,
                requires_policy=False,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=True,
                parser_family="internal_only",
                metadata={
                    "surface_classification": "system",
                    "registry_role": "inspect_only",
                },
            ),
            CommandRegistration(
                name="render",
                surface="docs",
                mode="docs_render",
                handler_name="docs_render",
                description="Render command registry docs and metadata.",
                input_kind="docs_command",
                allowed_in_batch=True,
                requires_policy=False,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=True,
                parser_family="internal_only",
                metadata={
                    "command_path": "docs/render",
                    "surface_classification": "documentation",
                    "registry_role": "docs_render_front_door",
                },
            ),
            CommandRegistration(
                name="patch",
                surface="patch",
                mode="patch_front_door",
                handler_name="patch",
                description="Patch front door routed through the batch runner.",
                input_kind="patch_command",
                allowed_in_batch=True,
                requires_policy=True,
                requires_grounding=False,
                requires_approval=True,
                mutates_state=True,
                inspect_only=False,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "patch_flow",
                    "approval_hint": "explicit_patch_flow",
                    "registry_role": "execution_front_door",
                },
            ),
            CommandRegistration(
                name="llm",
                surface="llm",
                mode="llm_front_door",
                handler_name="llm",
                description="LLM configuration and preset front door.",
                input_kind="llm_command",
                allowed_in_batch=True,
                requires_policy=True,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=True,
                inspect_only=False,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "config_surface",
                    "registry_role": "configuration_front_door",
                },
            ),
            CommandRegistration(
                name="codex",
                surface="codex",
                mode="codex_front_door",
                handler_name="codex",
                description="Inspect-only Codex prompt and package front door.",
                input_kind="codex_command",
                allowed_in_batch=True,
                requires_policy=False,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=True,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "inspect_only",
                    "registry_role": "prompt_package_front_door",
                },
            ),
            CommandRegistration(
                name="web",
                surface="web",
                mode="web_front_door",
                handler_name="web",
                description="Web fetch, extract, and search front door.",
                input_kind="web_command",
                allowed_in_batch=True,
                requires_policy=True,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=False,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "network_or_extract",
                    "policy_hint": "action_dependent",
                    "registry_role": "content_front_door",
                },
            ),
            CommandRegistration(
                name="search",
                surface="search",
                mode="search_front_door",
                handler_name="search",
                description="Repo and web search front door.",
                input_kind="search_command",
                allowed_in_batch=True,
                requires_policy=True,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=False,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "search",
                    "policy_hint": "action_dependent",
                    "registry_role": "search_front_door",
                },
            ),
            CommandRegistration(
                name="ground",
                surface="ground",
                mode="ground_front_door",
                handler_name="ground",
                description="Grounded evidence, collection, and report front door.",
                input_kind="ground_command",
                allowed_in_batch=True,
                requires_policy=True,
                requires_grounding=True,
                requires_approval=False,
                mutates_state=False,
                inspect_only=True,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "evidence_surface",
                    "registry_role": "grounding_front_door",
                },
            ),
            CommandRegistration(
                name="read",
                surface="repo",
                mode="repo_front_door",
                handler_name="repo",
                description="Repo-local file read front door.",
                input_kind="repo_command",
                allowed_in_batch=True,
                requires_policy=False,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=True,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "repo_inspection",
                    "registry_role": "read_only_repo_front_door",
                },
            ),
            CommandRegistration(
                name="ls",
                surface="repo",
                mode="repo_front_door",
                handler_name="repo",
                description="Repo-local directory listing front door.",
                input_kind="repo_command",
                allowed_in_batch=True,
                requires_policy=False,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=True,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "repo_inspection",
                    "registry_role": "read_only_repo_front_door",
                },
            ),
            CommandRegistration(
                name="tree",
                surface="repo",
                mode="repo_front_door",
                handler_name="repo",
                description="Repo-local tree listing front door.",
                input_kind="repo_command",
                allowed_in_batch=True,
                requires_policy=False,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=True,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "repo_inspection",
                    "registry_role": "read_only_repo_front_door",
                },
            ),
            CommandRegistration(
                name="find",
                surface="repo",
                mode="repo_front_door",
                handler_name="repo",
                description="Repo-local file and path search front door.",
                input_kind="repo_command",
                allowed_in_batch=True,
                requires_policy=False,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=True,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "repo_inspection",
                    "registry_role": "read_only_repo_front_door",
                },
            ),
            CommandRegistration(
                name="tool",
                surface="tool",
                mode="tool_front_door",
                handler_name="tool",
                description="Policy-sensitive tool invocation front door.",
                input_kind="tool_command",
                allowed_in_batch=True,
                requires_policy=True,
                requires_grounding=False,
                requires_approval=True,
                mutates_state=False,
                inspect_only=False,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "policy_sensitive",
                    "approval_hint": "required",
                    "registry_role": "tool_gateway",
                },
            ),
            CommandRegistration(
                name="switch",
                surface="switch",
                mode="switch_front_door",
                handler_name="switch",
                description="Control-plane command-registry surface for switch helpers.",
                input_kind="switch_command",
                allowed_in_batch=True,
                requires_policy=False,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=True,
                inspect_only=False,
                parser_family="batch_runner_shlex",
                metadata={
                    "surface_classification": "control_plane",
                    "registry_role": "command_registry_surface",
                },
            ),
        ),
    )
    validate_registry(registry)
    return registry
