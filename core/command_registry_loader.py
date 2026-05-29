"""Deterministic loader for command registry metadata fixtures.

This module reads `data/commands` metadata only. It does not execute handlers
or wire runtime behavior.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .command_registry import CommandRegistry, CommandRegistration, VALID_PARSER_FAMILIES


DATA_COMMANDS_DIR = Path("data/commands")
REGISTRY_FIXTURE = DATA_COMMANDS_DIR / "registry.json"
ALIASES_FIXTURE = DATA_COMMANDS_DIR / "aliases.json"
FAMILY_FIXTURES_DIR = DATA_COMMANDS_DIR / "families"

_REGISTRY_ALLOWED_KEYS = {"commands", "description", "schema_version"}
_REGISTRY_COMMAND_KEYS = {
    "description",
    "context_mode",
    "family",
    "lane_type",
    "default_requires_grounding",
    "output_contract",
    "may_use_grounding",
    "may_use_search",
    "may_use_scrape",
    "may_use_web",
    "parser_family",
    "requires_approval",
    "requires_grounding",
    "requires_scrape",
    "requires_web",
    "root",
    "response_template",
    "uses_llm",
}
_ALIASES_ALLOWED_KEYS = {"aliases", "description", "schema_version"}
_ALIAS_ENTRY_KEYS = {"alias", "root"}
_FAMILY_ALLOWED_KEYS = {"description", "family", "parser_family", "roots", "schema_version"}
_PROMPT_VARIANT_ROOTS = {
    "/write",
    "/generate",
    "/discuss",
    "/explain",
    "/describe",
    "/summarize",
    "/analyze",
    "/list",
    "/story",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sorted_copy(data: Mapping[str, Any]) -> dict[str, Any]:
    return {key: data[key] for key in sorted(data)}


def _ensure_only_keys(data: Mapping[str, Any], allowed: set[str], *, path: Path) -> None:
    unexpected = set(data) - allowed
    if unexpected:
        raise ValueError(f"{path}: unexpected keys: {sorted(unexpected)}")


def _canonical_root(root: str) -> str:
    text = _text(root)
    if not text.startswith("/"):
        raise ValueError(f"invalid slash root: {root!r}")
    return text


def _require_bool(value: Any, *, path: Path, field: str, index: int | None = None) -> bool:
    if isinstance(value, bool):
        return value
    location = f"entry #{index} " if index is not None else ""
    raise ValueError(f"{path}: {location}{field} must be a boolean")


def _optional_bool(value: Any, *, path: Path, field: str, index: int | None = None) -> bool:
    if value is None:
        return False
    return _require_bool(value, path=path, field=field, index=index)


def load_registry_fixture(path: Path | str = REGISTRY_FIXTURE) -> dict[str, Any]:
    path = Path(path)
    data = _load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected object")
    _ensure_only_keys(data, _REGISTRY_ALLOWED_KEYS, path=path)

    commands = data.get("commands")
    if not isinstance(commands, list):
        raise ValueError(f"{path}: commands must be a list")

    canonical_commands: list[dict[str, Any]] = []
    seen_roots: set[str] = set()

    for index, entry in enumerate(commands):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: command entry #{index} must be an object")
        _ensure_only_keys(entry, _REGISTRY_COMMAND_KEYS, path=path)

        root = _canonical_root(entry.get("root", ""))
        family = _text(entry.get("family"))
        parser_family = _text(entry.get("parser_family"))
        description = _text(entry.get("description"))
        lane_type = _text(entry.get("lane_type"))
        output_contract = _text(entry.get("output_contract"))
        response_template = _text(entry.get("response_template"))
        context_mode = _text(entry.get("context_mode"))
        uses_llm = _require_bool(entry.get("uses_llm"), path=path, field="uses_llm", index=index)
        requires_web = _require_bool(entry.get("requires_web"), path=path, field="requires_web", index=index)
        requires_scrape = _require_bool(entry.get("requires_scrape"), path=path, field="requires_scrape", index=index)
        requires_grounding = _require_bool(entry.get("requires_grounding"), path=path, field="requires_grounding", index=index)
        requires_approval = _require_bool(entry.get("requires_approval"), path=path, field="requires_approval", index=index)
        may_use_grounding = _optional_bool(entry.get("may_use_grounding"), path=path, field="may_use_grounding", index=index)
        may_use_web = _optional_bool(entry.get("may_use_web"), path=path, field="may_use_web", index=index)
        may_use_search = _optional_bool(entry.get("may_use_search"), path=path, field="may_use_search", index=index)
        may_use_scrape = _optional_bool(entry.get("may_use_scrape"), path=path, field="may_use_scrape", index=index)
        default_requires_grounding = _optional_bool(entry.get("default_requires_grounding"), path=path, field="default_requires_grounding", index=index)

        if not family:
            raise ValueError(f"{path}: command entry #{index} missing family")
        if parser_family not in VALID_PARSER_FAMILIES:
            raise ValueError(f"{path}: invalid parser_family for {root}: {parser_family}")
        if not description:
            raise ValueError(f"{path}: command entry #{index} missing description")
        if not lane_type:
            raise ValueError(f"{path}: command entry #{index} missing lane_type")
        if not output_contract:
            raise ValueError(f"{path}: command entry #{index} missing output_contract for lane {root}")
        if root in _PROMPT_VARIANT_ROOTS:
            if not response_template:
                raise ValueError(f"{path}: command entry #{index} missing response_template for prompt variant {root}")
            if not context_mode:
                raise ValueError(f"{path}: command entry #{index} missing context_mode for prompt variant {root}")
        elif any(
            key in entry
            for key in (
                "response_template",
                "context_mode",
                "may_use_grounding",
                "may_use_web",
                "may_use_search",
                "may_use_scrape",
                "default_requires_grounding",
            )
        ):
            raise ValueError(f"{path}: command entry #{index} contains prompt-variant metadata for non-prompt root {root}")
        if root in seen_roots:
            raise ValueError(f"{path}: duplicate root: {root}")
        seen_roots.add(root)

        canonical_commands.append(
            {
                "context_mode": context_mode,
                "description": description,
                "default_requires_grounding": default_requires_grounding,
                "family": family,
                "lane_type": lane_type,
                "may_use_grounding": may_use_grounding,
                "may_use_search": may_use_search,
                "may_use_scrape": may_use_scrape,
                "may_use_web": may_use_web,
                "output_contract": output_contract,
                "parser_family": parser_family,
                "requires_approval": requires_approval,
                "requires_grounding": requires_grounding,
                "requires_scrape": requires_scrape,
                "requires_web": requires_web,
                "root": root,
                "response_template": response_template,
                "uses_llm": uses_llm,
            }
        )

    canonical_commands.sort(key=lambda item: item["root"])

    return {
        "commands": canonical_commands,
        "description": _text(data.get("description", "")),
        "schema_version": _text(data.get("schema_version", "")),
    }


def load_alias_fixture(path: Path | str = ALIASES_FIXTURE) -> dict[str, Any]:
    path = Path(path)
    data = _load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected object")
    _ensure_only_keys(data, _ALIASES_ALLOWED_KEYS, path=path)

    aliases = data.get("aliases")
    if not isinstance(aliases, list):
        raise ValueError(f"{path}: aliases must be a list")

    canonical_aliases: list[dict[str, Any]] = []
    seen_aliases: set[str] = set()

    for index, entry in enumerate(aliases):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: alias entry #{index} must be an object")
        _ensure_only_keys(entry, _ALIAS_ENTRY_KEYS, path=path)

        alias = _canonical_root(entry.get("alias", ""))
        root = _canonical_root(entry.get("root", ""))
        if alias in seen_aliases:
            raise ValueError(f"{path}: duplicate alias: {alias}")
        seen_aliases.add(alias)

        canonical_aliases.append(
            {
                "alias": alias,
                "root": root,
            }
        )

    canonical_aliases.sort(key=lambda item: item["alias"])

    return {
        "aliases": canonical_aliases,
        "description": _text(data.get("description", "")),
        "schema_version": _text(data.get("schema_version", "")),
    }


def load_family_fixtures(path: Path | str = FAMILY_FIXTURES_DIR) -> dict[str, dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    families: dict[str, dict[str, Any]] = {}
    for family_path in sorted(path.glob("*.json")):
        data = _load_json(family_path)
        if not isinstance(data, dict):
            raise ValueError(f"{family_path}: expected object")
        _ensure_only_keys(data, _FAMILY_ALLOWED_KEYS, path=family_path)

        family = _text(data.get("family", ""))
        parser_family = _text(data.get("parser_family", ""))
        description = _text(data.get("description", ""))
        roots = data.get("roots")

        if not family:
            raise ValueError(f"{family_path}: missing family")
        if family_path.stem != family:
            raise ValueError(f"{family_path}: family name must match file stem")
        if not description:
            raise ValueError(f"{family_path}: missing description")
        if parser_family not in VALID_PARSER_FAMILIES:
            raise ValueError(f"{family_path}: invalid parser_family: {parser_family}")
        if not isinstance(roots, list):
            raise ValueError(f"{family_path}: roots must be a list")

        canonical_roots: list[str] = []
        seen_roots: set[str] = set()
        for index, root in enumerate(roots):
            value = _canonical_root(root)
            if value in seen_roots:
                raise ValueError(f"{family_path}: duplicate root: {value}")
            seen_roots.add(value)
            canonical_roots.append(value)

        canonical_roots.sort()
        families[family] = {
            "description": description,
            "family": family,
            "parser_family": parser_family,
            "roots": canonical_roots,
            "schema_version": _text(data.get("schema_version", "")),
        }

    return {name: families[name] for name in sorted(families)}


def load_command_registry_data(base_dir: Path | str = DATA_COMMANDS_DIR) -> CommandRegistry:
    base_dir = Path(base_dir)
    registry_fixture = load_registry_fixture(base_dir / "registry.json")
    alias_fixture = load_alias_fixture(base_dir / "aliases.json")
    family_fixtures = load_family_fixtures(base_dir / "families")

    registry_roots = [entry["root"] for entry in registry_fixture["commands"]]
    family_roots = [root for family in family_fixtures.values() for root in family["roots"]]

    if registry_roots != sorted(registry_roots):
        raise ValueError("registry roots must be sorted")
    if len(registry_roots) != len(set(registry_roots)):
        raise ValueError("registry roots must be unique")
    if len(family_roots) != len(set(family_roots)):
        raise ValueError("family roots must be unique")
    if set(registry_roots) != set(family_roots):
        raise ValueError("family/root consistency mismatch")

    alias_roots = [entry["root"] for entry in alias_fixture["aliases"]]
    if len(alias_roots) != len(set(alias_roots)):
        raise ValueError("alias roots must be unique")
    if len([entry["alias"] for entry in alias_fixture["aliases"]]) != len(set(entry["alias"] for entry in alias_fixture["aliases"])):
        raise ValueError("aliases must be unique")
    for alias_entry in alias_fixture["aliases"]:
        if alias_entry["root"] not in registry_roots:
            raise ValueError(f"alias root not found in registry: {alias_entry['root']}")

    aliases_by_root: dict[str, tuple[str, ...]] = {root: () for root in registry_roots}
    for alias_entry in alias_fixture["aliases"]:
        root = alias_entry["root"]
        aliases_by_root[root] = aliases_by_root[root] + (alias_entry["alias"],)

    registrations: list[CommandRegistration] = []
    for entry in registry_fixture["commands"]:
        root = entry["root"]
        family = entry["family"]
        family_fixture = family_fixtures.get(family)
        if family_fixture is None:
            raise ValueError(f"missing family fixture for {family}")
        if root not in family_fixture["roots"]:
            raise ValueError(f"registry root {root} not listed in family {family}")

        name = root.lstrip("/")
        aliases = aliases_by_root[root]
        registrations.append(
            CommandRegistration(
                name=name,
                surface=family,
                mode=f"catalog.{name}",
                handler_name=f"catalog.{name}",
                description=entry["description"],
                input_kind="catalog_command",
                allowed_in_batch=False,
                requires_policy=False,
                requires_grounding=entry["requires_grounding"],
                requires_approval=entry["requires_approval"],
                mutates_state=False,
                inspect_only=True,
                parser_family=entry["parser_family"],
                lane_type=entry["lane_type"],
                uses_llm=entry["uses_llm"],
                requires_web=entry["requires_web"],
                requires_scrape=entry["requires_scrape"],
                output_contract=entry["output_contract"],
                response_template=entry["response_template"],
                context_mode=entry["context_mode"],
                may_use_grounding=entry["may_use_grounding"],
                may_use_web=entry["may_use_web"],
                may_use_search=entry["may_use_search"],
                may_use_scrape=entry["may_use_scrape"],
                default_requires_grounding=entry["default_requires_grounding"],
                aliases=aliases,
                metadata={
                    "catalog_aliases": list(aliases),
                    "catalog_family": family,
                    "catalog_root": root,
                    "catalog_source": "data/commands",
                    "family_description": family_fixture["description"],
                    "family_parser_family": family_fixture["parser_family"],
                    "registry_description": registry_fixture["description"],
                    "registry_schema_version": registry_fixture["schema_version"],
                },
            )
        )

    return CommandRegistry(tuple(registrations))
