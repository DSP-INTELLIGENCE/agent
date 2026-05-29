"""Deterministic lane capability authorization checks.

This module is metadata-only. It validates whether a proposed lane is
authorized for the capabilities the proposal wants to use. It does not execute
lanes or invoke policy, routing, grounding, web, or scrape behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .command_registry import CommandRegistration


@dataclass(frozen=True)
class LaneCapabilityRequest:
    uses_llm: bool = False
    requires_grounding: bool = False
    requires_web: bool = False
    requires_search: bool = False
    requires_scrape: bool = False
    requires_approval: bool = False
    mutates_state: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutates_state": self.mutates_state,
            "requires_approval": self.requires_approval,
            "requires_grounding": self.requires_grounding,
            "requires_scrape": self.requires_scrape,
            "requires_search": self.requires_search,
            "requires_web": self.requires_web,
            "uses_llm": self.uses_llm,
        }


@dataclass(frozen=True)
class LaneCapabilityDecision:
    allowed: bool
    lane_name: str
    reasons: tuple[str, ...] = ()
    request: LaneCapabilityRequest = field(default_factory=LaneCapabilityRequest)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "lane_name": self.lane_name,
            "reasons": list(self.reasons),
            "request": self.request.to_dict(),
        }


def _authorize_capability(
    *,
    request_enabled: bool,
    lane_allowed: bool,
    lane_may_use: bool = False,
    label: str,
    reasons: list[str],
) -> None:
    if not request_enabled:
        return
    if lane_allowed or lane_may_use:
        return
    reasons.append(f"{label} capability not authorized by lane contract")


def validate_lane_capabilities(
    registration: CommandRegistration,
    request: LaneCapabilityRequest,
) -> LaneCapabilityDecision:
    reasons: list[str] = []

    _authorize_capability(
        request_enabled=request.uses_llm,
        lane_allowed=registration.uses_llm,
        label="uses_llm",
        reasons=reasons,
    )
    _authorize_capability(
        request_enabled=request.requires_grounding,
        lane_allowed=registration.requires_grounding,
        lane_may_use=registration.may_use_grounding,
        label="requires_grounding",
        reasons=reasons,
    )
    _authorize_capability(
        request_enabled=request.requires_web,
        lane_allowed=registration.requires_web,
        lane_may_use=registration.may_use_web,
        label="requires_web",
        reasons=reasons,
    )
    _authorize_capability(
        request_enabled=request.requires_search,
        lane_allowed=False,
        lane_may_use=registration.may_use_search,
        label="requires_search",
        reasons=reasons,
    )
    _authorize_capability(
        request_enabled=request.requires_scrape,
        lane_allowed=registration.requires_scrape,
        lane_may_use=registration.may_use_scrape,
        label="requires_scrape",
        reasons=reasons,
    )
    _authorize_capability(
        request_enabled=request.requires_approval,
        lane_allowed=registration.requires_approval,
        label="requires_approval",
        reasons=reasons,
    )
    _authorize_capability(
        request_enabled=request.mutates_state,
        lane_allowed=registration.mutates_state,
        label="mutates_state",
        reasons=reasons,
    )

    return LaneCapabilityDecision(
        allowed=not reasons,
        lane_name=registration.name,
        reasons=tuple(reasons),
        request=request,
    )
