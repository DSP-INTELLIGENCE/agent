"""Deterministic render helpers for execution dispatch plans.

These helpers are inspect-only. They do not execute handlers or imply runtime
authority.
"""
from __future__ import annotations

import json
from typing import Any

from .execution_dispatch import DispatchAdapter, DispatchPlan


def _metadata_text(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, sort_keys=True, indent=2)


def render_dispatch_plan_json(plan: DispatchPlan) -> str:
    return json.dumps(plan.to_dict(), sort_keys=True, indent=2)


def render_dispatch_adapter_markdown(adapter: DispatchAdapter) -> str:
    lines = [
        f"### {adapter.name}",
        "",
        f"- name: `{adapter.name}`",
        f"- family: `{adapter.family}`",
        f"- kind: `{adapter.kind}`",
        f"- parser_family: `{adapter.parser_family}`",
        "",
        "```json",
        _metadata_text(adapter.metadata),
        "```",
    ]
    return "\n".join(lines) + "\n"


def render_dispatch_plan_markdown(plan: DispatchPlan) -> str:
    lines = [
        f"# Dispatch Plan: {plan.command_root or plan.command}",
        "",
        f"- command: `{plan.command}`",
        f"- command_root: `{plan.command_root}`",
        f"- registry_name: `{plan.registry_name}`",
        f"- surface: `{plan.surface}`",
        f"- family: `{plan.family}`",
        f"- mode: `{plan.mode}`",
        f"- handler_name: `{plan.handler_name}`",
        f"- input_kind: `{plan.input_kind}`",
        f"- parser_family: `{plan.parser_family}`",
        f"- allowed: `{plan.allowed}`",
        f"- allowed_in_batch: `{plan.allowed_in_batch}`",
        f"- requires_policy: `{plan.requires_policy}`",
        f"- requires_grounding: `{plan.requires_grounding}`",
        f"- requires_approval: `{plan.requires_approval}`",
        f"- mutates_state: `{plan.mutates_state}`",
        f"- inspect_only: `{plan.inspect_only}`",
        f"- reason: `{plan.reason}`",
        f"- args: `{', '.join(plan.args) if plan.args else '[]'}`",
        "",
        "## Adapter",
        "",
        render_dispatch_adapter_markdown(plan.adapter).rstrip("\n"),
        "",
    ]
    if plan.registration is not None:
        lines.extend(
            [
                "## Registration",
                "",
                "```json",
                _metadata_text(plan.registration),
                "```",
                "",
            ]
        )
    if plan.metadata:
        lines.extend(
            [
                "## Metadata",
                "",
                "```json",
                _metadata_text(plan.metadata),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip("\n") + "\n"


__all__ = [
    "render_dispatch_adapter_markdown",
    "render_dispatch_plan_json",
    "render_dispatch_plan_markdown",
]
