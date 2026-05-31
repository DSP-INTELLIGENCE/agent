# General GitHub Patch ZIP Format Outline

## 1. Purpose

A Patch ZIP is a portable, staged change package for any GitHub repository.

It is designed to make repo changes:

```text
branch-first
reviewable
testable
reversible
PR-based
safe to apply manually or with a runner
```

The patch package should separate:

```text
prepare/apply/verify/test
```

from:

```text
commit/push/PR/merge
```

---

## 2. Package naming

Recommended format:

```text
<repo-name>-<milestone-name>-v<N>.zip
```

Examples:

```text
my-app-login-fix-v1.zip
api-service-healthcheck-v2.zip
docs-roadmap-update-v1.zip
frontend-button-styles-v3.zip
patcher-stage-split-v1.zip
```

---

## 3. Top-level ZIP structure

Recommended structure:

```text
<repo-name>-<milestone>-v<N>/
  README.md
  changed-files.txt
  patcher_manifest.json
  <repo-name>-<milestone>-v<N>.patch

  files/
    ...

  scripts/
    00_status.sh
    01_init.sh
    02_install.sh
    03_apply.sh
    04_verify.sh
    05_inspect.sh
    06_test.sh
    07_commit.sh
    08_push.sh
    09_pr.sh
    10_merge.sh
    11_cleanup.sh
    12_post_inspection.sh
    99_revert.sh
```

For very small patches, some scripts can be no-ops, but the stage names should stay consistent.

---

## 4. Required metadata files

## `README.md`

Explains:

```text
what the patch changes
what repo it targets
what branch it creates
what files it touches
how to apply
how to verify
how to test
how to commit/push/PR/merge
how to revert
known risks
```

## `changed-files.txt`

One path per line.

Example:

```text
README.md
src/auth/login.py
tests/test_login.py
docs/roadmap.md
```

Rules:

```text
paths are relative to repo root
do not include .git/
do not include venv/cache/build artifacts
```

## `patcher_manifest.json`

Machine-readable patch metadata.

Example:

```json
{
  "name": "my-app-login-fix-v1",
  "repo_name": "my-app",
  "branch": "patch/login-fix-v1",
  "base_branch": "main",
  "commit_message": "fix login redirect handling",
  "changed_files": [
    "src/auth/login.py",
    "tests/test_login.py"
  ],
  "prepare_stages": [
    "status",
    "init",
    "install",
    "apply",
    "verify",
    "inspect",
    "test"
  ],
  "landing_stages": [
    "commit",
    "push",
    "pr",
    "merge",
    "cleanup",
    "post-inspection"
  ],
  "requires_live_services": false,
  "requires_network": false
}
```

## `.patch`

A git-applyable patch when possible:

```text
<repo-name>-<milestone>-v<N>.patch
```

Use:

```bash
git apply --check patch-file.patch
git apply patch-file.patch
```

## `files/`

Full-file copies for robust fallback.

Example:

```text
files/README.md
files/src/auth/login.py
files/tests/test_login.py
```

Recommended rule:

```text
docs/config/scripts can be full-file copied
source code can use patch or full-file copy depending on risk
```

---

## 5. Stage groups

## Group A — Prepare stages

These stages are safe to run before landing.

```text
status
init
install
apply
verify
inspect
test
```

They should not commit, push, create a PR, or merge.

## Group B — Landing stages

These stages publish the change.

```text
commit
push
pr
merge
cleanup
post-inspection
```

They require explicit approval.

---

## 6. Stage scripts

## `00_status.sh`

Read-only repo status.

Should run:

```bash
pwd
git branch --show-current
git status --short
git log --oneline --decorate -5
```

Should not modify anything.

---

## `01_init.sh`

Creates the patch branch.

Typical behavior:

```bash
git checkout main
git pull --ff-only
git checkout -b patch/<milestone>-v<N>
```

Rules:

```text
fail if working tree is dirty
do not edit files
do not overwrite existing branches unless explicitly approved
```

---

## `02_install.sh`

Installs or verifies dependencies.

Examples:

Python:

```bash
python -m pip install -e .
```

Node:

```bash
npm ci
```

Rust:

```bash
cargo fetch
```

Go:

```bash
go mod download
```

Docs-only:

```bash
echo "No install needed"
```

Rules:

```text
prefer existing project-local env/tooling
avoid global installs unless explicitly required
do not silently change lockfiles unless expected
```

---

## `03_apply.sh`

Applies the patch.

Possible methods:

```bash
git apply --check <patch>
git apply <patch>
```

or full-file copy:

```bash
cp -R files/. .
```

Rules:

```text
must be on the patch branch
must not edit main directly
must stop on conflict
must not commit
must not push
```

---

## `04_verify.sh`

Verifies expected files and structure.

Examples:

```bash
test -f src/auth/login.py
test -f tests/test_login.py
python -m py_compile src/auth/login.py
```

For Node:

```bash
node --check scripts/tool.js
```

For docs:

```bash
test -f docs/roadmap.md
```

Rules:

```text
fail early if required files are missing
verify executable bits for scripts
verify config syntax where possible
```

---

## `05_inspect.sh`

Shows the diff for human review.

Should run:

```bash
git status --short
git diff --stat
git diff
```

For large diffs:

```bash
git diff --stat
git diff --name-only
```

Rules:

```text
read-only
no edits
no tests
no commit
```

---

## `06_test.sh`

Runs test suite/checks.

Examples:

Python:

```bash
python -m unittest discover -s tests -p 'test_*.py'
pytest
```

Node:

```bash
npm test
npm run lint
```

Rust:

```bash
cargo test
cargo clippy
```

Go:

```bash
go test ./...
```

Generic:

```bash
make test
```

Rules:

```text
unit tests before live/integration tests
stop on failure
do not commit if tests fail
```

---

## `07_commit.sh`

Commits the patch branch.

Should run:

```bash
git status --short
git diff --stat
git add <explicit paths>
git commit -m "<message>"
```

Rules:

```text
explicit file list preferred
do not git add .
unless manifest excludes junk
do not commit build artifacts
do not commit on main
```

---

## `08_push.sh`

Pushes patch branch.

Should run:

```bash
git push -u origin patch/<milestone>-v<N>
```

Rules:

```text
push branch only
do not push main directly
```

---

## `09_pr.sh`

Creates a pull request.

Using GitHub CLI:

```bash
gh pr create --fill
```

or explicit title/body:

```bash
gh pr create --title "<title>" --body "<body>"
```

Rules:

```text
show PR URL
do not merge automatically unless separately instructed
```

---

## `10_merge.sh`

Merges the PR.

Preferred:

```bash
gh pr merge --squash --delete-branch
```

Other valid modes:

```bash
gh pr merge --merge --delete-branch
gh pr merge --rebase --delete-branch
```

Rules:

```text
requires explicit approval
prefer squash merge for patch packages
delete remote branch after merge when appropriate
```

---

## `11_cleanup.sh`

Cleans local temporary files.

Allowed cleanup examples:

```bash
rm -rf .patch_backups/<patch-name>
rm -rf .tmp_patch/<patch-name>
```

Rules:

```text
only remove exact known temp paths
never rm -rf broad paths
never remove source files unless listed in manifest
```

---

## `12_post_inspection.sh`

Verifies final main branch state.

Should run:

```bash
git checkout main
git pull --ff-only
git status --short
git log --oneline --decorate -5
```

And tests if appropriate:

```bash
make test
```

Expected:

```text
on main
synced with origin/main
working tree clean
tests pass
```

---

## `99_revert.sh`

Reverts the patch before or after commit.

Before commit:

```bash
git restore <tracked files>
rm -f <new files>
rm -rf <new dirs if safe/empty>
```

After commit:

```bash
git revert <commit>
```

Rules:

```text
show git status before and after
never delete unrelated files
support exact changed-files.txt paths
```

---

## 7. Approval gates

Prepare stages can be automated:

```bash
00_status.sh
01_init.sh
02_install.sh
03_apply.sh
04_verify.sh
05_inspect.sh
06_test.sh
```

Landing stages require explicit approval:

```bash
07_commit.sh
08_push.sh
09_pr.sh
10_merge.sh
11_cleanup.sh
12_post_inspection.sh
```

Suggested CLI policy:

```text
--yes may approve prepare stages
--allow-landing required for commit/push/pr/merge
--allow-destructive required for cleanup/revert if deletion is involved
```

---

## 8. Safety rules

Every script should begin with:

```bash
#!/usr/bin/env bash
set -euo pipefail
```

Every script should detect repo root:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
```

Every script should verify branch when needed:

```bash
test "$(git branch --show-current)" != "main"
```

Every package should avoid committing:

```text
virtualenvs
node_modules
build artifacts
cache files
logs
secrets
.env files
credentials
```

Typical ignored paths:

```text
.venv/
node_modules/
dist/
build/
target/
__pycache__/
.pytest_cache/
*.pyc
*.egg-info/
.env
.DS_Store
.patch_backups/
```

---

## 9. Common workflows

## Apply and test only

```bash
unzip <patch>.zip -d /tmp
cd <repo>
/tmp/<patch>/scripts/00_status.sh
/tmp/<patch>/scripts/01_init.sh
/tmp/<patch>/scripts/02_install.sh
/tmp/<patch>/scripts/03_apply.sh
/tmp/<patch>/scripts/04_verify.sh
/tmp/<patch>/scripts/05_inspect.sh
/tmp/<patch>/scripts/06_test.sh
```

## Land after approval

```bash
/tmp/<patch>/scripts/07_commit.sh
/tmp/<patch>/scripts/08_push.sh
/tmp/<patch>/scripts/09_pr.sh
/tmp/<patch>/scripts/10_merge.sh
/tmp/<patch>/scripts/11_cleanup.sh
/tmp/<patch>/scripts/12_post_inspection.sh
```

## Revert before landing

```bash
/tmp/<patch>/scripts/99_revert.sh
```

---

## 10. Minimal package

For a tiny docs-only patch:

```text
my-repo-docs-v1/
  README.md
  changed-files.txt
  patcher_manifest.json
  files/
    README.md
  scripts/
    00_status.sh
    01_init.sh
    03_apply.sh
    05_inspect.sh
    06_test.sh
    07_commit.sh
    08_push.sh
    09_pr.sh
    10_merge.sh
    12_post_inspection.sh
    99_revert.sh
```

---

## 11. One-line summary

```text
A GitHub Patch ZIP is a branch-first, stage-scripted package that cleanly separates apply/verify/test from commit/push/PR/merge.
```
