from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

# DATACLASSES
# ============================================================

@dataclass
class RouteDecision:
    intent: str = "chat"
    route: str = "chat"
    confidence: float = 0.0
    command: str = "chat.reply"
    args: Dict[str, Any] = field(default_factory=dict)
    requires_web: bool = False
    requires_memory: bool = False
    requires_llm_response: bool = True
    rewritten_user_request: str = ""
    reasoning_summary: str = ""
    missing_arguments: List[str] = field(default_factory=list)
    safety_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SharedPlan:
    route: str
    command: str
    user_text: str
    rewritten_text: str
    args: Dict[str, Any] = field(default_factory=dict)
    requires_llm_response: bool = True
    source_kind: str = "tui"
    decision: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DispatchResult:
    ok: bool
    handled: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GroundingQuery:
    original: str
    profile: str = "general_reference"
    wikipedia_query: str = ""
    web_query: str = ""
    required_terms: List[str] = field(default_factory=list)
    optional_terms: List[str] = field(default_factory=list)
    preferred_domains: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SourceConfidence:
    url: str
    title: str
    score: float
    accepted: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
