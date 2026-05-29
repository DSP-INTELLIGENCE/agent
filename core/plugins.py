from __future__ import annotations

import importlib.util
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.constants import (
    PLUGIN_ALLOWED_SAFETY_LEVELS,
    PLUGIN_DATA_DIR,
    PLUGIN_MAX_FILES,
    PLUGIN_PROTECTED_COMMAND_PREFIXES,
    PLUGIN_SCHEMA_VERSION,
    PLUGINS_DIR,
)
from core.helpers import clean_text, now_str

# ============================================================
# PLUGIN CONTRACT / LOADER
# ============================================================

@dataclass
class PluginRecord:
    plugin_id: str
    name: str
    version: str
    description: str
    safety_level: str
    enabled: bool
    module_path: str
    manifest: Dict[str, Any] = field(default_factory=dict)
    commands: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    capabilities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    natural_language_triggers: List[Dict[str, Any]] = field(default_factory=list)
    load_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def safe_plugin_id_to_dirname(plugin_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", clean_text(plugin_id))
    return safe.strip("._-") or "plugin"


def validate_plugin_manifest(manifest: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    if not isinstance(manifest, dict):
        return False, ["manifest must be a dictionary"]

    if manifest.get("schema_version") != PLUGIN_SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {manifest.get('schema_version')}")

    plugin_id = clean_text(manifest.get("plugin_id") or "")
    if not plugin_id:
        errors.append("plugin_id is required")

    if not clean_text(manifest.get("name") or ""):
        errors.append("name is required")

    if not clean_text(manifest.get("version") or ""):
        errors.append("version is required")

    safety = clean_text(manifest.get("safety_level") or "")
    if safety not in PLUGIN_ALLOWED_SAFETY_LEVELS:
        errors.append(f"unknown safety_level: {safety}")

    commands = manifest.get("commands")
    if not isinstance(commands, list):
        errors.append("commands must be a list")

    seen_commands = set()
    for command in commands if isinstance(commands, list) else []:
        if not isinstance(command, dict):
            errors.append("command entries must be dictionaries")
            continue

        name = clean_text(command.get("name") or "")
        action = clean_text(command.get("action") or "")

        if not name:
            errors.append("command.name is required")
        if not action:
            errors.append(f"command.action is required for {name or '(unnamed command)'}")

        if name.startswith(PLUGIN_PROTECTED_COMMAND_PREFIXES):
            errors.append(f"plugin command may not use protected core prefix: {name}")

        if name in seen_commands:
            errors.append(f"duplicate command in manifest: {name}")
        if name:
            seen_commands.add(name)

    return not errors, errors


def normalize_plugin_result(result: Dict[str, Any]) -> Dict[str, Any]:
    raw_display = result.get("display")
    if isinstance(raw_display, dict):
        display = raw_display
    elif isinstance(raw_display, str) and raw_display.strip():
        display = {"type": "text", "text": raw_display.strip()}
    else:
        display = {}

    return {
        "ok": bool(result.get("ok", False)),
        "handled": bool(result.get("handled", True)),
        # Preserve plugin-provided newlines. clean_text() intentionally
        # collapses whitespace and is not appropriate for terminal display text.
        "message": str(result.get("message") or "").strip(),
        "data": result.get("data") if isinstance(result.get("data"), dict) else {},
        "artifacts": result.get("artifacts") if isinstance(result.get("artifacts"), list) else [],
        "sources": result.get("sources") if isinstance(result.get("sources"), list) else [],
        "warnings": result.get("warnings") if isinstance(result.get("warnings"), list) else [],
        "errors": result.get("errors") if isinstance(result.get("errors"), list) else [],
        "display": display,
        "memory_suggestions": result.get("memory_suggestions") if isinstance(result.get("memory_suggestions"), list) else [],
        "next_actions": result.get("next_actions") if isinstance(result.get("next_actions"), list) else [],
    }


def _as_string_list(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [clean_text(x) for x in value if clean_text(x)]
    return []


def _trigger_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return clean_text(value).lower() not in {"0", "false", "no", "off", "disabled"}


def _plugin_trigger_args(
    *,
    raw: str,
    trigger: Dict[str, Any],
    args_text: str,
    regex_groups: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    args: Dict[str, Any] = {}

    default_args = trigger.get("default_args")
    if isinstance(default_args, dict):
        args.update(default_args)

    regex_groups = regex_groups if isinstance(regex_groups, dict) else {}
    for key, value in regex_groups.items():
        if clean_text(value):
            args[key] = value

    arg_name = clean_text(trigger.get("arg_name") or "text") or "text"

    if args_text:
        args.setdefault(arg_name, args_text)
        args.setdefault("text", args_text)
        args.setdefault("query", args_text)

    args.setdefault("message", raw)

    return args


def match_plugin_natural_language_trigger(
    text: str,
    triggers: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Match user text against manifest-declared plugin natural-language triggers.

    Supported trigger fields:
      command / plugin_command / command_name: plugin command to run
      enabled: bool optional
      match / type: prefix | contains | phrase | regex | keywords
      phrases: list[str] or str
      pattern: regex pattern
      keywords: list[str]
      confidence: optional float override
      min_confidence: optional float, default 0.75
      min_keyword_ratio: optional float, default 1.0
      strip_matched_phrase: bool, default True for prefix phrases
      arg_name: target payload arg name, default text
      default_args: dict merged into payload args

    Return shape:
      {
        "command": plugin command name,
        "confidence": score,
        "args_text": extracted text,
        "args": plugin payload args,
        "trigger": compact trigger metadata
      }
    """
    raw = str(text or "").strip()
    lowered = clean_text(raw).lower()
    if not raw or not lowered or not isinstance(triggers, list):
        return None

    matches: List[Dict[str, Any]] = []

    for trigger in triggers:
        if not isinstance(trigger, dict):
            continue

        if not _trigger_bool(trigger.get("enabled"), True):
            continue

        command_name = clean_text(
            trigger.get("command")
            or trigger.get("plugin_command")
            or trigger.get("command_name")
            or ""
        )
        if not command_name:
            continue

        match_kind = clean_text(trigger.get("match") or trigger.get("type") or "").lower()
        phrases = _as_string_list(trigger.get("phrases") or trigger.get("phrase"))
        keywords = _as_string_list(trigger.get("keywords"))
        pattern = clean_text(trigger.get("pattern") or "")

        min_confidence = 0.75
        try:
            min_confidence = float(trigger.get("min_confidence", min_confidence))
        except Exception:
            pass

        best_score = 0.0
        best_args_text = raw
        matched_by = ""
        matched_value = ""
        regex_groups: Dict[str, str] = {}

        # Regex trigger.
        if pattern:
            try:
                m = re.search(pattern, raw, flags=re.IGNORECASE)
            except re.error:
                m = None

            if m:
                score = 0.95
                try:
                    score = float(trigger.get("confidence", score))
                except Exception:
                    pass

                best_score = max(best_score, score)
                matched_by = "regex"
                matched_value = pattern
                regex_groups = {
                    k: clean_text(v)
                    for k, v in m.groupdict().items()
                    if clean_text(v)
                }

                if regex_groups.get("query"):
                    best_args_text = regex_groups["query"]
                elif regex_groups.get("text"):
                    best_args_text = regex_groups["text"]
                elif m.groups():
                    best_args_text = clean_text(m.group(1))
                else:
                    best_args_text = raw

        # Phrase / prefix / contains trigger.
        for phrase in phrases:
            phrase_clean = clean_text(phrase)
            phrase_lower = phrase_clean.lower()
            if not phrase_lower:
                continue

            phrase_matched = False
            phrase_score = 0.0

            if match_kind == "prefix":
                phrase_matched = lowered.startswith(phrase_lower)
                phrase_score = 0.92
            elif match_kind in {"contains", "phrase", "any_phrase"}:
                phrase_matched = phrase_lower in lowered
                phrase_score = 0.84
            else:
                if lowered.startswith(phrase_lower):
                    phrase_matched = True
                    phrase_score = 0.90
                elif phrase_lower in lowered:
                    phrase_matched = True
                    phrase_score = 0.82

            if not phrase_matched:
                continue

            try:
                phrase_score = float(trigger.get("confidence", phrase_score))
            except Exception:
                pass

            if phrase_score > best_score:
                best_score = phrase_score
                matched_by = match_kind or "phrase"
                matched_value = phrase_clean

                strip_phrase = _trigger_bool(trigger.get("strip_matched_phrase"), True)
                if strip_phrase and lowered.startswith(phrase_lower):
                    best_args_text = clean_text(raw[len(phrase_clean):])
                else:
                    best_args_text = raw

        # Keyword trigger.
        if keywords:
            keyword_hits = 0
            for keyword in keywords:
                if clean_text(keyword).lower() in lowered:
                    keyword_hits += 1

            ratio = keyword_hits / max(1, len(keywords))
            try:
                min_ratio = float(trigger.get("min_keyword_ratio", 1.0))
            except Exception:
                min_ratio = 1.0

            if ratio >= min_ratio:
                keyword_score = 0.86 if ratio >= 1.0 else 0.76
                try:
                    keyword_score = float(trigger.get("confidence", keyword_score))
                except Exception:
                    pass

                if keyword_score > best_score:
                    best_score = keyword_score
                    matched_by = "keywords"
                    matched_value = ", ".join(keywords)
                    best_args_text = raw

        if best_score >= min_confidence:
            matches.append({
                "command": command_name,
                "confidence": round(best_score, 3),
                "args_text": best_args_text,
                "args": _plugin_trigger_args(
                    raw=raw,
                    trigger=trigger,
                    args_text=best_args_text,
                    regex_groups=regex_groups,
                ),
                "trigger": {
                    "plugin_id": trigger.get("plugin_id"),
                    "trigger_id": trigger.get("trigger_id") or trigger.get("id"),
                    "match": matched_by,
                    "matched": matched_value,
                    "description": clean_text(trigger.get("description") or ""),
                },
            })

    if not matches:
        return None

    matches.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)
    return matches[0]

class PluginManager:
    def __init__(self, plugins_dir: Path, plugin_data_dir: Path) -> None:
        self.plugins_dir = plugins_dir
        self.plugin_data_dir = plugin_data_dir
        self.records: Dict[str, PluginRecord] = {}
        self.modules: Dict[str, Any] = {}
        self.command_to_plugin: Dict[str, str] = {}

    def load_plugin_file(self, path: Path) -> PluginRecord:
        import importlib.util

        module_name = f"agent_plugin_{path.stem}_{abs(hash(str(path)))}"
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not import plugin file: {path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "get_plugin_manifest"):
            raise RuntimeError("plugin is missing get_plugin_manifest()")

        if not hasattr(module, "handle_plugin_action"):
            raise RuntimeError("plugin is missing handle_plugin_action()")

        manifest = module.get_plugin_manifest()
        ok, errors = validate_plugin_manifest(manifest)
        if not ok:
            raise RuntimeError("; ".join(errors))

        plugin_id = clean_text(manifest.get("plugin_id"))
        if plugin_id in self.records:
            raise RuntimeError(f"duplicate plugin_id: {plugin_id}")

        commands: Dict[str, Dict[str, Any]] = {}
        for cmd in manifest.get("commands") or []:
            if isinstance(cmd, dict):
                command_name = clean_text(cmd.get("name"))
                if command_name:
                    if command_name in self.command_to_plugin:
                        raise RuntimeError(f"duplicate plugin command across plugins: {command_name}")
                    commands[command_name] = cmd

        capabilities: Dict[str, Dict[str, Any]] = {}
        for cap in manifest.get("capabilities") or []:
            if isinstance(cap, dict):
                cap_id = clean_text(cap.get("capability_id"))
                if cap_id:
                    capabilities[cap_id] = cap

        record = PluginRecord(
            plugin_id=plugin_id,
            name=clean_text(manifest.get("name")),
            version=clean_text(manifest.get("version")),
            description=clean_text(manifest.get("description")),
            safety_level=clean_text(manifest.get("safety_level")),
            enabled=bool(manifest.get("enabled_by_default", True)),
            module_path=str(path),
            manifest=manifest,
            commands=commands,
            capabilities=capabilities,
            natural_language_triggers=manifest.get("natural_language_triggers") if isinstance(manifest.get("natural_language_triggers"), list) else [],
        )

        self.records[plugin_id] = record
        self.modules[plugin_id] = module

        for command_name in commands:
            self.command_to_plugin[command_name] = plugin_id

        return record

    def scan_and_load(self) -> Dict[str, Any]:
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)

        self.records.clear()
        self.modules.clear()
        self.command_to_plugin.clear()

        loaded: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        plugin_files = sorted(self.plugins_dir.glob("*.py"))[:PLUGIN_MAX_FILES]

        for path in plugin_files:
            if path.name.startswith("_"):
                continue
            try:
                record = self.load_plugin_file(path)
                loaded.append(record.to_dict())
            except Exception as exc:
                errors.append({
                    "path": str(path),
                    "error": str(exc),
                })

        return {
            "loaded_count": len(loaded),
            "error_count": len(errors),
            "loaded": loaded,
            "errors": errors,
        }

    def natural_language_triggers(self) -> List[Dict[str, Any]]:
        """
        Return compact enabled natural-language trigger specs from loaded plugin manifests.

        Manifest field:
            natural_language_triggers: list[dict | str]

        String trigger shorthand is allowed only when the plugin exposes exactly one command:
            "make scaffold"
        becomes:
            {"phrases": ["make scaffold"], "command": "<only command>"}
        """
        triggers: List[Dict[str, Any]] = []

        for plugin_id, record in sorted(self.records.items()):
            if not record.enabled:
                continue

            raw_triggers = record.natural_language_triggers
            if not isinstance(raw_triggers, list) or not raw_triggers:
                continue

            only_command = ""
            if len(record.commands) == 1:
                only_command = next(iter(record.commands.keys()))

            for index, raw_trigger in enumerate(raw_triggers):
                if isinstance(raw_trigger, str):
                    if not only_command:
                        continue
                    trigger = {
                        "phrases": [raw_trigger],
                        "command": only_command,
                        "match": "contains",
                    }
                elif isinstance(raw_trigger, dict):
                    trigger = dict(raw_trigger)
                else:
                    continue

                command_name = clean_text(
                    trigger.get("command")
                    or trigger.get("plugin_command")
                    or trigger.get("command_name")
                    or only_command
                )

                if not command_name:
                    continue

                # Trigger can only route to a command owned by this loaded plugin.
                if command_name not in record.commands:
                    continue

                trigger["command"] = command_name
                trigger["plugin_id"] = plugin_id
                trigger.setdefault("trigger_id", f"{plugin_id}.trigger.{index}")
                trigger.setdefault("plugin_name", record.name)
                triggers.append(trigger)

        return triggers[:100]


    def switch_entries(self) -> List[Dict[str, Any]]:
        """Return plugin-owned /switch aliases and switchable commands.

        Sources:
        - every loaded plugin command is switchable by full command name
        - manifest["switch_aliases"] may expose plugin/action aliases
        - optional module.plugin_switches() may expose richer aliases
        """
        entries: List[Dict[str, Any]] = []

        for plugin_id, record in sorted(self.records.items()):
            if not record.enabled:
                continue

            module = self.modules.get(plugin_id)
            manifest_aliases = record.manifest.get("switch_aliases")
            plugin_aliases: List[str] = []

            if isinstance(manifest_aliases, dict):
                raw_plugin_aliases = manifest_aliases.get("plugin") or manifest_aliases.get("aliases") or []
                plugin_aliases = _as_string_list(raw_plugin_aliases)
            else:
                plugin_aliases = _as_string_list(manifest_aliases)

            # Full command names are always switchable.
            for command_name, command_spec in sorted(record.commands.items()):
                action = clean_text(command_spec.get("action") or command_name)
                description = clean_text(command_spec.get("description") or "")
                short_action = command_name.split(".")[-1]
                keys = [command_name]
                for alias in plugin_aliases:
                    keys.append(f"{alias}.{short_action}")
                entries.append({
                    "key": command_name,
                    "keys": sorted(set(keys)),
                    "plugin_id": plugin_id,
                    "command": command_name,
                    "action": action,
                    "description": description,
                    "safety_level": record.safety_level,
                    "source": "command",
                })

            # Structured manifest aliases.
            if isinstance(manifest_aliases, dict):
                command_aliases = manifest_aliases.get("commands")
                if isinstance(command_aliases, dict):
                    for alias, target in sorted(command_aliases.items()):
                        alias = clean_text(alias)
                        if not alias:
                            continue
                        if isinstance(target, str):
                            command_name = clean_text(target)
                            default_args: Dict[str, Any] = {}
                        elif isinstance(target, dict):
                            command_name = clean_text(target.get("command") or target.get("target") or "")
                            default_args = target.get("default_args") if isinstance(target.get("default_args"), dict) else {}
                        else:
                            continue
                        if command_name not in record.commands:
                            continue
                        command_spec = record.commands.get(command_name) or {}
                        entries.append({
                            "key": alias,
                            "keys": [alias],
                            "plugin_id": plugin_id,
                            "command": command_name,
                            "action": clean_text(command_spec.get("action") or command_name),
                            "description": clean_text(command_spec.get("description") or ""),
                            "safety_level": record.safety_level,
                            "default_args": default_args,
                            "source": "manifest.switch_aliases",
                        })

            # Optional plugin-owned switch registry.
            if module is not None and hasattr(module, "plugin_switches"):
                try:
                    raw_switches = module.plugin_switches()
                except Exception:
                    raw_switches = []
                if isinstance(raw_switches, list):
                    for raw in raw_switches:
                        if not isinstance(raw, dict):
                            continue
                        command_name = clean_text(raw.get("command") or raw.get("target") or "")
                        if command_name not in record.commands:
                            continue
                        aliases = _as_string_list(raw.get("aliases") or raw.get("alias") or raw.get("key"))
                        if not aliases:
                            continue
                        command_spec = record.commands.get(command_name) or {}
                        entries.append({
                            "key": aliases[0],
                            "keys": sorted(set(aliases)),
                            "plugin_id": plugin_id,
                            "command": command_name,
                            "action": clean_text(command_spec.get("action") or command_name),
                            "description": clean_text(raw.get("description") or command_spec.get("description") or ""),
                            "safety_level": record.safety_level,
                            "default_args": raw.get("default_args") if isinstance(raw.get("default_args"), dict) else {},
                            "source": "plugin.plugin_switches",
                        })

        return entries[:500]

    def switch_index(self) -> Dict[str, Dict[str, Any]]:
        index: Dict[str, Dict[str, Any]] = {}
        for entry in self.switch_entries():
            for key in entry.get("keys") or [entry.get("key")]:
                key_clean = clean_text(key).lower()
                if key_clean and key_clean not in index:
                    normalized = dict(entry)
                    normalized["matched_key"] = key_clean
                    index[key_clean] = normalized
        return index

    def dispatch(self, command_name: str, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        plugin_id = self.command_to_plugin.get(command_name)
        if not plugin_id:
            return {
                "ok": False,
                "handled": False,
                "message": f"No plugin command registered: {command_name}",
                "data": {},
                "errors": [f"No plugin command registered: {command_name}"],
            }

        record = self.records.get(plugin_id)
        module = self.modules.get(plugin_id)

        if not record or not module:
            return {
                "ok": False,
                "handled": False,
                "message": f"Plugin not loaded: {plugin_id}",
                "data": {},
                "errors": [f"Plugin not loaded: {plugin_id}"],
            }

        if not record.enabled:
            return {
                "ok": False,
                "handled": True,
                "message": f"Plugin is disabled: {plugin_id}",
                "data": {},
                "errors": [f"Plugin is disabled: {plugin_id}"],
            }

        command_spec = record.commands.get(command_name) or {}
        action = clean_text(command_spec.get("action") or "")

        if not action:
            return {
                "ok": False,
                "handled": True,
                "message": f"Plugin command has no action: {command_name}",
                "data": {},
                "errors": [f"Plugin command has no action: {command_name}"],
            }

        plugin_data_dir = self.plugin_data_dir / safe_plugin_id_to_dirname(plugin_id)
        plugin_data_dir.mkdir(parents=True, exist_ok=True)

        plugin_context = dict(context or {})
        plugin_context["plugin_id"] = plugin_id
        plugin_context["plugin_data_dir"] = str(plugin_data_dir)
        plugin_context["command_name"] = command_name
        plugin_context["command_spec"] = command_spec
        plugin_context["manifest"] = record.manifest

        try:
            result = module.handle_plugin_action(action, args or {}, plugin_context)
        except Exception as exc:
            return {
                "ok": False,
                "handled": True,
                "message": f"Plugin action failed: {exc}",
                "data": {},
                "errors": [str(exc)],
            }

        if not isinstance(result, dict):
            return {
                "ok": False,
                "handled": True,
                "message": "Plugin returned non-dictionary result.",
                "data": {"raw_result": str(result)},
                "errors": ["Plugin returned non-dictionary result."],
            }

        return normalize_plugin_result(result)
