#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


Step = tuple[str, int, str]


def run(cmd: list[str], *, cwd: Path, report: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    text = f"$ {' '.join(cmd)}\n\nSTDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n\nEXIT: {proc.returncode}\n"
    if report:
        report.write_text(text)
    if check and proc.returncode != 0:
        raise RuntimeError(text)
    return proc


def git_rev_parse(repo: Path, ref: str) -> str:
    proc = run(["git", "rev-parse", ref], cwd=repo)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def write_run_json(
    report_dir: Path,
    *,
    repo: Path,
    package: Path,
    patch: Path | None,
    steps: list[Step],
    status: str,
    metadata: dict | None = None,
    error: str | None = None,
    git_head_before: str = "",
    git_head_after: str = "",
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "repo": str(repo),
        "package": str(package),
        "package_sha256": sha256_file(package) if package.exists() else "",
        "patch": patch.name if patch else None,
        "patch_sha256": sha256_file(patch) if patch and patch.exists() else "",
        "git_head_before": git_head_before,
        "git_head_after": git_head_after,
        "metadata": metadata or {},
        "steps": [
            {"name": name, "exit": code, "report": report}
            for name, code, report in steps
        ],
        "error": error or "",
    }
    (report_dir / "run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_summary(
    report_dir: Path,
    *,
    package: Path,
    patch: Path | None,
    steps: list[Step],
    status: str,
    metadata: dict | None = None,
    error: str | None = None,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Patch Run Summary",
        "",
        f"- Status: `{status}`",
        f"- Package: `{package}`",
        f"- Patch: `{patch.name if patch else 'not found'}`",
        f"- Reports directory: `{report_dir}`",
    ]

    if metadata:
        lines += [
            f"- Name: `{metadata.get('name', '')}`",
            f"- Risk: `{metadata.get('risk', '')}`",
            f"- Description: {metadata.get('description', '')}",
        ]

    lines += [
        "",
        "## Steps",
        "",
        "| Step | Exit | Report |",
        "|---|---:|---|",
    ]
    for name, code, report in steps:
        lines.append(f"| {name} | {code} | `{report}` |")
    if error:
        lines += ["", "## Error", "", "```text", error.strip(), "```"]
    lines.append("")
    (report_dir / "summary.md").write_text("\n".join(lines))


def git_clean(repo: Path) -> bool:
    return run(["git", "status", "--short"], cwd=repo).stdout.strip() == ""


def replay_run(run_json: Path, *, repo: Path) -> int:
    if not run_json.exists():
        raise SystemExit(f"run.json not found: {run_json}")

    payload = json.loads(run_json.read_text())
    package = Path(payload.get("package", ""))
    expected_package_sha = payload.get("package_sha256", "")
    expected_head_before = payload.get("git_head_before", "")
    current_head = git_rev_parse(repo, "HEAD")

    problems: list[str] = []

    if not package.exists():
        problems.append(f"package missing: {package}")
    elif expected_package_sha and sha256_file(package) != expected_package_sha:
        problems.append("package sha256 mismatch")

    if expected_head_before and current_head != expected_head_before:
        problems.append(
            "git HEAD mismatch: "
            + f"current={current_head} expected={expected_head_before}"
        )

    print("# Patch Replay Audit")
    print(f"run_json: {run_json}")
    print(f"status: {payload.get('status')}")
    print(f"package: {package}")
    print(f"current_head: {current_head}")
    print(f"expected_head_before: {expected_head_before}")
    print(f"steps: {len(payload.get('steps', []))}")

    if problems:
        print("")
        print("Replay audit failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("")
    print("Replay audit ok.")
    return 0


def read_patch_metadata(pkgroot: Path) -> dict:
    path = pkgroot / "patch.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise RuntimeError("patch.json must contain a JSON object.")
    return data


def read_package_manifest(pkgroot: Path) -> dict:
    path = pkgroot / "package-manifest.json"
    if not path.exists():
        raise RuntimeError("package-manifest.json is required.")
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise RuntimeError("package-manifest.json must contain a JSON object.")
    return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_signature(pkgroot: Path, *, gpg_keyring: str | None = None) -> bool:
    manifest = pkgroot / "checksums.txt"
    signature = pkgroot / "checksums.txt.sig"

    if not signature.exists():
        return False

    if not manifest.exists():
        raise RuntimeError("checksums.txt.sig exists but checksums.txt is missing.")

    cmd = ["gpg", "--verify", str(signature), str(manifest)]

    if gpg_keyring:
        cmd = [
            "gpg",
            "--no-default-keyring",
            "--keyring",
            gpg_keyring,
            "--verify",
            str(signature),
            str(manifest),
        ]

    proc = subprocess.run(cmd, text=True, capture_output=True)

    if proc.returncode != 0:
        raise RuntimeError(
            "Signature verification failed:\n"
            + proc.stdout
            + proc.stderr
        )

    return True


def verify_checksums(pkgroot: Path) -> None:
    manifest = pkgroot / "checksums.txt"
    if not manifest.exists():
        return

    errors: list[str] = []

    for lineno, raw in enumerate(manifest.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        try:
            expected, rel = line.split(None, 1)
        except ValueError:
            errors.append(f"line {lineno}: expected '<sha256>  <path>'")
            continue

        rel = rel.strip()
        if rel == "checksums.txt" or rel.endswith("/checksums.txt"):
            errors.append(f"line {lineno}: checksums.txt must not include itself")
            continue

        target = pkgroot / rel
        if not target.exists() or not target.is_file():
            errors.append(f"line {lineno}: missing file {rel}")
            continue

        actual = sha256_file(target)
        if actual.lower() != expected.lower():
            errors.append(f"line {lineno}: checksum mismatch for {rel}")

    if errors:
        raise RuntimeError("Checksum verification failed:\n" + "\n".join(errors))


def find_patch(root: Path) -> Path:
    patches = sorted(root.glob("*.patch"))
    if not patches:
        raise SystemExit("No .patch file found in package root.")
    if len(patches) > 1:
        raise SystemExit(f"Multiple .patch files found: {[p.name for p in patches]}")
    return patches[0]


def read_declared_changed_files(pkgroot: Path) -> set[str]:
    path = pkgroot / "changed-files.txt"
    if not path.exists():
        raise RuntimeError("changed-files.txt is required.")
    files = {
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    if not files:
        raise RuntimeError("changed-files.txt is empty.")
    return files


def patch_changed_files(patch: Path) -> set[str]:
    files: set[str] = set()
    for line in patch.read_text(errors="replace").splitlines():
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
        sorted(dict.fromkeys(added)),
        sorted(dict.fromkeys(modified)),
        sorted(dict.fromkeys(deleted)),
        sorted(dict.fromkeys(changed)),
    )


def _normalize_path(path: str) -> str:
    normalized = str(path or "").strip()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def _normalize_manifest_paths(values: object, *, field: str) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise RuntimeError(f"package-manifest.json {field} must be a list of strings.")
    normalized = []
    for raw in values:
        text = raw.strip()
        if text.startswith("./"):
            text = text[2:]
        while "//" in text:
            text = text.replace("//", "/")
        if text:
            normalized.append(text)
    return sorted(dict.fromkeys(normalized))


def _format_path_list(title: str, paths: list[str]) -> list[str]:
    lines = [title]
    if paths:
        lines.extend(f"  - {path}" for path in paths)
    else:
        lines.append("  (none)")
    return lines


def validate_applied_manifest_state(repo: Path, manifest: dict, report_path: Path) -> None:
    expected_changed = _normalize_manifest_paths(manifest.get("changed_files", []), field="changed_files")
    expected_added = _normalize_manifest_paths(manifest.get("staged_added", []), field="staged_added")
    expected_modified = _normalize_manifest_paths(manifest.get("staged_modified", []), field="staged_modified")
    expected_deleted = _normalize_manifest_paths(manifest.get("staged_deleted", []), field="staged_deleted")

    missing_added = sorted(path for path in expected_added if not (repo / path).is_file())
    missing_modified = sorted(path for path in expected_modified if not (repo / path).is_file())
    deleted_present = sorted(path for path in expected_deleted if (repo / path).exists())

    lines = [
        "## Manifest applied-state validation",
        "",
        *(_format_path_list("manifest.changed_files", expected_changed)),
        "",
        *(_format_path_list("manifest.staged_added", expected_added)),
        "",
        *(_format_path_list("manifest.staged_modified", expected_modified)),
        "",
        *(_format_path_list("manifest.staged_deleted", expected_deleted)),
        "",
        *(_format_path_list("missing_added_files", missing_added)),
        "",
        *(_format_path_list("missing_modified_files", missing_modified)),
        "",
        *(_format_path_list("deleted_files_still_present", deleted_present)),
        "",
    ]

    report_path.write_text("\n".join(lines))

    problems: list[str] = []
    if missing_added:
        problems.append("missing added files")
    if missing_modified:
        problems.append("missing modified files")
    if deleted_present:
        problems.append("deleted files still present")

    if problems:
        raise RuntimeError(
            "Manifest applied-state validation failed:\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )


def validate_staged_manifest_state(
    repo: Path,
    manifest: dict,
    declared_files: set[str],
    report_path: Path,
) -> None:
    expected_changed = _normalize_manifest_paths(manifest.get("changed_files", []), field="changed_files")
    expected_added = _normalize_manifest_paths(manifest.get("staged_added", []), field="staged_added")
    expected_modified = _normalize_manifest_paths(manifest.get("staged_modified", []), field="staged_modified")
    expected_deleted = _normalize_manifest_paths(manifest.get("staged_deleted", []), field="staged_deleted")
    declared_changed = sorted(dict.fromkeys(_normalize_path(path) for path in declared_files if _normalize_path(path)))

    proc = run(["git", "diff", "--cached", "--name-status"], cwd=repo, report=report_path, check=True)
    actual_added, actual_modified, actual_deleted, actual_changed = parse_name_status(proc.stdout)

    report_lines = [
        "## Manifest staged-state verification",
        "",
        *(_format_path_list("changed-files.txt.changed_files", declared_changed)),
        "",
        *(_format_path_list("manifest.changed_files", expected_changed)),
        "",
        *(_format_path_list("index.changed_files", actual_changed)),
        "",
        *(_format_path_list("manifest.staged_added", expected_added)),
        "",
        *(_format_path_list("index.staged_added", actual_added)),
        "",
        *(_format_path_list("manifest.staged_modified", expected_modified)),
        "",
        *(_format_path_list("index.staged_modified", actual_modified)),
        "",
        *(_format_path_list("manifest.staged_deleted", expected_deleted)),
        "",
        *(_format_path_list("index.staged_deleted", actual_deleted)),
        "",
    ]

    report_path.write_text("\n".join(report_lines))

    problems: list[str] = []
    if declared_changed != expected_changed:
        problems.append("package-manifest and changed-files.txt mismatch")
    if actual_changed != expected_changed:
        problems.append("manifest/git mismatch")
    if actual_changed != declared_changed:
        problems.append("changed-files.txt/git mismatch")
    if actual_added != expected_added:
        problems.append("staged added files mismatch")
    if actual_modified != expected_modified:
        problems.append("staged modified files mismatch")
    if actual_deleted != expected_deleted:
        problems.append("staged deleted files mismatch")

    if problems:
        raise RuntimeError(
            "Manifest staged-state validation failed:\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )


def rollback_repo(repo: Path, *, report_dir: Path) -> list[Step]:
    steps: list[Step] = []
    proc = run(["git", "reset", "--hard", "HEAD"], cwd=repo, report=report_dir / "rollback-reset.txt", check=True)
    steps.append(("rollback git reset --hard", proc.returncode, "rollback-reset.txt"))
    proc = run(["git", "clean", "-fd", "-e", "reports/patch-runs/"], cwd=repo, report=report_dir / "rollback-clean.txt", check=True)
    steps.append(("rollback git clean -fd", proc.returncode, "rollback-clean.txt"))
    return steps


FORBIDDEN_PATH_PREFIXES = (
    ".git/",
    ".ssh/",
    "secrets/",
    "private/",
    "data_agent/runtime/",
)

FORBIDDEN_PATH_NAMES = {
    ".env",
    ".env.local",
    ".envrc",
    "id_rsa",
    "id_ed25519",
}


def is_forbidden_path(path: str) -> bool:
    normalized = path.strip()

    if normalized.startswith("./"):
        normalized = normalized[2:]

    while "//" in normalized:
        normalized = normalized.replace("//", "/")

    parts = set(normalized.split("/"))

    if normalized in FORBIDDEN_PATH_NAMES:
        return True

    if parts & FORBIDDEN_PATH_NAMES:
        return True

    return any(normalized.startswith(prefix) for prefix in FORBIDDEN_PATH_PREFIXES)


def enforce_forbidden_paths(paths: set[str]) -> None:
    blocked = sorted(path for path in paths if is_forbidden_path(path))
    if blocked:
        raise RuntimeError("Forbidden patch paths:\n" + "\n".join(f"  - {x}" for x in blocked))


def enforce_changed_files(pkgroot: Path, patch: Path) -> None:
    declared = read_declared_changed_files(pkgroot)
    actual = patch_changed_files(patch)
    enforce_forbidden_paths(actual | declared)

    undeclared = sorted(actual - declared)
    missing = sorted(declared - actual)
    if undeclared or missing:
        details = []
        if undeclared:
            details.append("Undeclared patch paths:\n" + "\n".join(f"  - {x}" for x in undeclared))
        if missing:
            details.append("Declared but not touched:\n" + "\n".join(f"  - {x}" for x in missing))
        raise RuntimeError("\n\n".join(details))


def normalize_risk(metadata: dict) -> str:
    risk = str(metadata.get("risk", "low")).strip().lower()
    if risk not in {"low", "medium", "high"}:
        raise RuntimeError(f"Invalid patch risk class: {risk!r}")
    return risk


def path_allowed_by_scope(path: str, allowed_paths: list[str]) -> bool:
    normalized = path.strip()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")

    for raw_prefix in allowed_paths:
        prefix = str(raw_prefix).strip()
        if not prefix:
            continue
        if prefix.startswith("./"):
            prefix = prefix[2:]
        while "//" in prefix:
            prefix = prefix.replace("//", "/")

        if normalized == prefix or normalized.startswith(prefix.rstrip("/") + "/"):
            return True

    return False


def enforce_policy_class(
    *,
    metadata: dict,
    patch: Path,
    allow_dirty: bool,
    require_signature: bool,
    signature_verified: bool,
) -> None:
    risk = normalize_risk(metadata)

    if risk in {"medium", "high"} and allow_dirty:
        raise RuntimeError(f"risk={risk} patches cannot use --allow-dirty.")

    if risk == "high" and not (require_signature and signature_verified):
        raise RuntimeError("risk=high patches require --require-signature and a valid signature.")

    allowed_paths = metadata.get("allowed_paths")
    if allowed_paths is None:
        return

    if not isinstance(allowed_paths, list) or not all(isinstance(x, str) for x in allowed_paths):
        raise RuntimeError("patch.json allowed_paths must be a list of strings.")

    actual = patch_changed_files(patch)
    blocked = sorted(path for path in actual if not path_allowed_by_scope(path, allowed_paths))
    if blocked:
        raise RuntimeError(
            "Patch paths outside allowed_paths:\n"
            + "\n".join(f"  - {x}" for x in blocked)
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply a patch ZIP with reports and patch-specific validation.")
    ap.add_argument("package", nargs="?", help="Patch package zip")
    ap.add_argument("--replay", help="Replay/audit a prior reports/.../run.json without applying anything.")
    ap.add_argument("--repo", default=".", help="Repository root")
    ap.add_argument("--reports-dir", default="reports/patch-runs", help="Reports output directory")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-package-tests", action="store_true")
    ap.add_argument("--full-test", help="Optional full test command, e.g. ./tests.sh")
    ap.add_argument("--require-signature", action="store_true", help="Require checksums.txt.sig and verify it with gpg.")
    ap.add_argument("--gpg-keyring", help="Optional GPG keyring path for signature verification.")
    ap.add_argument("--commit", help="Commit message if checks pass")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()

    if args.replay:
        return replay_run(Path(args.replay).resolve(), repo=repo)

    if not args.package:
        raise SystemExit("Package path required unless --replay is used.")

    package = Path(args.package).resolve()
    if not package.exists():
        raise SystemExit(f"Package not found: {package}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    report_dir = repo / args.reports_dir / stamp
    report_dir.mkdir(parents=True, exist_ok=True)

    git_head_before = git_rev_parse(repo, "HEAD")
    git_head_after = ""

    steps: list[Step] = []
    patch: Path | None = None
    metadata: dict = {}
    rollback_patch: Path | None = None
    applied = False
    committed = False
    declared_files: set[str] = set()

    if not args.allow_dirty and not git_clean(repo):
        proc = run(["git", "status", "--short"], cwd=repo, report=report_dir / "blocked-dirty-status.txt")
        steps.append(("blocked dirty status", proc.returncode, "blocked-dirty-status.txt"))
        git_head_after = git_rev_parse(repo, "HEAD")
        write_summary(report_dir, package=package, patch=patch, steps=steps, status="blocked", metadata=metadata, error="Repo is dirty.")
        write_run_json(report_dir, repo=repo, package=package, patch=patch, steps=steps, status="blocked", metadata=metadata, error="Repo is dirty.", git_head_before=git_head_before, git_head_after=git_head_after)
        raise SystemExit(f"Repo is dirty. See {report_dir}/summary.md or use --allow-dirty.")

    try:
        with tempfile.TemporaryDirectory(prefix="agent-patch-") as td:
            pkgroot = Path(td) / "package"
            pkgroot.mkdir()

            with zipfile.ZipFile(package) as zf:
                zf.extractall(pkgroot)

            signature_verified = verify_signature(pkgroot, gpg_keyring=args.gpg_keyring)

            if args.require_signature and not signature_verified:
                raise RuntimeError("Signature required but checksums.txt.sig is missing.")

            if signature_verified:
                steps.append(("signature verification", 0, "checksums.txt.sig"))

            verify_checksums(pkgroot)
            steps.append(("checksum verification", 0, "checksums.txt"))

            metadata = read_patch_metadata(pkgroot)
            if metadata:
                shutil.copy2(pkgroot / "patch.json", report_dir / "patch.json")

            manifest = read_package_manifest(pkgroot)
            shutil.copy2(pkgroot / "package-manifest.json", report_dir / "package-manifest.json")

            patch = find_patch(pkgroot)

            enforce_policy_class(
                metadata=metadata,
                patch=patch,
                allow_dirty=args.allow_dirty,
                require_signature=args.require_signature,
                signature_verified=signature_verified,
            )
            steps.append(("policy class enforcement", 0, "patch.json"))

            rollback_patch = report_dir / patch.name
            shutil.copy2(patch, rollback_patch)

            declared_files = read_declared_changed_files(pkgroot)
            enforce_changed_files(pkgroot, patch)
            steps.append(("changed-files and forbidden-path enforcement", 0, "changed-files.txt"))

            proc = run(["git", "apply", "--check", str(patch)], cwd=repo, report=report_dir / "git-apply-check.txt", check=True)
            steps.append(("git apply --check", proc.returncode, "git-apply-check.txt"))

            if args.dry_run:
                proc = run(["git", "diff", "--stat"], cwd=repo, report=report_dir / "git-diff-stat-before.txt")
                steps.append(("git diff --stat before", proc.returncode, "git-diff-stat-before.txt"))
                git_head_after = git_rev_parse(repo, "HEAD")
                write_summary(report_dir, package=package, patch=patch, steps=steps, status="dry-run-ok", metadata=metadata)
                write_run_json(report_dir, repo=repo, package=package, patch=patch, steps=steps, status="dry-run-ok", metadata=metadata, git_head_before=git_head_before, git_head_after=git_head_after)
                print(f"Dry run OK. Reports: {report_dir}")
                return 0

            proc = run(["git", "apply", str(patch)], cwd=repo, report=report_dir / "git-apply.txt", check=True)
            steps.append(("git apply", proc.returncode, "git-apply.txt"))
            applied = True

            if not args.no_package_tests:
                smoke = pkgroot / "tests" / "smoke.sh"
                verify = pkgroot / "tests" / "verify.py"

                if smoke.exists():
                    smoke.chmod(0o755)
                    proc = run([str(smoke), str(repo)], cwd=pkgroot, report=report_dir / "package-smoke.txt", check=True)
                    steps.append(("package smoke", proc.returncode, "package-smoke.txt"))

                if verify.exists():
                    proc = run([sys.executable, str(verify), str(repo)], cwd=pkgroot, report=report_dir / "package-verify.txt", check=True)
                    steps.append(("package verify", proc.returncode, "package-verify.txt"))

            if args.full_test:
                proc = run(["bash", "-lc", args.full_test], cwd=repo, report=report_dir / "full-test.txt", check=True)
                steps.append(("full test", proc.returncode, "full-test.txt"))

            if args.commit:
                validate_applied_manifest_state(repo, manifest, report_dir / "manifest-state.txt")
                steps.append(("manifest applied-state validation", 0, "manifest-state.txt"))

                add_paths = sorted(declared_files)
                if not add_paths:
                    raise RuntimeError("changed-files.txt is required before commit.")

                proc = run(["git", "add", "-A", "--", *add_paths], cwd=repo, report=report_dir / "git-add.txt", check=True)
                steps.append(("git add", proc.returncode, "git-add.txt"))

                validate_staged_manifest_state(repo, manifest, declared_files, report_dir / "git-manifest-verify.txt")
                steps.append(("manifest staged-state verification", 0, "git-manifest-verify.txt"))

                proc = run(["git", "status", "--short"], cwd=repo, report=report_dir / "git-status.txt")
                steps.append(("git status", proc.returncode, "git-status.txt"))

                proc = run(["git", "diff", "--cached", "--stat"], cwd=repo, report=report_dir / "git-diff-stat.txt")
                steps.append(("git diff --cached --stat", proc.returncode, "git-diff-stat.txt"))

                proc = run(["git", "diff", "--cached"], cwd=repo, report=report_dir / "git-diff.txt")
                steps.append(("git diff --cached", proc.returncode, "git-diff.txt"))

                proc = run(["git", "commit", "-m", args.commit], cwd=repo, report=report_dir / "git-commit.txt", check=True)
                steps.append(("git commit", proc.returncode, "git-commit.txt"))
                committed = True
            else:
                proc = run(["git", "status", "--short"], cwd=repo, report=report_dir / "git-status.txt")
                steps.append(("git status", proc.returncode, "git-status.txt"))

                proc = run(["git", "diff", "--stat"], cwd=repo, report=report_dir / "git-diff-stat.txt")
                steps.append(("git diff --stat", proc.returncode, "git-diff-stat.txt"))

                proc = run(["git", "diff"], cwd=repo, report=report_dir / "git-diff.txt")
                steps.append(("git diff", proc.returncode, "git-diff.txt"))

            if args.push:
                proc = run(["git", "push"], cwd=repo, report=report_dir / "git-push.txt", check=True)
                steps.append(("git push", proc.returncode, "git-push.txt"))

            git_head_after = git_rev_parse(repo, "HEAD")
            write_summary(report_dir, package=package, patch=patch, steps=steps, status="ok", metadata=metadata)
            write_run_json(report_dir, repo=repo, package=package, patch=patch, steps=steps, status="ok", metadata=metadata, git_head_before=git_head_before, git_head_after=git_head_after)

    except Exception as exc:
        rollback_error = None
        if applied and not committed:
            try:
                rollback_steps = rollback_repo(repo, report_dir=report_dir)
                steps.extend(rollback_steps)
            except Exception as rb_exc:
                rollback_error = str(rb_exc)
                steps.append(("rollback failed", 1, "rollback.txt"))

        error_text = str(exc)
        if rollback_error:
            error_text += "\n\nRollback failed:\n" + rollback_error

        git_head_after = git_rev_parse(repo, "HEAD")
        write_summary(report_dir, package=package, patch=patch, steps=steps, status="failed", metadata=metadata, error=error_text)
        write_run_json(report_dir, repo=repo, package=package, patch=patch, steps=steps, status="failed", metadata=metadata, error=error_text, git_head_before=git_head_before, git_head_after=git_head_after)
        raise SystemExit(f"Patch package failed. See {report_dir}/summary.md") from exc

    print(f"Patch package complete. Reports: {report_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
