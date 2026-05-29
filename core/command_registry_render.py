"""Deterministic render helpers for command registry metadata.

These helpers are inspect-only. They do not execute handlers or imply
runtime authority.
"""
from __future__ import annotations

import json
from typing import Any

from .command_registry import CommandRegistration, CommandRegistry


def _metadata_text(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, sort_keys=True, indent=2)


def render_registry_json(registry: CommandRegistry) -> str:
    return json.dumps(registry.to_dict(), sort_keys=True, indent=2)


def render_command_markdown(registration: CommandRegistration) -> str:
    lines = [
        f"# {registration.name}",
        "",
        f"- name: `{registration.name}`",
        f"- surface: `{registration.surface}`",
        f"- mode: `{registration.mode}`",
        f"- handler_name: `{registration.handler_name}`",
        f"- parser_family: `{registration.parser_family}`",
        f"- lane_type: `{registration.lane_type}`",
        f"- uses_llm: `{registration.uses_llm}`",
        f"- requires_web: `{registration.requires_web}`",
        f"- requires_scrape: `{registration.requires_scrape}`",
        f"- output_contract: `{registration.output_contract}`",
        f"- response_template: `{registration.response_template}`",
        f"- context_mode: `{registration.context_mode}`",
        f"- may_use_grounding: `{registration.may_use_grounding}`",
        f"- may_use_web: `{registration.may_use_web}`",
        f"- may_use_search: `{registration.may_use_search}`",
        f"- may_use_scrape: `{registration.may_use_scrape}`",
        f"- default_requires_grounding: `{registration.default_requires_grounding}`",
        f"- inspect_only: `{registration.inspect_only}`",
        f"- mutates_state: `{registration.mutates_state}`",
        f"- requires_policy: `{registration.requires_policy}`",
        f"- requires_grounding: `{registration.requires_grounding}`",
        f"- requires_approval: `{registration.requires_approval}`",
        f"- aliases: `{', '.join(registration.aliases) if registration.aliases else '[]'}`",
        f"- description: {registration.description}",
        "",
        "## Metadata",
        "",
        "```json",
        _metadata_text(registration.metadata),
        "```",
    ]
    return "\n".join(lines) + "\n"


def render_registry_markdown(registry: CommandRegistry) -> str:
    registrations = registry.list_commands()
    lines: list[str] = [
        "# Command Registry",
        "",
        "Inspect-only command registry metadata.",
        "",
    ]
    for index, registration in enumerate(registrations):
        if index:
            lines.extend(["", "---", ""])
        lines.append(render_command_markdown(registration).rstrip("\n"))
    return "\n".join(lines) + "\n"
