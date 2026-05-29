"""Inspect-only execution dispatch scaffolding.

This module turns command registry metadata into deterministic dispatch plans.
It does not execute handlers or wire runtime behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .command_registry import (
    CommandRegistry,
    CommandRegistration,
    build_default_command_registry,
    list_commands,
    validate_registry,
)
from .command_registry_loader import load_command_registry_data


_FIRST_CLASS_FAMILY_HINTS = ("web", "llm", "vision", "image", "repo", "grounding", "patch", "local_cli", "system", "docs")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _copy_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    return dict(metadata)


def _copy_args(args: Iterable[str] | None) -> tuple[str, ...]:
    if args is None:
        return ()
    values: list[str] = []
    for arg in args:
        text = _text(arg)
        if text:
            values.append(text)
    return tuple(values)


def _merge_aliases(*alias_groups: Iterable[str]) -> tuple[str, ...]:
    aliases: list[str] = []
    seen: set[str] = set()
    for alias_group in alias_groups:
        for alias in alias_group:
            text = _text(alias)
            if text and text not in seen:
                seen.add(text)
                aliases.append(text)
    return tuple(aliases)


def _merge_metadata(*metadata_groups: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for metadata in metadata_groups:
        merged.update(_copy_metadata(metadata))
    return {key: merged[key] for key in sorted(merged)}


def _merge_registration(primary: CommandRegistration, overlay: CommandRegistration) -> CommandRegistration:
    return CommandRegistration(
        name=primary.name or overlay.name,
        surface=primary.surface or overlay.surface,
        mode=primary.mode or overlay.mode,
        handler_name=primary.handler_name or overlay.handler_name,
        description=primary.description or overlay.description,
        input_kind=primary.input_kind or overlay.input_kind,
        allowed_in_batch=primary.allowed_in_batch,
        requires_policy=primary.requires_policy,
        requires_grounding=primary.requires_grounding,
        requires_approval=primary.requires_approval,
        mutates_state=primary.mutates_state,
        inspect_only=primary.inspect_only,
        parser_family=primary.parser_family or overlay.parser_family,
        lane_type=overlay.lane_type or primary.lane_type,
        uses_llm=overlay.uses_llm or primary.uses_llm,
        requires_web=overlay.requires_web or primary.requires_web,
        requires_scrape=overlay.requires_scrape or primary.requires_scrape,
        output_contract=overlay.output_contract or primary.output_contract,
        response_template=overlay.response_template or primary.response_template,
        context_mode=overlay.context_mode or primary.context_mode,
        may_use_grounding=overlay.may_use_grounding or primary.may_use_grounding,
        may_use_web=overlay.may_use_web or primary.may_use_web,
        may_use_search=overlay.may_use_search or primary.may_use_search,
        may_use_scrape=overlay.may_use_scrape or primary.may_use_scrape,
        default_requires_grounding=overlay.default_requires_grounding or primary.default_requires_grounding,
        aliases=_merge_aliases(primary.aliases, overlay.aliases),
        metadata=_merge_metadata(overlay.metadata, primary.metadata),
    )


def _merge_registries(primary: CommandRegistry, overlay: CommandRegistry) -> CommandRegistry:
    merged: dict[str, CommandRegistration] = {
        registration.name: registration for registration in list_commands(primary)
    }
    for registration in list_commands(overlay):
        existing = merged.get(registration.name)
        if existing is None:
            merged[registration.name] = registration
        else:
            merged[registration.name] = _merge_registration(existing, registration)
    return CommandRegistry(tuple(merged.values()))


def _future_family_placeholder_registrations() -> CommandRegistry:
    return CommandRegistry(
        registrations=(
            CommandRegistration(
                name="vision",
                surface="vision",
                mode="vision_front_door",
                handler_name="vision",
                description="Reserved first-class multimodal vision command family metadata.",
                input_kind="vision_command",
                allowed_in_batch=False,
                requires_policy=False,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=True,
                parser_family="internal_only",
                metadata={
                    "command_path": "/vision",
                    "registry_role": "future_family_placeholder",
                    "surface_classification": "multimodal",
                },
            ),
            CommandRegistration(
                name="image",
                surface="image",
                mode="image_front_door",
                handler_name="image",
                description="Reserved first-class multimodal image command family metadata.",
                input_kind="image_command",
                allowed_in_batch=False,
                requires_policy=False,
                requires_grounding=False,
                requires_approval=False,
                mutates_state=False,
                inspect_only=True,
                parser_family="internal_only",
                metadata={
                    "command_path": "/image",
                    "registry_role": "future_family_placeholder",
                    "surface_classification": "multimodal",
                },
            ),
        ),
    )


def build_default_dispatch_registry() -> CommandRegistry:
    """Build the metadata-only registry used by dispatch planning."""

    runtime_registry = build_default_command_registry()
    catalog_registry = load_command_registry_data()
    placeholder_registry = _future_family_placeholder_registrations()

    registry = _merge_registries(runtime_registry, catalog_registry)
    registry = _merge_registries(registry, placeholder_registry)
    validate_registry(registry)
    return registry


def _split_command_text(command: str) -> tuple[str, tuple[str, ...]]:
    text = _text(command)
    if not text:
        return "", ()
    tokens = text.split()
    if not tokens:
        return "", ()
    return tokens[0], tuple(tokens[1:])


def _canonical_command_root(command: str) -> str:
    token, _ = _split_command_text(command)
    token = token.lstrip("/")
    return token.lower()


def _candidate_lookup_keys(command: str) -> tuple[str, ...]:
    root, _ = _split_command_text(command)
    root = _text(root)
    if not root:
        return ()

    stripped = root.lstrip("/")
    lowered = stripped.lower()
    candidates = (
        root,
        stripped,
        lowered,
        f"/{stripped}",
        f"/{lowered}",
    )
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        text = _text(candidate)
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)
    return tuple(ordered)


def lookup_dispatch_registration(
    command: str,
    registry: CommandRegistry | None = None,
) -> CommandRegistration | None:
    """Look up a registry entry for a slash root or alias without executing."""

    registration, _, _ = _lookup_dispatch_registration(command, registry=registry)
    return registration


def _lookup_dispatch_registration(
    command: str,
    registry: CommandRegistry | None = None,
) -> tuple[CommandRegistration | None, str, str]:
    registry = registry or build_default_dispatch_registry()
    candidates = _candidate_lookup_keys(command)
    for candidate in candidates:
        registration = registry.get_command(candidate)
        if registration is not None:
            candidate_root = candidate.lstrip("/").lower()
            match_kind = "alias_match" if candidate_root != registration.name.lower() else "registry_match"
            return registration, match_kind, candidate
    return None, "unknown_command", _canonical_command_root(command)


def list_dispatch_registrations(
    registry: CommandRegistry | None = None,
) -> tuple[CommandRegistration, ...]:
    registry = registry or build_default_dispatch_registry()
    return list_commands(registry)


@dataclass(frozen=True)
class DispatchAdapter:
    name: str
    family: str
    kind: str
    parser_family: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name))
        object.__setattr__(self, "family", _text(self.family))
        object.__setattr__(self, "kind", _text(self.kind))
        object.__setattr__(self, "parser_family", _text(self.parser_family))
        object.__setattr__(self, "metadata", _merge_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "kind": self.kind,
            "metadata": dict(self.metadata),
            "name": self.name,
            "parser_family": self.parser_family,
        }


def _resolve_registration_family(registration: CommandRegistration) -> str:
    candidate = _text(registration.metadata.get("catalog_family")) or registration.surface or registration.name
    hint = _family_hint(candidate)
    return hint if hint != "unknown" else candidate


def resolve_dispatch_adapter(registration: CommandRegistration) -> DispatchAdapter:
    family = _resolve_registration_family(registration)
    kind = "future_family_placeholder" if registration.metadata.get("registry_role") == "future_family_placeholder" else "registry_surface_adapter"
    if family in {"web", "llm", "vision", "image"}:
        kind = "first_class_family_adapter"
    elif registration.parser_family == "batch_runner_shlex":
        kind = "batch_runner_adapter"
    elif registration.parser_family == "runtime_decoder_simple":
        kind = "runtime_decoder_adapter"

    return DispatchAdapter(
        name=f"dispatch.{family}",
        family=family,
        kind=kind,
        parser_family=registration.parser_family,
        metadata={
            "handler_name": registration.handler_name,
            "registry_role": registration.metadata.get("registry_role", ""),
            "surface": registration.surface,
        },
    )


@dataclass(frozen=True)
class DispatchPlan:
    command: str
    command_root: str
    args: tuple[str, ...]
    allowed: bool
    reason: str
    registry_name: str
    surface: str
    family: str
    mode: str
    handler_name: str
    input_kind: str
    parser_family: str
    allowed_in_batch: bool
    requires_policy: bool
    requires_grounding: bool
    requires_approval: bool
    mutates_state: bool
    inspect_only: bool
    adapter: DispatchAdapter
    registration: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _text(self.command))
        object.__setattr__(self, "command_root", _text(self.command_root).lstrip("/").lower())
        object.__setattr__(self, "args", _copy_args(self.args))
        object.__setattr__(self, "registry_name", _text(self.registry_name))
        object.__setattr__(self, "surface", _text(self.surface))
        object.__setattr__(self, "family", _text(self.family))
        object.__setattr__(self, "mode", _text(self.mode))
        object.__setattr__(self, "handler_name", _text(self.handler_name))
        object.__setattr__(self, "input_kind", _text(self.input_kind))
        object.__setattr__(self, "parser_family", _text(self.parser_family))
        object.__setattr__(self, "metadata", _merge_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter.to_dict(),
            "allowed": self.allowed,
            "allowed_in_batch": self.allowed_in_batch,
            "args": list(self.args),
            "command": self.command,
            "command_root": self.command_root,
            "family": self.family,
            "handler_name": self.handler_name,
            "input_kind": self.input_kind,
            "inspect_only": self.inspect_only,
            "metadata": dict(self.metadata),
            "mode": self.mode,
            "reason": self.reason,
            "registry_name": self.registry_name,
            "registration": dict(self.registration) if self.registration is not None else None,
            "requires_approval": self.requires_approval,
            "requires_grounding": self.requires_grounding,
            "requires_policy": self.requires_policy,
            "surface": self.surface,
            "mutates_state": self.mutates_state,
            "parser_family": self.parser_family,
        }


def _family_hint(command_root: str) -> str:
    if command_root in {"web", "llm", "vision", "image"}:
        return command_root
    if command_root in {"find", "grep", "ls", "tree"}:
        return "repo"
    if command_root in {"git", "python", "shell"}:
        return "local_cli"
    if command_root in {"ground"}:
        return "grounding"
    if command_root in {"patch"}:
        return "patch"
    if command_root in {"help", "commands"}:
        return "system"
    if command_root in {"render"}:
        return "docs"
    if command_root in _FIRST_CLASS_FAMILY_HINTS:
        return command_root
    return "unknown"


def build_dispatch_plan(
    command: str,
    args: Iterable[str] | None = None,
    registry: CommandRegistry | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> DispatchPlan:
    """Build an inspect-only execution dispatch plan.

    The plan is metadata only. It does not execute handlers.
    If args are omitted, simple whitespace tokenization is used to split the
    command text into a root plus trailing args.
    """

    registry = registry or build_default_dispatch_registry()
    registration, match_kind, matched_key = _lookup_dispatch_registration(command, registry=registry)
    command_root = _canonical_command_root(command)
    parsed_command = _text(command)
    parsed_args = _copy_args(args)
    if args is None:
        _, parsed_args = _split_command_text(command)
        parsed_command = _text(command)

    if registration is None:
        family = _family_hint(command_root)
        return DispatchPlan(
            command=parsed_command,
            command_root=command_root,
            args=parsed_args,
            allowed=False,
            reason="unknown_command",
            registry_name=command_root,
            surface=family if family != "unknown" else "unknown",
            family=family,
            mode="unsupported_command",
            handler_name="",
            input_kind="unknown_command",
            parser_family="internal_only",
            allowed_in_batch=False,
            requires_policy=False,
            requires_grounding=False,
            requires_approval=False,
            mutates_state=False,
            inspect_only=True,
            adapter=DispatchAdapter(
                name=f"dispatch.{family}",
                family=family,
                kind="unresolved_command",
                parser_family="internal_only",
                metadata={
                    "command_root": command_root,
                    "lookup_status": "unknown_command",
                },
            ),
            registration=None,
            metadata={
                **(_copy_metadata(metadata)),
                "lookup_status": "unknown_command",
                "matched_key": matched_key,
                "match_kind": match_kind,
                "registry_source": "build_default_dispatch_registry",
            },
        )

    adapter = resolve_dispatch_adapter(registration)
    family = _resolve_registration_family(registration)
    return DispatchPlan(
        command=parsed_command,
        command_root=command_root,
        args=parsed_args,
        allowed=True,
        reason="alias_match" if match_kind == "alias_match" else "registry_match",
        registry_name=registration.name,
        surface=registration.surface,
        family=family,
        mode=registration.mode,
        handler_name=registration.handler_name,
        input_kind=registration.input_kind,
        parser_family=registration.parser_family,
        allowed_in_batch=registration.allowed_in_batch,
        requires_policy=registration.requires_policy,
        requires_grounding=registration.requires_grounding,
        requires_approval=registration.requires_approval,
        mutates_state=registration.mutates_state,
        inspect_only=registration.inspect_only,
        adapter=adapter,
        registration=registration.to_dict(),
        metadata={
            **(_copy_metadata(metadata)),
            "lookup_status": "registered_command",
            "matched_key": matched_key,
            "match_kind": match_kind,
            "registry_source": "build_default_dispatch_registry",
        },
    )


__all__ = [
    "DispatchAdapter",
    "DispatchPlan",
    "build_default_dispatch_registry",
    "build_dispatch_plan",
    "list_dispatch_registrations",
    "lookup_dispatch_registration",
    "resolve_dispatch_adapter",
]
