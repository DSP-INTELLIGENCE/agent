"""Typed lane invocation contract.

This module describes one trusted lane invocation after semantic route handoff
readiness. It does not execute, compile, or call runtime handlers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from .command_registry import CommandRegistry
from .semantic_route_diagnostics import SemanticRouteDiagnosticsSummary
from .semantic_route_handoff import SemanticRouteHandoffAssessment
from .semantic_route_threshold import SemanticRouteThresholdDecision


LANE_INVOCATION_SCHEMA_VERSION = "lane_invocation_v1"
_NO_RUNTIME_ACTIONS_STATEMENT = "no runtime actions executed"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _copy_mapping(mapping: Mapping[str, Any] | None) -> dict[str, Any]:
    if mapping is None:
        return {}
    return {key: mapping[key] for key in mapping}


def _sorted_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {key: mapping[key] for key in sorted(mapping)}


def _normalize_lane(lane: str | None) -> str:
    return _text(lane).lstrip("/")


def _decision_summary(
    diagnostics: SemanticRouteDiagnosticsSummary,
    threshold: SemanticRouteThresholdDecision,
    assessment: SemanticRouteHandoffAssessment,
) -> dict[str, Any]:
    return {
        "assessment_handoff_ready": bool(assessment.handoff_ready),
        "assessment_status": assessment.status,
        "diagnostics_status": diagnostics.status,
        "statement": _NO_RUNTIME_ACTIONS_STATEMENT,
        "threshold_reasons": list(threshold.reasons),
        "threshold_status": threshold.status,
        "threshold_trusted": bool(threshold.trusted),
    }


@dataclass(frozen=True)
class LaneInvocation:
    schema_version: str
    root: str
    slash_root: str
    raw_input: str
    normalized_input: str
    source: str
    handoff_ready: bool
    selected_lane: str
    selected_confidence: float | None
    requested_capabilities: dict[str, Any] = field(default_factory=dict)
    capability_decision: dict[str, Any] = field(default_factory=dict)
    lane_metadata: dict[str, Any] = field(default_factory=dict)
    output_contract: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _text(self.schema_version) or LANE_INVOCATION_SCHEMA_VERSION)
        object.__setattr__(self, "root", _normalize_lane(self.root))
        slash_root = _text(self.slash_root)
        object.__setattr__(self, "slash_root", slash_root if slash_root.startswith("/") else f"/{_normalize_lane(slash_root)}")
        object.__setattr__(self, "raw_input", _text(self.raw_input))
        object.__setattr__(self, "normalized_input", _text(self.normalized_input))
        object.__setattr__(self, "source", _text(self.source))
        object.__setattr__(self, "handoff_ready", bool(self.handoff_ready))
        object.__setattr__(self, "selected_lane", _text(self.selected_lane))

        if self.selected_confidence is None:
            selected_confidence = None
        else:
            try:
                selected_confidence = float(self.selected_confidence)
            except Exception:
                selected_confidence = 0.0
        object.__setattr__(self, "selected_confidence", selected_confidence)
        object.__setattr__(self, "requested_capabilities", _sorted_mapping(_copy_mapping(self.requested_capabilities)))
        object.__setattr__(self, "capability_decision", _sorted_mapping(_copy_mapping(self.capability_decision)))
        object.__setattr__(self, "lane_metadata", _sorted_mapping(_copy_mapping(self.lane_metadata)))
        object.__setattr__(self, "output_contract", _text(self.output_contract))
        object.__setattr__(self, "metadata", _sorted_mapping(_copy_mapping(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_decision": _sorted_mapping(self.capability_decision),
            "handoff_ready": self.handoff_ready,
            "lane_metadata": _sorted_mapping(self.lane_metadata),
            "metadata": _sorted_mapping(self.metadata),
            "normalized_input": self.normalized_input,
            "output_contract": self.output_contract,
            "raw_input": self.raw_input,
            "requested_capabilities": _sorted_mapping(self.requested_capabilities),
            "root": self.root,
            "schema_version": self.schema_version,
            "selected_confidence": self.selected_confidence,
            "selected_lane": self.selected_lane,
            "slash_root": self.slash_root,
            "source": self.source,
        }


def _lane_output_contract(registration: Any) -> str:
    for field_name in ("output_contract", "lane_type", "response_template"):
        value = _text(getattr(registration, field_name, ""))
        if value:
            return value
        if isinstance(registration, Mapping):
            value = _text(registration.get(field_name))
            if value:
                return value
    return ""


def build_lane_invocation_from_handoff(
    diagnostics: SemanticRouteDiagnosticsSummary,
    threshold: SemanticRouteThresholdDecision,
    assessment: SemanticRouteHandoffAssessment,
    registry: CommandRegistry,
) -> LaneInvocation | None:
    if not isinstance(diagnostics, SemanticRouteDiagnosticsSummary):
        raise ValueError("diagnostics must be a SemanticRouteDiagnosticsSummary")
    if not isinstance(threshold, SemanticRouteThresholdDecision):
        raise ValueError("threshold must be a SemanticRouteThresholdDecision")
    if not isinstance(assessment, SemanticRouteHandoffAssessment):
        raise ValueError("assessment must be a SemanticRouteHandoffAssessment")
    if not isinstance(registry, CommandRegistry):
        raise ValueError("registry must be a CommandRegistry")

    if not assessment.handoff_ready:
        return None

    selected_lane = _text(assessment.selected_lane)
    root = _normalize_lane(selected_lane)
    if not root:
        raise ValueError("handoff-ready assessment is missing a selected lane")

    registration = registry.get_command(root)
    if registration is None:
        raise ValueError(f"selected lane is not registered: {selected_lane}")

    raw_input = _text(getattr(diagnostics, "input_text", ""))
    normalized_input = raw_input.strip()
    capability_decision = _decision_summary(diagnostics, threshold, assessment)
    lane_metadata = _sorted_mapping(_copy_mapping(registration.metadata))
    output_contract = _lane_output_contract(registration)

    metadata = {
        "assessment": {
            "handoff_ready": assessment.handoff_ready,
            "status": assessment.status,
            "statement": assessment.statement,
        },
        "statement": _NO_RUNTIME_ACTIONS_STATEMENT,
        "threshold": {
            "status": threshold.status,
            "trusted": threshold.trusted,
        },
    }

    source = ""
    if isinstance(diagnostics.metadata, Mapping):
        source = _text(diagnostics.metadata.get("source"))

    return LaneInvocation(
        schema_version=LANE_INVOCATION_SCHEMA_VERSION,
        root=root,
        slash_root=selected_lane if selected_lane.startswith("/") else f"/{root}",
        raw_input=raw_input,
        normalized_input=normalized_input,
        source=source,
        handoff_ready=assessment.handoff_ready,
        selected_lane=selected_lane,
        selected_confidence=assessment.selected_confidence,
        requested_capabilities=assessment.requested_capabilities,
        capability_decision=capability_decision,
        lane_metadata=lane_metadata,
        output_contract=output_contract,
        metadata=metadata,
    )


def render_lane_invocation_json(invocation: LaneInvocation) -> str:
    return json.dumps(invocation.to_dict(), ensure_ascii=True, indent=2, sort_keys=True) + "\n"
