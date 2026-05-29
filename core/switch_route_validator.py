from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


DEFAULT_SWITCH_CATALOG = Path("data_agent/switches/linux_cli_switches.json")
DEFAULT_SWITCH_PROFILES = Path("data_agent/switches/switch_profiles.json")


@dataclass(frozen=True)
class SwitchRouteValidation:
    allowed: bool
    surface: str
    command: str
    reason: str
    profile: str = "safe"
    switch_id: str = ""
    risk: str = ""
    persistence: str = ""
    requires_root: bool = False
    dry_run_required: bool = False
    blockers: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "surface": self.surface,
            "command": self.command,
            "reason": self.reason,
            "profile": self.profile,
            "switch_id": self.switch_id,
            "risk": self.risk,
            "persistence": self.persistence,
            "requires_root": self.requires_root,
            "dry_run_required": self.dry_run_required,
            "blockers": list(self.blockers),
            "notes": list(self.notes),
        }

    def format_plan_block(self) -> str:
        status = "allowed" if self.allowed else "blocked"
        lines = [
            "Switch route validation:",
            f"- status: {status}",
            f"- surface: {self.surface}",
            f"- command: {self.command}",
            f"- profile: {self.profile}",
            f"- reason: {self.reason}",
        ]
        if self.switch_id:
            lines.append(f"- switch_id: {self.switch_id}")
        if self.risk:
            lines.append(f"- risk: {self.risk}")
        if self.persistence:
            lines.append(f"- persistence: {self.persistence}")
        lines.append(f"- requires_root: {str(self.requires_root).lower()}")
        lines.append(f"- dry_run_required: {str(self.dry_run_required).lower()}")
        if self.blockers:
            lines.append("- blockers:")
            lines.extend(f"  - {item}" for item in self.blockers)
        if self.notes:
            lines.append("- notes:")
            lines.extend(f"  - {item}" for item in self.notes)
        return "\n".join(lines)


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def load_switches(path: Path = DEFAULT_SWITCH_CATALOG) -> Dict[str, Dict[str, Any]]:
    data = _load_json(path)
    rows = data.get("switches", [])
    if not isinstance(rows, list):
        raise ValueError("switch catalog must contain switches list")
    switches: Dict[str, Dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        switch_id = str(item.get("id") or "").strip()
        if switch_id:
            switches[switch_id] = item
    return switches


def load_profiles(path: Path = DEFAULT_SWITCH_PROFILES) -> Dict[str, Dict[str, Any]]:
    data = _load_json(path)
    rows = data.get("profiles", [])
    if not isinstance(rows, list):
        raise ValueError("switch profiles must contain profiles list")
    profiles: Dict[str, Dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        profile_id = str(item.get("id") or "").strip()
        if profile_id:
            profiles[profile_id] = item
    return profiles


class SwitchRouteValidator:
    """Plan-time validator for slash surfaces and switch/profile state.

    This module does not execute commands, mutate runtime state, apply profiles,
    perform live reads, call sudo, or access the network.
    """

    APPLY_WORDS = {
        "apply",
        "rollback",
        "sudo",
        "write",
        "restart",
        "enable",
        "disable",
        "install",
        "remove",
        "delete",
    }
    PROFILE_MUTATION_WORDS = {
        "apply",
        "set",
        "use",
        "activate",
        "enable",
        "disable",
        "on",
        "off",
        "write",
        "delete",
    }

    def __init__(
        self,
        *,
        switches: Optional[Mapping[str, Mapping[str, Any]]] = None,
        profiles: Optional[Mapping[str, Mapping[str, Any]]] = None,
        profile: str = "safe",
    ):
        self.switches: Dict[str, Mapping[str, Any]] = dict(switches or load_switches())
        self.profiles: Dict[str, Mapping[str, Any]] = dict(profiles or load_profiles())
        self.profile = profile if profile in self.profiles else "safe"

    @property
    def profile_switches(self) -> Mapping[str, Any]:
        profile = self.profiles.get(self.profile, {})
        switches = profile.get("switches", {})
        return switches if isinstance(switches, dict) else {}

    def _profile_enabled(self, key: str, default: bool = False) -> bool:
        value = self.profile_switches.get(key, default)
        return bool(value)

    def validate_text(self, text: str) -> SwitchRouteValidation:
        raw = str(text or "").strip()
        if not raw:
            return SwitchRouteValidation(
                True,
                "chat",
                "",
                "empty input has no switch-route effect",
                profile=self.profile,
            )

        try:
            tokens = shlex.split(raw)
        except ValueError as exc:
            return SwitchRouteValidation(
                False,
                "unknown",
                raw,
                f"could not parse command: {exc}",
                profile=self.profile,
                blockers=["invalid shell-like quoting"],
            )

        if not tokens:
            return SwitchRouteValidation(True, "chat", "", "no command", profile=self.profile)

        surface = tokens[0]
        args = tokens[1:]

        if surface == "/switch":
            return self._validate_switch(args)
        if surface == "/llm":
            return self._validate_llm(args)
        if surface == "/tool":
            return self._validate_tool(args)
        if surface == "/plan":
            return SwitchRouteValidation(
                True,
                "/plan",
                "plan",
                "plan inspection is allowed and must not execute tools",
                profile=self.profile,
                notes=["plan-only"],
            )
        if surface == "/web":
            return self._validate_family("/web", "web.live_enabled", args)
        if surface == "/shell":
            return self._validate_family("/shell", "shell.enabled", args)
        if surface == "/python":
            return self._validate_family("/python", "python.enabled", args)
        if surface == "/fs":
            return self._validate_family("/fs", "fs.read_enabled", args)
        if surface == "/git":
            return self._validate_git(args)
        if surface in {"/audio", "/speech", "/dsp", "/image"}:
            return self._validate_media(surface, args)

        return SwitchRouteValidation(
            True,
            surface,
            "unknown",
            "surface is not switch-gated yet",
            profile=self.profile,
            notes=["validator advisory only"],
        )

    def _validate_switch(self, args: List[str]) -> SwitchRouteValidation:
        command = args[0] if args else "status"

        if command == "profile":
            return self._validate_switch_profile(args[1:])

        allowed = {"status", "list", "show", "plan", "read", "apply-gate"}
        if command not in allowed:
            return SwitchRouteValidation(
                False,
                "/switch",
                command,
                "unsupported /switch command",
                profile=self.profile,
                blockers=["allowed commands: status, list, show, plan, read, apply-gate"],
            )

        if any(token in self.APPLY_WORDS for token in args):
            return SwitchRouteValidation(
                False,
                "/switch",
                command,
                "mutation words are blocked on /switch",
                profile=self.profile,
                blockers=["apply/rollback/sudo/write operations are disabled"],
            )

        switch_id = args[1] if len(args) > 1 and command in {"show", "plan", "read", "apply-gate"} else ""
        switch = self.switches.get(switch_id, {}) if switch_id else {}

        if command in {"show", "plan", "read"} and not switch:
            return SwitchRouteValidation(
                False,
                "/switch",
                command,
                "unknown switch id",
                profile=self.profile,
                switch_id=switch_id,
                blockers=[f"switch not found: {switch_id}"],
            )

        if command == "apply-gate":
            return SwitchRouteValidation(
                False,
                "/switch",
                command,
                "switch apply gate is plan-only; apply execution remains disabled",
                profile=self.profile,
                switch_id=switch_id,
                risk=str(switch.get("risk") or ""),
                persistence=str(switch.get("persistence") or ""),
                requires_root=bool(switch.get("requires_root", False)),
                dry_run_required=False,
                blockers=[
                    "apply execution is disabled",
                    "runtime mutation is disabled",
                    "persistent switch state is disabled",
                ],
                notes=["policy-gate-only", "no apply execution", "no runtime mutation"],
            )

        return SwitchRouteValidation(
            True,
            "/switch",
            command,
            "switch inspection is allowed",
            profile=self.profile,
            switch_id=switch_id,
            risk=str(switch.get("risk") or ""),
            persistence=str(switch.get("persistence") or ""),
            requires_root=bool(switch.get("requires_root", False)),
            dry_run_required=(command == "read"),
            notes=["read-only/plan-only surface"],
        )

    def _validate_switch_profile(self, args: List[str]) -> SwitchRouteValidation:
        command = args[0] if args else "status"
        allowed = {"status", "list", "show", "validate", "plan-apply"}

        if command not in allowed:
            return SwitchRouteValidation(
                False,
                "/switch profile",
                command,
                "unsupported /switch profile command",
                profile=self.profile,
                blockers=["allowed commands: status, list, show, validate, plan-apply"],
            )

        if any(token in self.PROFILE_MUTATION_WORDS for token in args):
            return SwitchRouteValidation(
                False,
                "/switch profile",
                command,
                "profile mutation is blocked",
                profile=self.profile,
                blockers=["profile apply/use/set/activate is disabled"],
            )

        profile_id = args[1] if len(args) > 1 and command in {"show", "plan-apply"} else ""
        if profile_id and profile_id not in self.profiles:
            return SwitchRouteValidation(
                False,
                "/switch profile",
                command,
                "unknown profile id",
                profile=self.profile,
                blockers=[f"profile not found: {profile_id}"],
            )

        if command == "plan-apply":
            return SwitchRouteValidation(
                True,
                "/switch profile",
                command,
                "profile apply planning is allowed without runtime mutation",
                profile=self.profile,
                notes=["plan-only", "no profile activation", "no runtime mutation", "no persistence"],
            )

        return SwitchRouteValidation(
            True,
            "/switch profile",
            command,
            "profile inspection is allowed",
            profile=self.profile,
            notes=["profile data is read-only"],
        )

    def _validate_llm(self, args: List[str]) -> SwitchRouteValidation:
        command = args[0] if args else "status"
        front_door_allowed = {
            "status",
            "models",
            "list",
            "choose",
            "use",
            "select",
            "current",
            "clear",
            "chat",
            "ask",
            "test",
            "help",
        }
        config_allowed = {"config", "provider", "model", "base-url", "timeout", "streaming", "reset"}
        allowed = front_door_allowed | config_allowed
        if command not in allowed:
            return SwitchRouteValidation(
                False,
                "/llm",
                command,
                "unsupported /llm command",
                profile=self.profile,
                blockers=[
                    "allowed front-door commands: status, models, list, choose, use, select, current, clear, chat, ask, test, help",
                    "allowed config compatibility commands: config, provider, model, base-url, timeout, streaming, reset",
                ],
            )
        if command in config_allowed:
            return SwitchRouteValidation(
                True,
                "/llm",
                command,
                "LLM config change is allowed; provider runtime/network remains disabled",
                profile=self.profile,
                notes=["config-only", "no provider runtime", "no network call"],
            )
        return SwitchRouteValidation(
            True,
            "/llm",
            command,
            "LLM front-door route is allowed through the switch spine",
            profile=self.profile,
            notes=["switch-backed front door", "provider calls opt-in", "no network call"],
        )

    def _validate_tool(self, args: List[str]) -> SwitchRouteValidation:
        command = args[0] if args else "list"
        if not self._profile_enabled("tools.enabled", True):
            return SwitchRouteValidation(
                False,
                "/tool",
                command,
                "tools are disabled by selected profile",
                profile=self.profile,
                blockers=["tools.enabled = false"],
            )
        return SwitchRouteValidation(
            True,
            "/tool",
            command,
            "tool bridge is allowed subject to manifest validation",
            profile=self.profile,
            notes=["manifest bridge still enforces allowlists"],
        )

    def _validate_family(self, surface: str, switch_key: str, args: List[str]) -> SwitchRouteValidation:
        command = args[0] if args else "status"
        if not self._profile_enabled(switch_key, False):
            return SwitchRouteValidation(
                False,
                surface,
                command,
                f"{surface} is disabled by selected profile",
                profile=self.profile,
                blockers=[f"{switch_key} = false"],
            )

        mutation_words = self.APPLY_WORDS.intersection(args)
        if mutation_words:
            return SwitchRouteValidation(
                False,
                surface,
                command,
                f"{surface} mutation is blocked",
                profile=self.profile,
                blockers=[f"blocked mutation tokens: {', '.join(sorted(mutation_words))}"],
            )

        return SwitchRouteValidation(
            True,
            surface,
            command,
            f"{surface} is allowed by selected profile",
            profile=self.profile,
            notes=["validator advisory only"],
        )

    def _validate_git(self, args: List[str]) -> SwitchRouteValidation:
        command = args[0] if args else "status"

        if not self._profile_enabled("git.enabled", False):
            return SwitchRouteValidation(
                False,
                "/git",
                command,
                "/git is disabled by selected profile",
                profile=self.profile,
                blockers=["git.enabled = false"],
            )

        if command == "push" and not self._profile_enabled("git.push_enabled", False):
            return SwitchRouteValidation(
                False,
                "/git",
                command,
                "git push is disabled by selected profile",
                profile=self.profile,
                blockers=["git.push_enabled = false"],
            )

        if command in {"delete", "reset", "clean"} and not self._profile_enabled("git.destructive_enabled", False):
            return SwitchRouteValidation(
                False,
                "/git",
                command,
                "destructive git operation is disabled by selected profile",
                profile=self.profile,
                blockers=["git.destructive_enabled = false"],
            )

        mutation_words = self.APPLY_WORDS.intersection(args)
        if mutation_words:
            return SwitchRouteValidation(
                False,
                "/git",
                command,
                "git mutation is blocked",
                profile=self.profile,
                blockers=[f"blocked mutation tokens: {', '.join(sorted(mutation_words))}"],
            )

        return SwitchRouteValidation(
            True,
            "/git",
            command,
            "/git read/planning command is allowed by selected profile",
            profile=self.profile,
            notes=["validator advisory only"],
        )

    def _validate_media(self, surface: str, args: List[str]) -> SwitchRouteValidation:
        command = args[0] if args else "status"
        key = {
            "/audio": "audio.enabled",
            "/speech": "speech.enabled",
            "/dsp": "dsp.enabled",
            "/image": "images.enabled",
        }.get(surface, "")
        if key and not self._profile_enabled(key, False):
            return SwitchRouteValidation(
                False,
                surface,
                command,
                f"{surface} is disabled by selected profile",
                profile=self.profile,
                blockers=[f"{key} = false"],
            )
        live_keys = {
            "/audio": "audio.playback.enabled",
            "/speech": "speech.tts.enabled",
            "/image": "images.live_generation.enabled",
        }
        live_key = live_keys.get(surface)
        if live_key and not self._profile_enabled(live_key, False):
            return SwitchRouteValidation(
                True,
                surface,
                command,
                f"{surface} planning is allowed but live side effects are disabled",
                profile=self.profile,
                blockers=[f"{live_key} = false"],
                notes=["dry-run/planning only"],
            )
        return SwitchRouteValidation(
            True,
            surface,
            command,
            f"{surface} is allowed by selected profile",
            profile=self.profile,
            notes=["validator advisory only"],
        )

def validation_payload(
    text: str,
    *,
    profile: str = "safe",
    switches: Optional[Mapping[str, Mapping[str, Any]]] = None,
    profiles: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return a machine-readable switch route validation payload.

    This helper is inspection-only. It does not execute tools, mutate runtime
    state, apply profiles, perform live reads, call sudo, or access the network.
    """

    validator = SwitchRouteValidator(
        switches=switches,
        profiles=profiles,
        profile=profile,
    )
    result = validator.validate_text(text)
    payload = result.to_dict()
    payload.update(
        {
            "ok": True,
            "mode": "switch_route_validation",
            "input": str(text or ""),
            "safety": {
                "inspection_only": True,
                "execution_enabled": False,
                "apply_enabled": False,
                "rollback_enabled": False,
                "sudo_enabled": False,
                "runtime_mutation": False,
                "live_read_enabled_by_validator": False,
            },
        }
    )
    return payload


def validation_json(
    text: str,
    *,
    profile: str = "safe",
    pretty: bool = False,
    switches: Optional[Mapping[str, Mapping[str, Any]]] = None,
    profiles: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> str:
    """Return switch route validation as JSON text."""

    payload = validation_payload(
        text,
        profile=profile,
        switches=switches,
        profiles=profiles,
    )
    return json.dumps(payload, indent=2 if pretty else None, sort_keys=True)

