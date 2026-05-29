"""Codex CLI front-door command parsing and prompt construction.

This module intentionally stays at the command-construction layer for now.
It does not execute Codex CLI from agent-cli.py yet.
"""
from __future__ import annotations

from dataclasses import dataclass
import shlex
from pathlib import Path


VALID_CODEX_ACTIONS = {"status", "prompt", "package"}


@dataclass(frozen=True)
class CodexFrontdoorCommand:
    action: str
    task: str | None = None


class CodexFrontdoorError(ValueError):
    pass


def parse_codex_command(text: str) -> CodexFrontdoorCommand:
    parts = shlex.split(text.strip())

    if not parts or parts[0] != "/codex":
        raise CodexFrontdoorError("codex command must start with /codex")

    if len(parts) == 1:
        raise CodexFrontdoorError("usage: /codex <status|prompt|package> [task]")

    action = parts[1]
    if action not in VALID_CODEX_ACTIONS:
        raise CodexFrontdoorError(f"unknown /codex action: {action}")

    if action == "status":
        if len(parts) != 2:
            raise CodexFrontdoorError("usage: /codex status")
        return CodexFrontdoorCommand(action=action)

    task = " ".join(parts[2:]).strip()
    if not task:
        raise CodexFrontdoorError(f"usage: /codex {action} <task>")

    return CodexFrontdoorCommand(action=action, task=task)


def build_codex_package_prompt(task: str) -> str:
    task_text = str(task or "").strip()
    if not task_text:
        raise CodexFrontdoorError("codex package prompt requires a task")

    return (
        "You are helping with this repository as an external coding worker.\n"
        "Read these stable project instructions first:\n"
        "- AGENTS.md\n"
        "- docs/project-memory.md\n"
        "- docs/codex-handoff.md\n\n"
        f"Task:\n{task_text}\n\n"
        "Requirements:\n"
        "- Produce changes only as a patch ZIP.\n"
        "- Use scripts/make_patch_package.py to build the patch ZIP from real git diff output.\n"
        "- Use scripts/agent_patch_runner.py to validate and apply the patch ZIP.\n"
        "- do not directly commit unvalidated edits.\n"
        "- Do not auto-commit or auto-push.\n"
        "- Keep the patch runner as the final policy gate.\n"
    )


def build_codex_command(command: CodexFrontdoorCommand, *, repo_root: Path | None = None) -> list[str]:
    _ = repo_root

    if command.action == "status":
        return ["codex", "--help"]

    if command.task is None:
        raise CodexFrontdoorError(f"/codex {command.action} requires a task")

    if command.action == "prompt":
        return ["codex", "prompt", command.task]

    if command.action == "package":
        return ["codex", "prompt", build_codex_package_prompt(command.task)]

    raise CodexFrontdoorError(f"unsupported /codex action: {command.action}")


def codex_help_text() -> str:
    return (
        "Codex commands:\n"
        "  /codex status\n"
        "  /codex prompt <task>\n"
        "  /codex package <task>\n"
    )
