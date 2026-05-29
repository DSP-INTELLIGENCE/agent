#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


STAGE_SCRIPTS = {
    "branch": "00_branch.sh",
    "inspect": "00_inspect.sh",
    "preflight": "01_preflight.sh",
    "apply": "02_apply.sh",
    "test": "03_test.sh",
    "report": "04_report.sh",
    "commit": "05_commit.sh",
    "push": "06_push.sh",
    "merge": "07_merge.sh",
    "cleanup": "08_cleanup.sh",
}

APPROVAL_STAGES = {"branch", "preflight", "apply", "test", "commit", "push", "merge", "cleanup"}

WORKFLOWS = {
    "review": ("branch", "inspect", "preflight", "apply", "test", "report"),
    "publish": ("commit", "push"),
    "merge-cleanup": ("merge", "push", "cleanup"),
}

STRUCTURAL_TEST = (
    "python -m py_compile run.py agent-cli.py models.py lanes.py router.py "
    "encoder.py decoder.py executors.py utils.py scripts/codec_patch_install.py && "
    "python run.py --self-test && "
    "python -m pytest -q && "
    "python agent-cli.py --help >/tmp/codec-agent-cli-help.out && "
    "python agent-cli.py status >/tmp/codec-agent-cli-status.out"
)


def run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
    proc = subprocess.run(cmd, cwd=cwd, env=env)
    return int(proc.returncode)


def run_shell(command: str, *, cwd: Path, env: dict[str, str] | None = None) -> int:
    proc = subprocess.run(["bash", "-lc", command], cwd=cwd, env=env)
    return int(proc.returncode)


def output(cmd: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    return proc.stdout if proc.returncode == 0 else proc.stdout + proc.stderr


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise SystemExit(f"{path.name} must contain a JSON object")
    return data


def package_root(package: Path) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if package.is_dir():
        return package.resolve(), None
    if not package.exists():
        raise SystemExit(f"package not found: {package}")
    if not zipfile.is_zipfile(package):
        raise SystemExit(f"package is not a zip file: {package}")
    tmp = tempfile.TemporaryDirectory(prefix="codec-patch-install-")
    root = Path(tmp.name)
    with zipfile.ZipFile(package) as z:
        z.extractall(root)
    return root, tmp


def changed_files(pkg: Path) -> list[str]:
    path = pkg / "changed-files.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def require_clean(repo: Path, *, allow_dirty: bool) -> None:
    status = output(["git", "status", "--short", "--untracked-files=all"], cwd=repo).strip()
    if status and not allow_dirty:
        raise SystemExit("repo is dirty; pass --allow-dirty only if this is intentional\n" + status)


def require_approval(stage: str, yes: bool) -> None:
    if stage in APPROVAL_STAGES and not yes:
        raise SystemExit(f"stage {stage!r} requires --yes")


def stage_env(repo: Path, package: Path, pkg: Path, args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "AGENT_PATCH_REPO": str(repo),
            "AGENT_PATCH_PACKAGE": str(package),
            "AGENT_PATCH_WORKDIR": str(pkg),
            "AGENT_PATCH_STAGE": str(args.stage),
            "AGENT_PATCH_YES": "1" if args.yes else "0",
            "AGENT_PATCH_LIVE": "1" if args.live else "0",
            "AGENT_PATCH_FULL_DIFF": "1" if args.full_diff else "0",
            "AGENT_PATCH_BRANCH": str(args.branch or ""),
        }
    )
    if args.message:
        env["AGENT_PATCH_COMMIT_MESSAGE"] = args.message
    return env


def run_package_stage(pkg: Path, repo: Path, package: Path, args: argparse.Namespace) -> int | None:
    script_name = STAGE_SCRIPTS[args.stage]
    script = pkg / "stages" / script_name
    if not script.exists():
        return None

    cmd = ["bash", str(script)]
    if args.stage == "commit":
        if not args.message:
            raise SystemExit("commit stage requires --message")
        cmd.append(args.message)

    print(f"== package stage: {script_name} ==")
    if getattr(args, "stage", "") == "report":
        print_changed_files_manifest_report(repo, pkg)
    return run(cmd, cwd=repo, env=stage_env(repo, package, pkg, args))



def current_branch(repo: Path) -> str:
    return output(["git", "branch", "--show-current"], cwd=repo).strip()


def local_branch_exists(repo: Path, branch: str) -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", branch],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    return proc.returncode == 0


def remote_tracking_branch_exists(repo: Path, branch: str) -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    return proc.returncode == 0


def require_patch_branch(branch: str | None) -> str:
    value = str(branch or "").strip()
    if not value:
        raise SystemExit("branch stage requires --branch")
    if value in {"main", "master"}:
        raise SystemExit("refusing to use main/master as a patch branch")
    if value.startswith("-") or ".." in value or value.endswith("/"):
        raise SystemExit(f"unsafe branch name: {value!r}")
    return value


def builtin_branch(repo: Path, args: argparse.Namespace) -> int:
    require_clean(repo, allow_dirty=args.allow_dirty)
    branch = require_patch_branch(args.branch)
    current = current_branch(repo)
    if current != "main":
        print(f"current branch: {current}")
        print("switching to main before creating/switching patch branch")
    if run(["git", "switch", "main"], cwd=repo) != 0:
        return 1
    if local_branch_exists(repo, branch):
        print(f"switching existing branch: {branch}")
        return run(["git", "switch", branch], cwd=repo)
    print(f"creating branch: {branch}")
    return run(["git", "switch", "-c", branch], cwd=repo)


def builtin_merge(repo: Path, args: argparse.Namespace) -> int:
    require_clean(repo, allow_dirty=args.allow_dirty)
    branch = str(args.branch or "").strip() or current_branch(repo)
    branch = require_patch_branch(branch)
    current = current_branch(repo)
    if current != "main":
        if current == branch:
            print(f"switching from patch branch {branch} to main before merge")
        else:
            print(f"switching from {current} to main before merge")
        if run(["git", "switch", "main"], cwd=repo) != 0:
            return 1
    print(f"merging {branch} into main with --ff-only")
    return run(["git", "merge", "--ff-only", branch], cwd=repo)


def builtin_cleanup(repo: Path, args: argparse.Namespace) -> int:
    require_clean(repo, allow_dirty=args.allow_dirty)
    branch = require_patch_branch(args.branch)
    current = current_branch(repo)

    if current == branch:
        print(f"switching from patch branch {branch} to main before cleanup")
        if run(["git", "switch", "main"], cwd=repo) != 0:
            return 1
    elif current != "main":
        print(f"current branch: {current}")
        print("switching to main before cleanup")
        if run(["git", "switch", "main"], cwd=repo) != 0:
            return 1

    if local_branch_exists(repo, branch):
        print(f"deleting local branch: {branch}")
        if run(["git", "branch", "-d", branch], cwd=repo) != 0:
            return 1
    else:
        print(f"local branch not found; skipping: {branch}")

    if remote_tracking_branch_exists(repo, branch):
        print(f"deleting remote branch: origin/{branch}")
        return run(["git", "push", "origin", "--delete", branch], cwd=repo)

    print(f"remote tracking branch not found; skipping: origin/{branch}")
    return 0


def builtin_inspect(pkg: Path, repo: Path) -> int:
    print("== patch package ==")
    print(f"package: {pkg}")
    readme = pkg / "README.md"
    if readme.exists():
        print(readme.read_text())

    print("== patch metadata ==")
    metadata = load_json(pkg / "patch.json")
    print(json.dumps(metadata, indent=2, sort_keys=True))

    print("== changed files ==")
    for path in changed_files(pkg):
        print(path)

    print("== patch stat ==")
    patch = pkg / "change.patch"
    if patch.exists():
        run(["git", "apply", "--stat", str(patch)], cwd=repo)

    print("== repo status ==")
    sys.stdout.write(output(["git", "status", "--short", "--untracked-files=all"], cwd=repo))

    print("== current HEAD ==")
    sys.stdout.write(output(["git", "log", "--oneline", "-5"], cwd=repo))
    return 0


def builtin_preflight(pkg: Path, repo: Path, args: argparse.Namespace) -> int:
    require_clean(repo, allow_dirty=args.allow_dirty)
    verify = pkg / "tests" / "verify.py"
    if verify.exists() and run([sys.executable, str(verify)], cwd=repo) != 0:
        return 1
    patch = pkg / "change.patch"
    if run(["git", "apply", "--check", str(patch)], cwd=repo) != 0:
        return 1
    return run_shell(STRUCTURAL_TEST, cwd=repo)


def builtin_apply(pkg: Path, repo: Path, args: argparse.Namespace) -> int:
    require_clean(repo, allow_dirty=args.allow_dirty)
    patch = pkg / "change.patch"
    if run(["git", "apply", "--check", str(patch)], cwd=repo) != 0:
        return 1
    if run(["git", "apply", str(patch)], cwd=repo) != 0:
        return 1
    print("apply passed")
    sys.stdout.write(output(["git", "status", "--short", "--untracked-files=all"], cwd=repo))
    sys.stdout.write(output(["git", "diff", "--stat"], cwd=repo))
    return 0


def builtin_test(pkg: Path, repo: Path, args: argparse.Namespace) -> int:
    smoke = pkg / "tests" / "smoke.sh"
    if smoke.exists() and run(["bash", str(smoke), str(repo)], cwd=repo) != 0:
        return 1
    verify = pkg / "tests" / "verify.py"
    if verify.exists() and run([sys.executable, str(verify)], cwd=repo) != 0:
        return 1
    return run_shell(STRUCTURAL_TEST, cwd=repo)


# codec-patcher-report-v4:start
def _codec_patcher_report_package_root(package: Path):
    package = Path(package)
    if package.is_dir():
        return package, None
    result = package_root(package)
    if isinstance(result, tuple):
        return result
    return result, None


def _codec_patcher_report_changed_files(package: Path) -> list[str]:
    pkg, tmp = _codec_patcher_report_package_root(Path(package))
    try:
        manifest = pkg / "changed-files.txt"
        if not manifest.exists():
            return []
        return [
            line.strip()
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    finally:
        if tmp is not None:
            tmp.cleanup()


def print_changed_files_manifest_report(repo: Path, package: Path) -> None:
    """Print a manifest-driven changed-files report, including untracked files."""
    changed_files = _codec_patcher_report_changed_files(Path(package))

    print("== report: changed-files.txt ==")
    if not changed_files:
        print("(none)")
        return
    for item in changed_files:
        print(item)

    print("== report: changed-files status ==")
    for item in changed_files:
        status = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all", "--", item],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        output = status.stdout.strip()
        if output:
            print(output)
        else:
            print(f"   {item}")

    print("== report: changed-files diff stat ==")
    diff_stat = subprocess.run(
        ["git", "diff", "--stat", "--"] + changed_files,
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if diff_stat.stdout.strip():
        print(diff_stat.stdout.rstrip())
    else:
        print("(no tracked diff stat; see changed-files status for untracked/new files)")
# codec-patcher-report-v4:end

def builtin_report(repo: Path, args: argparse.Namespace) -> int:
    # codec-patcher-report-v4: manifest-driven report for tracked and untracked files
    print_changed_files_manifest_report(repo, Path(args.package))
    print("== git status ==")
    sys.stdout.write(output(["git", "status", "--short", "--untracked-files=all"], cwd=repo))
    print("\n== git diff --stat ==")
    sys.stdout.write(output(["git", "diff", "--stat"], cwd=repo))
    if args.full_diff:
        print("\n== git diff ==")
        sys.stdout.write(output(["git", "diff"], cwd=repo))
    return 0


def builtin_commit(pkg: Path, repo: Path, args: argparse.Namespace) -> int:
    if not args.message:
        raise SystemExit("commit stage requires --message")
    files = changed_files(pkg)
    if not files:
        raise SystemExit("changed-files.txt is empty")
    if run(["git", "add", *files], cwd=repo) != 0:
        return 1
    sys.stdout.write(output(["git", "status", "--short", "--untracked-files=all"], cwd=repo))
    return run(["git", "commit", "-m", args.message], cwd=repo)


def builtin_push(repo: Path) -> int:
    branch = output(["git", "branch", "--show-current"], cwd=repo).strip() or "main"
    return run(["git", "push", "origin", branch], cwd=repo)


def run_builtin(pkg: Path, repo: Path, args: argparse.Namespace) -> int:
    if args.stage == "branch":
        return builtin_branch(repo, args)
    if args.stage == "inspect":
        return builtin_inspect(pkg, repo)
    if args.stage == "preflight":
        return builtin_preflight(pkg, repo, args)
    if args.stage == "apply":
        return builtin_apply(pkg, repo, args)
    if args.stage == "test":
        return builtin_test(pkg, repo, args)
    if args.stage == "report":
        return builtin_report(repo, args)
    if args.stage == "commit":
        return builtin_commit(pkg, repo, args)
    if args.stage == "push":
        return builtin_push(repo)
    if args.stage == "merge":
        return builtin_merge(repo, args)
    if args.stage == "cleanup":
        return builtin_cleanup(repo, args)
    raise SystemExit(f"unsupported stage: {args.stage}")


def _workflow_stage_args(args: argparse.Namespace, stage: str) -> argparse.Namespace:
    values = vars(args).copy()
    values["stage"] = stage
    if stage == "report":
        values["full_diff"] = True
    return argparse.Namespace(**values)


def run_workflow(pkg: Path, repo: Path, package: Path, args: argparse.Namespace) -> int:
    workflow = str(args.workflow or "")
    stages = WORKFLOWS.get(workflow)
    if not stages:
        raise SystemExit(f"unsupported workflow: {workflow}")
    if not args.yes:
        raise SystemExit(f"workflow {workflow!r} requires --yes")

    print(f"== workflow: {workflow} ==")
    for stage in stages:
        stage_args = _workflow_stage_args(args, stage)
        print(f"== workflow stage: {stage} ==")
        try:
            require_approval(stage, stage_args.yes)
            code = run_package_stage(pkg, repo, package, stage_args)
            if code is None:
                code = run_builtin(pkg, repo, stage_args)
        except SystemExit:
            print(f"workflow failed at stage: {stage}")
            raise
        if code != 0:
            print(f"workflow failed at stage: {stage} exit={code}")
            return int(code)
    print(f"workflow passed: {workflow}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one staged patch package step.")
    parser.add_argument("package", help="Patch ZIP path or unpacked package directory")
    parser.add_argument(
        "--stage",
        choices=tuple(STAGE_SCRIPTS),
        default="inspect",
        help="One stage to run; no stage advances automatically.",
    )
    parser.add_argument(
        "--workflow",
        choices=tuple(WORKFLOWS),
        help="Run a named multi-stage workflow; review stops before commit/push/merge/cleanup.",
    )
    parser.add_argument("--repo", default=".", help="Repository root")
    parser.add_argument("--yes", action="store_true", help="Required for mutating/advancing stages")
    parser.add_argument("--message", help="Commit message for commit stage")
    parser.add_argument("--branch", help="Patch branch name for branch/merge stages")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow dirty repo for apply/preflight")
    parser.add_argument("--full-diff", action="store_true", help="Print full diff in report stage")
    parser.add_argument("--live", action="store_true", help="Allow live/network checks when a stage supports them")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    package = Path(args.package).expanduser().resolve()

    require_approval(args.stage, args.yes)

    pkg, tmp = package_root(package)
    try:
        if args.workflow:
            return run_workflow(pkg, repo, package, args)
        code = run_package_stage(pkg, repo, package, args)
        if code is not None:
            return code
        return run_builtin(pkg, repo, args)
    finally:
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
