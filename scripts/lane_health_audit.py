#!/usr/bin/env python3
"""Deterministic lane health audit for the Agent backend.

Default audits avoid live LLM/Ollama lanes. Use --include-llm only for explicit
local diagnostics where live model or grounding calls are acceptable.
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.batch_runner import BatchResult, run_command

SCHEMA_VERSION = "lane_health_audit_v1"

DEFAULT_COMMANDS: tuple[str, ...] = (
    "/read README.md",
    "/ls .",
    "/tree .",
    "/find README",
    "/search repo AgentScript",
)

LLM_OPTIONAL_COMMANDS: tuple[str, ...] = (
    "/prompt say hello",
    "/explain README.md",
    "/summarize README.md",
    "/question what is this repo?",
)


def build_cases(*, include_llm: bool = False, commands: Sequence[str] | None = None) -> tuple[dict[str, str], ...]:
    """Return the deterministic audit cases to run."""
    if commands:
        return tuple({"command": str(command), "group": "custom"} for command in commands)

    cases = [{"command": command, "group": "default"} for command in DEFAULT_COMMANDS]
    if include_llm:
        cases.extend({"command": command, "group": "llm_optional"} for command in LLM_OPTIONAL_COMMANDS)
    return tuple(cases)


def _result_to_dict(case: dict[str, str], result: BatchResult) -> dict[str, object]:
    stdout = str(result.stdout or "")
    stderr = str(result.stderr or "")
    return {
        "command": case["command"],
        "group": case["group"],
        "ok": bool(result.ok),
        "returncode": int(result.returncode),
        "mode": str(result.mode),
        "stdout_bytes": len(stdout.encode("utf-8")),
        "stderr": stderr,
    }


def run_lane_health_audit(cases: Iterable[dict[str, str]]) -> dict[str, object]:
    """Run audit cases through core.batch_runner.run_command."""
    results: list[dict[str, object]] = []
    for case in cases:
        result = run_command(case["command"])
        results.append(_result_to_dict(case, result))

    failed = [result for result in results if not result["ok"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not failed,
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
    }


def render_text(payload: dict[str, object]) -> str:
    lines = [
        f"lane health: {'ok' if payload['ok'] else 'failed'}",
        f"total={payload['total']} passed={payload['passed']} failed={payload['failed']}",
    ]
    for item in payload["results"]:  # type: ignore[index]
        result = item  # type: ignore[assignment]
        status = "ok" if result["ok"] else "failed"  # type: ignore[index]
        lines.append(
            f"  - {status} {result['command']} mode={result['mode']} returncode={result['returncode']}"  # type: ignore[index]
        )
        if result["stderr"]:  # type: ignore[index]
            lines.append(f"    stderr: {result['stderr']}")  # type: ignore[index]
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Agent lane health through core.batch_runner.")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--include-llm", action="store_true", help="Include live LLM/grounded lanes in the audit.")
    parser.add_argument(
        "--command",
        action="append",
        default=None,
        help="Audit this exact command. May be repeated. Overrides default command set.",
    )
    parser.add_argument("--fail-on-error", action="store_true", help="Exit non-zero when any audited lane fails.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cases = build_cases(include_llm=bool(args.include_llm), commands=args.command)
    payload = run_lane_health_audit(cases)

    if args.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_text(payload))

    if args.fail_on_error and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
