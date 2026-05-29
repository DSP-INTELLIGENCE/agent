#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_TEST_SMOKE = """#!/usr/bin/env bash
set -euo pipefail
repo="${1:?repo path required}"
git -C "$repo" diff --check
"""


DEFAULT_TEST_VERIFY = """#!/usr/bin/env python3
print('verify ok')
"""


IGNORED_UNTRACKED_PREFIXES = (
    ".git/",
    ".venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    "reports/",
    "data_agent/plugin_data/",
    "data_agent/plugins/cli/",
    "data_agent/sessions/",
)

IGNORED_UNTRACKED_SUFFIXES = (
    ".pyc",
    ".zip",
)

IGNORED_UNTRACKED_NAMES = {
    ".DS_Store",
}


class PatchPackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class PatchPackagePlan:
    repo: Path
    output: Path
    name: str
    description: str
    risk: str
    staged: bool
    changed_files: tuple[str, ...]
    staged_added: tuple[str, ...]
    staged_modified: tuple[str, ...]
    staged_deleted: tuple[str, ...]
    relevant_untracked: tuple[str, ...]
    relevant_unstaged: tuple[str, ...]
    package_files: tuple[str, ...]
    missing_from_patch: tuple[str, ...] = field(default_factory=tuple)
    missing_from_metadata: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "repo": str(self.repo),
            "output": str(self.output),
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "staged": self.staged,
            "changed_files": list(self.changed_files),
            "staged_added": list(self.staged_added),
            "staged_modified": list(self.staged_modified),
            "staged_deleted": list(self.staged_deleted),
            "relevant_untracked": list(self.relevant_untracked),
            "relevant_unstaged": list(self.relevant_unstaged),
            "package_files": list(self.package_files),
            "missing_from_patch": list(self.missing_from_patch),
            "missing_from_metadata": list(self.missing_from_metadata),
        }


def run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_output(repo: Path, *args: str) -> str:
    proc = run(["git", *args], cwd=repo)
    if proc.returncode != 0:
        raise PatchPackageError(proc.stderr or f"git {' '.join(args)} failed")
    return proc.stdout


def git_diff(repo: Path, staged: bool) -> str:
    cmd = ["git", "diff", "--binary"]
    if staged:
        cmd.append("--cached")
    proc = run(cmd, cwd=repo)
    if proc.returncode != 0:
        raise PatchPackageError(proc.stderr or "git diff failed")
    return proc.stdout


def parse_name_only(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_name_status(text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    changed: list[str] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0]
        path = ""
        if len(parts) >= 3 and status[:1] in {"R", "C"}:
            path = parts[2]
        elif len(parts) >= 2:
            path = parts[1]

        if not path:
            continue

        changed.append(path)
        if status.startswith("A"):
            added.append(path)
        elif status.startswith("D"):
            deleted.append(path)
        else:
            modified.append(path)

    return (
        _sorted_unique(added),
        _sorted_unique(modified),
        _sorted_unique(deleted),
        _sorted_unique(changed),
    )


def git_untracked(repo: Path) -> list[str]:
    text = git_output(repo, "ls-files", "--others", "--exclude-standard")
    return _sorted_unique(parse_name_only(text))


def git_unstaged(repo: Path) -> list[str]:
    text = git_output(repo, "diff", "--name-only")
    return _sorted_unique(parse_name_only(text))


def is_relevant_untracked(path: str, *, output: Path, repo: Path) -> bool:
    normalized = _normalize_path(path)
    if not normalized:
        return False

    if _is_generated_path(normalized):
        return False

    if _path_matches_output(normalized, output, repo):
        return False

    return True


def _is_generated_path(path: str) -> bool:
    if path in IGNORED_UNTRACKED_NAMES:
        return True
    if any(path.startswith(prefix) for prefix in IGNORED_UNTRACKED_PREFIXES):
        return True
    if any(path.endswith(suffix) for suffix in IGNORED_UNTRACKED_SUFFIXES):
        return True
    return False


def _path_matches_output(path: str, output: Path, repo: Path) -> bool:
    try:
        output_rel = output.resolve(strict=False).relative_to(repo.resolve())
    except Exception:
        return False
    return path == str(output_rel)


def validate_packaging_inputs(
    *,
    repo: Path,
    output: Path,
    staged: bool,
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str]]:
    untracked = git_untracked(repo)
    relevant_untracked = sorted(
        path for path in untracked if is_relevant_untracked(path, output=output, repo=repo)
    )
    if relevant_untracked:
        raise PatchPackageError(
            "Relevant untracked files would be omitted:\n"
            + "\n".join(f"  - {path}" for path in relevant_untracked)
        )

    unstaged: list[str] = []
    if staged:
        unstaged = [
            path for path in git_unstaged(repo) if is_relevant_untracked(path, output=output, repo=repo)
        ]
        if unstaged:
            raise PatchPackageError(
                "Relevant unstaged files would be omitted from --staged package:\n"
                + "\n".join(f"  - {path}" for path in unstaged)
            )

    status_args = ["diff", "--name-status", "--binary"]
    if staged:
        status_args.append("--cached")
    name_status = git_output(repo, *status_args)
    added, modified, deleted, changed = parse_name_status(name_status)
    patch_files = _sorted_unique(patch_changed_files_from_text(git_diff(repo, staged=staged)))
    if set(changed) != set(patch_files):
        raise PatchPackageError(
            build_listed_error(
                "Patch/package metadata mismatch",
                ("Missing from patch", sorted(path for path in changed if path not in patch_files)),
                ("Missing from metadata", sorted(path for path in patch_files if path not in changed)),
            )
        )
    return added, modified, deleted, changed, relevant_untracked, unstaged


def build_patch_plan(
    *,
    repo: Path,
    output: Path,
    name: str,
    description: str,
    risk: str,
    allowed_paths: list[str],
    staged: bool,
) -> PatchPackagePlan:
    risk = risk.strip().lower()
    if risk not in {"low", "medium", "high"}:
        raise PatchPackageError("risk must be one of: low, medium, high")

    if not name.strip():
        raise PatchPackageError("name is required")
    if not description.strip():
        raise PatchPackageError("description is required")

    added, modified, deleted, changed, relevant_untracked, relevant_unstaged = validate_packaging_inputs(
        repo=repo,
        output=output,
        staged=staged,
    )

    diff_text = git_diff(repo, staged=staged)
    if not diff_text.strip():
        raise PatchPackageError(
            "No git diff found. Edit files first or use --staged for staged changes."
        )

    changed_files = _sorted_unique(changed)
    patch_files = _sorted_unique(patch_changed_files_from_text(diff_text))
    missing_from_patch = sorted(path for path in changed_files if path not in patch_files)
    missing_from_metadata = sorted(path for path in patch_files if path not in changed_files)
    if missing_from_patch or missing_from_metadata:
        raise PatchPackageError(
            build_listed_error(
                "Patch/package metadata mismatch",
                ("Missing from patch", missing_from_patch),
                ("Missing from metadata", missing_from_metadata),
            )
        )

    package_files = (
        "README.md",
        "change.patch",
        "changed-files.txt",
        "checksums.txt",
        "package-manifest.json",
        "patch.json",
        "tests/smoke.sh",
        "tests/verify.py",
    )

    return PatchPackagePlan(
        repo=repo,
        output=output,
        name=name,
        description=description,
        risk=risk,
        staged=staged,
        changed_files=tuple(changed_files),
        staged_added=tuple(added),
        staged_modified=tuple(modified),
        staged_deleted=tuple(deleted),
        relevant_untracked=tuple(relevant_untracked),
        relevant_unstaged=tuple(relevant_unstaged),
        package_files=package_files,
        missing_from_patch=tuple(missing_from_patch),
        missing_from_metadata=tuple(missing_from_metadata),
    )


def build_package(
    *,
    repo: Path,
    output: Path,
    name: str,
    description: str,
    risk: str,
    allowed_paths: list[str],
    staged: bool,
    dry_run: bool = False,
) -> PatchPackagePlan:
    plan = build_patch_plan(
        repo=repo,
        output=output,
        name=name,
        description=description,
        risk=risk,
        allowed_paths=allowed_paths,
        staged=staged,
    )

    if dry_run:
        return plan

    with tempfile.TemporaryDirectory(prefix="agent-package-") as td:
        pkg = Path(td) / "package"
        tests = pkg / "tests"
        tests.mkdir(parents=True)

        (pkg / "change.patch").write_text(git_diff(repo, staged=staged))
        (pkg / "changed-files.txt").write_text("\n".join(plan.changed_files) + "\n")
        (pkg / "patch.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "description": description,
                    "risk": risk.strip().lower(),
                    "allowed_paths": allowed_paths,
                    "staged": staged,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        (pkg / "package-manifest.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "description": description,
                    "risk": risk.strip().lower(),
                    "staged": staged,
                    "repo": str(repo),
                    "output": str(output),
                    "changed_files": list(plan.changed_files),
                    "staged_added": list(plan.staged_added),
                    "staged_modified": list(plan.staged_modified),
                    "staged_deleted": list(plan.staged_deleted),
                    "relevant_untracked": list(plan.relevant_untracked),
                    "relevant_unstaged": list(plan.relevant_unstaged),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        (pkg / "README.md").write_text(f"# {name}\n\n{description}\n")

        write_executable(tests / "smoke.sh", DEFAULT_TEST_SMOKE)
        write_executable(tests / "verify.py", DEFAULT_TEST_VERIFY)

        checksum_files = [
            "README.md",
            "change.patch",
            "changed-files.txt",
            "package-manifest.json",
            "patch.json",
            "tests/smoke.sh",
            "tests/verify.py",
        ]
        (pkg / "checksums.txt").write_text(
            "".join(f"{sha256_file(pkg / rel)}  {rel}\n" for rel in checksum_files)
        )

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(pkg.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(pkg))

        verify_package_zip(output, plan)

    return plan


def verify_package_zip(package: Path, plan: PatchPackagePlan) -> None:
    with zipfile.ZipFile(package) as zf:
        names = set(zf.namelist())
        expected = set(plan.package_files)
        if not expected <= names:
            missing = sorted(expected - names)
            raise PatchPackageError(
                "Package ZIP missing expected files:\n" + "\n".join(f"  - {x}" for x in missing)
            )

        manifest = json.loads(zf.read("package-manifest.json").decode("utf-8"))
        if not isinstance(manifest, dict):
            raise PatchPackageError("package-manifest.json must contain a JSON object.")

        for key, expected_value in {
            "changed_files": list(plan.changed_files),
            "staged_added": list(plan.staged_added),
            "staged_modified": list(plan.staged_modified),
            "staged_deleted": list(plan.staged_deleted),
            "relevant_untracked": list(plan.relevant_untracked),
            "relevant_unstaged": list(plan.relevant_unstaged),
        }.items():
            actual_value = manifest.get(key)
            if actual_value != expected_value:
                raise PatchPackageError(
                    f"package-manifest.json mismatch for {key}: expected {expected_value!r} got {actual_value!r}"
                )


def write_executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


def patch_changed_files_from_text(patch_text: str) -> set[str]:
    files: set[str] = set()
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                b_path = parts[3]
                if b_path.startswith("b/"):
                    files.add(b_path[2:])
        elif line.startswith("+++ b/"):
            files.add(line[len("+++ b/"):])
    files.discard("/dev/null")
    return files


def build_listed_error(title: str, *sections: tuple[str, list[str]]) -> str:
    parts = [title]
    for label, items in sections:
        if items:
            parts.append("")
            parts.append(f"{label}:")
            parts.extend(f"  - {item}" for item in items)
    return "\n".join(parts)


def _sorted_unique(items: Iterable[str]) -> list[str]:
    return sorted(dict.fromkeys(item for item in items if item))


def _normalize_path(path: str) -> str:
    normalized = str(path or "").strip()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build an agent patch ZIP package from git diff.")
    ap.add_argument("--repo", default=".", help="Repository root")
    ap.add_argument("--output", required=True, help="Output patch ZIP path")
    ap.add_argument("--name", required=True, help="Patch package name")
    ap.add_argument("--description", required=True, help="Patch description")
    ap.add_argument("--risk", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--allowed-path", action="append", default=[], help="Allowed path prefix; repeatable")
    ap.add_argument("--staged", action="store_true", help="Package staged changes instead of unstaged changes")
    ap.add_argument("--dry-run", action="store_true", help="Validate package completeness without writing the ZIP")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    output = Path(args.output).expanduser().resolve()
    allowed_paths = args.allowed_path or ["docs/", "scripts/", "core/", "tests/"]

    try:
        plan = build_package(
            repo=repo,
            output=output,
            name=args.name,
            description=args.description,
            risk=args.risk,
            allowed_paths=allowed_paths,
            staged=args.staged,
            dry_run=args.dry_run,
        )
    except PatchPackageError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
