"""Patch front-door command parsing and runner dispatch.

This module intentionally keeps patch execution delegated to
`scripts/agent_patch_runner.py`. It does not duplicate patch validation logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess


VALID_PATCH_ACTIONS = {"dry-run", "apply", "replay", "status"}


@dataclass(frozen=True)
class PatchFrontdoorCommand:
    action: str
    target: str | None = None


@dataclass(frozen=True)
class PatchFrontdoorResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class PatchFrontdoorError(ValueError):
    pass


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_patch_command(text: str) -> PatchFrontdoorCommand:
    parts = shlex.split(text.strip())

    if not parts or parts[0] != '/patch':
        raise PatchFrontdoorError('patch command must start with /patch')

    if len(parts) == 1:
        raise PatchFrontdoorError('usage: /patch <dry-run|apply|replay|status> [path]')

    action = parts[1]
    if action not in VALID_PATCH_ACTIONS:
        raise PatchFrontdoorError(f'unknown /patch action: {action}')

    if action == 'status':
        if len(parts) != 2:
            raise PatchFrontdoorError('usage: /patch status')
        return PatchFrontdoorCommand(action=action)

    if len(parts) != 3:
        raise PatchFrontdoorError(f'usage: /patch {action} <path>')

    return PatchFrontdoorCommand(action=action, target=parts[2])


def build_patch_runner_command(command: PatchFrontdoorCommand, *, repo_root: Path | None = None) -> list[str]:
    repo = repo_root or repo_root_from_here()
    agent_python = repo / 'scripts' / 'agent_python.sh'
    runner = repo / 'scripts' / 'agent_patch_runner.py'

    if command.action == 'status':
        return ['git', 'status', '--short']

    if command.target is None:
        raise PatchFrontdoorError(f'/patch {command.action} requires a path')
    target = str(Path(command.target).expanduser())

    if command.action == 'dry-run':
        return [str(agent_python), str(runner), target, '--dry-run']

    if command.action == 'apply':
        return [str(agent_python), str(runner), target]

    if command.action == 'replay':
        return [str(agent_python), str(runner), '--replay', target]

    raise PatchFrontdoorError(f'unsupported /patch action: {command.action}')


def run_patch_command(text: str, *, repo_root: Path | None = None) -> PatchFrontdoorResult:
    repo = repo_root or repo_root_from_here()
    parsed = parse_patch_command(text)
    cmd = build_patch_runner_command(parsed, repo_root=repo)
    proc = subprocess.run(cmd, cwd=repo, text=True, capture_output=True)

    stdout = proc.stdout
    if parsed.action == "status" and proc.returncode == 0 and not stdout.strip():
        stdout = "working tree clean\n"

    return PatchFrontdoorResult(
        command=cmd,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=proc.stderr,
    )


def patch_help_text() -> str:
    return (
        'Patch commands:\n'
        '  /patch dry-run <patch.zip>\n'
        '  /patch apply <patch.zip>\n'
        '  /patch replay <reports/.../run.json>\n'
        '  /patch status'
    )
