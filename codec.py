#!/usr/bin/env python3
"""Clean Codec command-line frontend.

codec.py is the human-facing frontend for the codec runtime.  It keeps the
public command surface small while delegating execution to the existing runtime
engines:

* prompt/ground use core.batch_runner with explicit slash lanes.
* patch delegates to scripts.codec_patch_install.

agent-cli.py remains as the legacy compatibility CLI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.batch_runner import format_result, run_command


REPO_ROOT = Path(__file__).resolve().parent


def _join_text(parts: list[str]) -> str:
    return " ".join(str(part) for part in parts).strip()


def _run_text_lane(prefix: str, text_parts: list[str], *, label: str) -> int:
    text = _join_text(text_parts)
    if not text:
        sys.stderr.write(f"codec {label} error: text is required\n")
        return 2

    result = run_command(f"{prefix} {text}")
    output = format_result(result, "text")
    if output:
        stream = sys.stdout if result.ok else sys.stderr
        stream.write(output)
        if not output.endswith("\n"):
            stream.write("\n")
    return int(result.returncode)


def _git_output(*args: str) -> str:
    try:
        import subprocess
        result = subprocess.run(
            ["git", *args],
            cwd=Path(__file__).resolve().parent,
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def _status_payload() -> dict:
    status_short = _git_output("status", "--short", "--untracked-files=all")
    branch = _git_output("branch", "--show-current") or "unknown"
    head = _git_output("rev-parse", "--short", "HEAD") or "unknown"
    return {
        "codec_frontend": "available",
        "entrypoint": "codec.py",
        "answer_lanes": {
            "prompt": "/prompt",
            "ground": "/ground",
        },
        "patch_operator": "codec-patch.py",
        "patch_workflow": ["review", "publish", "merge-cleanup"],
        "repo": {
            "branch": branch,
            "head": head,
            "clean": not bool(status_short),
            "status_short": status_short,
        },
    }


def _status(*, json_output: bool = False) -> int:
    payload = _status_payload()
    if json_output:
        import json
        print(json.dumps(payload, sort_keys=True))
        return 0

    print("codec frontend: available")
    print("entrypoint: codec.py")
    print("answer lanes:")
    print("  prompt -> /prompt")
    print("  ground -> /ground")
    print("patch operator: codec-patch.py")
    print("patch workflow: review -> publish -> merge-cleanup")
    print("repo:")
    print(f"  branch: {payload['repo']['branch']}")
    print(f"  head: {payload['repo']['head']}")
    print(f"  clean: {str(payload['repo']['clean']).lower()}")
    return 0

def _patch_args(args: argparse.Namespace) -> list[str]:
    patch_args = [
        args.package,
        "--workflow",
        args.patch_workflow,
        "--repo",
        str(REPO_ROOT),
    ]
    if args.yes:
        patch_args.append("--yes")
    if getattr(args, "branch", None):
        patch_args.extend(["--branch", args.branch])
    if getattr(args, "message", None):
        patch_args.extend(["--message", args.message])
    if getattr(args, "allow_dirty", False):
        patch_args.append("--allow-dirty")
    if getattr(args, "live", False):
        patch_args.append("--live")
    return patch_args


def _run_patch(args: argparse.Namespace) -> int:
    from scripts.codec_patch_install import main as patch_main

    return int(patch_main(_patch_args(args)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codec.py", description="Clean Codec frontend.")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show codec status and diagnostics", description="Show codec status and diagnostics")
    status.add_argument("--json", action="store_true", dest="json_output", help="Emit JSON status")

    prompt = sub.add_parser("prompt", help="Raw/direct LLM lane")
    prompt.add_argument("text", nargs=argparse.REMAINDER, help="Text to send to the raw /prompt lane")

    ground = sub.add_parser("ground", help="Grounded/RAG question lane")
    ground.add_argument("text", nargs=argparse.REMAINDER, help="Question to send to the grounded /ground lane")

    patch = sub.add_parser("patch", help="Patch package workflows")
    patch_sub = patch.add_subparsers(dest="patch_command", required=True)

    review = patch_sub.add_parser("review", help="Run branch -> inspect -> preflight -> apply -> test -> report")
    review.set_defaults(patch_workflow="review")
    review.add_argument("package", help="Patch ZIP path or unpacked package directory")
    review.add_argument("--branch", required=True, help="Patch branch name")
    review.add_argument("--yes", action="store_true", required=True, help="Required approval for the review workflow")
    review.add_argument("--allow-dirty", action="store_true", help="Allow dirty repo when the underlying workflow permits it")
    review.add_argument("--live", action="store_true", help="Allow live/network checks when a stage supports them")
    review.set_defaults(func=_run_patch)

    publish = patch_sub.add_parser("publish", help="Run commit -> push")
    publish.set_defaults(patch_workflow="publish")
    publish.add_argument("package", help="Patch ZIP path or unpacked package directory")
    publish.add_argument("--message", required=True, help="Commit message")
    publish.add_argument("--yes", action="store_true", required=True, help="Required approval for the publish workflow")
    publish.add_argument("--allow-dirty", action="store_true", help="Allow dirty repo when the underlying workflow permits it")
    publish.add_argument("--live", action="store_true", help="Allow live/network checks when a stage supports them")
    publish.set_defaults(func=_run_patch)

    merge_cleanup = patch_sub.add_parser("merge-cleanup", help="Run merge -> push -> cleanup")
    merge_cleanup.set_defaults(patch_workflow="merge-cleanup")
    merge_cleanup.add_argument("package", help="Patch ZIP path or unpacked package directory")
    merge_cleanup.add_argument("--branch", required=True, help="Patch branch name to merge and clean up")
    merge_cleanup.add_argument("--yes", action="store_true", required=True, help="Required approval for the merge-cleanup workflow")
    merge_cleanup.add_argument("--allow-dirty", action="store_true", help="Allow dirty repo when the underlying workflow permits it")
    merge_cleanup.add_argument("--live", action="store_true", help="Allow live/network checks when a stage supports them")
    merge_cleanup.set_defaults(func=_run_patch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "status":
        return _status(json_output=bool(getattr(args, "json_output", False)))
    if args.command == "prompt":
        return _run_text_lane("/prompt", args.text, label="prompt")
    if args.command == "ground":
        return _run_text_lane("/ground", args.text, label="ground")
    if args.command == "patch":
        return int(args.func(args))

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
