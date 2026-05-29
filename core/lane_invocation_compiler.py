"""Deterministic LaneInvocation -> AgentScript compiler for read-only lanes."""
from __future__ import annotations

from typing import Any

from .agent_script import AgentScript, AgentScriptStep
from .lane_invocation import LaneInvocation


_READ_LANE_ROOT = "read"
_TREE_LANE_ROOT = "tree"
_FIND_LANE_ROOT = "find"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_lane(lane: str | None) -> str:
    return _text(lane).lstrip("/")


def compile_lane_invocation_to_agent_script(invocation: LaneInvocation) -> AgentScript:
    if not isinstance(invocation, LaneInvocation):
        raise ValueError("invocation must be a LaneInvocation")
    if not invocation.handoff_ready:
        raise ValueError("lane invocation must be handoff-ready")

    root = _normalize_lane(invocation.selected_lane)
    if root not in {_READ_LANE_ROOT, _TREE_LANE_ROOT, _FIND_LANE_ROOT}:
        raise ValueError(f"unsupported lane for AgentScript compiler: {invocation.selected_lane}")

    input_text = _text(invocation.normalized_input)
    if not input_text:
        raise ValueError("read lane invocation requires input text")

    script_metadata = {
        "input_text": input_text,
        "lane": f"/{root}",
    }
    if invocation.source:
        script_metadata["source"] = invocation.source

    command = f"/{root} {input_text}"
    return AgentScript(
        schema_version="agent_script_v1",
        metadata=script_metadata,
        nodes=(AgentScriptStep(command=command, raw=command),),
    )
