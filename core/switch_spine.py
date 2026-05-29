"""Minimal switch control-plane spine.

This module is intentionally small and dependency-free.  It does not execute
tools, call providers, edit files, or run shell commands.  It only loads
capability binding records and resolves whether a requested capability is
visible, enabled, plannable, dispatchable, and bound to a backend/provider/tool.

Domain front doors such as /image, /audio, /llm, /ai, and aliases such as /sd
should normalize user intent to a capability_id, then call this resolver before
building execution plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import argparse
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


DEFAULT_SWITCH_CATALOG = Path("data_agent/switches/capabilities.seed.json")


class SwitchSpineError(ValueError):
    """Raised when a switch catalog or binding is malformed."""


@dataclass(frozen=True)
class CapabilityBinding:
    """A capability-to-backend/provider/tool binding record."""

    capability_id: str
    domain: str = ""
    front_doors: Sequence[str] = field(default_factory=tuple)
    enabled: bool = False
    visible: bool = True
    plannable: bool = True
    dispatchable: bool = False
    selected_backend: Optional[str] = None
    allowed_backends: Sequence[str] = field(default_factory=tuple)
    provider_hint: Optional[str] = None
    tool_manifest: Optional[str] = None
    tool_program: Optional[str] = None
    requires_switches: Sequence[str] = field(default_factory=tuple)
    risk: str = "unknown"
    policy: Optional[str] = None
    dry_run_default: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "CapabilityBinding":
        capability_id = str(raw.get("capability_id") or "").strip()
        if not capability_id:
            raise SwitchSpineError("capability binding is missing capability_id")

        allowed_backends = _as_str_tuple(raw.get("allowed_backends", ()))
        selected_backend = _optional_str(raw.get("selected_backend"))

        return cls(
            capability_id=capability_id,
            domain=str(raw.get("domain") or "").strip(),
            front_doors=_as_str_tuple(raw.get("front_doors", ())),
            enabled=_as_bool(raw.get("enabled", False)),
            visible=_as_bool(raw.get("visible", True)),
            plannable=_as_bool(raw.get("plannable", True)),
            dispatchable=_as_bool(raw.get("dispatchable", False)),
            selected_backend=selected_backend,
            allowed_backends=allowed_backends,
            provider_hint=_optional_str(raw.get("provider_hint")),
            tool_manifest=_optional_str(raw.get("tool_manifest")),
            tool_program=_optional_str(raw.get("tool_program")),
            requires_switches=_as_str_tuple(raw.get("requires_switches", ())),
            risk=str(raw.get("risk") or "unknown").strip(),
            policy=_optional_str(raw.get("policy")),
            dry_run_default=_as_bool(raw.get("dry_run_default", True)),
            metadata=dict(raw.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "domain": self.domain,
            "front_doors": list(self.front_doors),
            "enabled": self.enabled,
            "visible": self.visible,
            "plannable": self.plannable,
            "dispatchable": self.dispatchable,
            "selected_backend": self.selected_backend,
            "allowed_backends": list(self.allowed_backends),
            "provider_hint": self.provider_hint,
            "tool_manifest": self.tool_manifest,
            "tool_program": self.tool_program,
            "requires_switches": list(self.requires_switches),
            "risk": self.risk,
            "policy": self.policy,
            "dry_run_default": self.dry_run_default,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CapabilityResolution:
    """Result of resolving a capability through the switch spine."""

    capability_id: str
    found: bool
    visible: bool = False
    enabled: bool = False
    plannable: bool = False
    dispatchable: bool = False
    plan_allowed: bool = False
    dispatch_allowed: bool = False
    selected_backend: Optional[str] = None
    provider_hint: Optional[str] = None
    tool_manifest: Optional[str] = None
    tool_program: Optional[str] = None
    risk: str = "unknown"
    policy: Optional[str] = None
    dry_run_default: bool = True
    required_switches: Sequence[str] = field(default_factory=tuple)
    missing_required_switches: Sequence[str] = field(default_factory=tuple)
    disabled_required_switches: Sequence[str] = field(default_factory=tuple)
    plan_blocked_reason: Optional[str] = None
    dispatch_blocked_reason: Optional[str] = None
    blocked_reason: Optional[str] = None
    binding: Optional[CapabilityBinding] = None

    @property
    def blocked(self) -> bool:
        return self.blocked_reason is not None

    @property
    def plan_blocked(self) -> bool:
        return self.plan_blocked_reason is not None

    @property
    def dispatch_blocked(self) -> bool:
        return self.dispatch_blocked_reason is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "found": self.found,
            "visible": self.visible,
            "enabled": self.enabled,
            "plannable": self.plannable,
            "dispatchable": self.dispatchable,
            "plan_allowed": self.plan_allowed,
            "dispatch_allowed": self.dispatch_allowed,
            "selected_backend": self.selected_backend,
            "provider_hint": self.provider_hint,
            "tool_manifest": self.tool_manifest,
            "tool_program": self.tool_program,
            "risk": self.risk,
            "policy": self.policy,
            "dry_run_default": self.dry_run_default,
            "required_switches": list(self.required_switches),
            "missing_required_switches": list(self.missing_required_switches),
            "disabled_required_switches": list(self.disabled_required_switches),
            "plan_blocked_reason": self.plan_blocked_reason,
            "dispatch_blocked_reason": self.dispatch_blocked_reason,
            "blocked_reason": self.blocked_reason,
            "binding": self.binding.to_dict() if self.binding else None,
        }


def load_capability_bindings(path: Path | str = DEFAULT_SWITCH_CATALOG) -> Dict[str, CapabilityBinding]:
    """Load capability bindings from a JSON catalog.

    The catalog can be either a list of binding objects or an object with a
    top-level ``capabilities`` list.
    """

    catalog_path = Path(path)
    with catalog_path.open("r", encoding="utf-8") as handle:
        raw_catalog = json.load(handle)

    if isinstance(raw_catalog, Mapping):
        raw_bindings = raw_catalog.get("capabilities")
    else:
        raw_bindings = raw_catalog

    if not isinstance(raw_bindings, list):
        raise SwitchSpineError("switch catalog must be a list or contain a capabilities list")

    bindings: Dict[str, CapabilityBinding] = {}
    for index, raw in enumerate(raw_bindings):
        if not isinstance(raw, Mapping):
            raise SwitchSpineError(f"switch catalog entry {index} is not an object")
        binding = CapabilityBinding.from_mapping(raw)
        if binding.capability_id in bindings:
            raise SwitchSpineError(f"duplicate capability_id: {binding.capability_id}")
        bindings[binding.capability_id] = binding

    return bindings


def resolve_capability(
    capability_id: str,
    bindings: Mapping[str, CapabilityBinding],
) -> CapabilityResolution:
    """Resolve a capability ID through loaded switch bindings."""

    requested_id = str(capability_id or "").strip()
    if not requested_id:
        return CapabilityResolution(
            capability_id="",
            found=False,
            blocked_reason="missing capability_id",
        )

    binding = bindings.get(requested_id)
    if binding is None:
        return CapabilityResolution(
            capability_id=requested_id,
            found=False,
            blocked_reason=f"capability not found: {requested_id}",
        )

    missing_required: List[str] = []
    disabled_required: List[str] = []
    for required_id in binding.requires_switches:
        required_binding = bindings.get(required_id)
        if required_binding is None:
            missing_required.append(required_id)
            continue
        if not required_binding.enabled:
            disabled_required.append(required_id)

    plan_blocked_reason = _plan_blocked_reason(binding)
    plan_allowed = plan_blocked_reason is None

    dispatch_blocked_reason = _dispatch_blocked_reason(
        binding,
        plan_blocked_reason,
        missing_required,
        disabled_required,
    )
    dispatch_allowed = dispatch_blocked_reason is None

    return CapabilityResolution(
        capability_id=binding.capability_id,
        found=True,
        visible=binding.visible,
        enabled=binding.enabled,
        plannable=binding.plannable,
        dispatchable=binding.dispatchable,
        plan_allowed=plan_allowed,
        dispatch_allowed=dispatch_allowed,
        selected_backend=binding.selected_backend,
        provider_hint=binding.provider_hint,
        tool_manifest=binding.tool_manifest,
        tool_program=binding.tool_program,
        risk=binding.risk,
        policy=binding.policy,
        dry_run_default=binding.dry_run_default,
        required_switches=tuple(binding.requires_switches),
        missing_required_switches=tuple(missing_required),
        disabled_required_switches=tuple(disabled_required),
        plan_blocked_reason=plan_blocked_reason,
        dispatch_blocked_reason=dispatch_blocked_reason,
        blocked_reason=dispatch_blocked_reason or plan_blocked_reason,
        binding=binding,
    )


def list_capabilities(
    bindings: Mapping[str, CapabilityBinding],
    *,
    domain: Optional[str] = None,
    visible_only: bool = False,
) -> List[CapabilityBinding]:
    """Return capability bindings, optionally filtered by domain/visibility."""

    result: List[CapabilityBinding] = []
    for binding in bindings.values():
        if domain and binding.domain != domain:
            continue
        if visible_only and not binding.visible:
            continue
        result.append(binding)
    return sorted(result, key=lambda item: item.capability_id)


def _plan_blocked_reason(binding: CapabilityBinding) -> Optional[str]:
    """Return the reason a capability cannot even produce a safe plan."""

    if not binding.visible:
        return f"capability is hidden: {binding.capability_id}"
    if not binding.enabled:
        return f"capability is disabled: {binding.capability_id}"
    if not binding.plannable:
        return f"capability is not plannable: {binding.capability_id}"
    if binding.selected_backend and binding.allowed_backends:
        if binding.selected_backend not in set(binding.allowed_backends):
            return (
                f"selected backend {binding.selected_backend!r} is not allowed for "
                f"{binding.capability_id}"
            )
    return None


def _dispatch_blocked_reason(
    binding: CapabilityBinding,
    plan_blocked_reason: Optional[str],
    missing_required: Sequence[str],
    disabled_required: Sequence[str],
) -> Optional[str]:
    """Return the reason a capability cannot dispatch to execution.

    Dispatch is stricter than planning.  A domain front door can build and show
    a plan even when execution is blocked by missing/disabled required switches,
    but it cannot dispatch until those requirements and the dispatchable flag
    allow it.
    """

    if plan_blocked_reason:
        return plan_blocked_reason
    if missing_required:
        return "missing required switches: " + ", ".join(missing_required)
    if disabled_required:
        return "disabled required switches: " + ", ".join(disabled_required)
    if not binding.dispatchable:
        return f"capability is not dispatchable: {binding.capability_id}"
    return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_str_tuple(value: Any) -> Sequence[str]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, Iterable):
        return (str(value),)
    return tuple(str(item).strip() for item in value if str(item).strip())


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve agent switch capabilities.")
    parser.add_argument("capability_id", nargs="?", help="Capability ID to resolve, such as images.generate")
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_SWITCH_CATALOG),
        help="Path to switch capability catalog JSON",
    )
    parser.add_argument("--list", action="store_true", help="List capabilities instead of resolving one")
    parser.add_argument("--domain", help="Optional domain filter for --list")
    args = parser.parse_args(argv)

    bindings = load_capability_bindings(args.catalog)

    if args.list:
        payload = [binding.to_dict() for binding in list_capabilities(bindings, domain=args.domain)]
    else:
        if not args.capability_id:
            parser.error("capability_id is required unless --list is used")
        payload = resolve_capability(args.capability_id, bindings).to_dict()

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
