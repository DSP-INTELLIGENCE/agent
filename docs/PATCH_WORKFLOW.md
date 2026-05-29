# Patch Workflow

Patch ZIPs are the canonical way agents change this repository.

## Core rule

```text
LLMs propose.
Patch packages carry changes.
Patch runners validate and apply changes.
Git records accepted changes.
Operators approve commit and push.
```

## Package shape

Minimum portable shape:

```text
<patch-name>.patch
changed-files.txt
README.md
apply_patch.sh
```

Full staged shape:

```text
<patch-name>.patch
changed-files.txt
README.md
apply_patch.sh
stages/
  00_inspect.sh
  01_preflight.sh
  02_apply.sh
  03_test.sh
  04_report.sh
  05_commit.sh
  06_push.sh
```

## Stage contract

Run one stage at a time and stop.

| Stage | Purpose | Mutates repo? |
| --- | --- | --- |
| `00_inspect.sh` | Show status, package contents, changed files, and patch stat. | No |
| `01_preflight.sh` | Run `git apply --check` and lightweight syntax/check commands. | No |
| `02_apply.sh` | Apply the patch. | Yes |
| `03_test.sh` | Run relevant tests after apply. | No new mutations expected |
| `04_report.sh` | Show status, diff stat, and review summary. | No |
| `05_commit.sh` | Commit accepted changes. | Yes |
| `06_push.sh` | Push committed changes. | Yes; requires explicit approval |

## Operator commands

```bash
git status --short
git diff
git diff --stat
git apply --check <patch-name>.patch
git apply <patch-name>.patch
git diff --stat
```

Package-runner flow when available:

```bash
./scripts/agent_python.sh scripts/agent_patch_runner.py ~/Downloads/<package>.zip --dry-run
./scripts/agent_python.sh scripts/agent_patch_runner.py ~/Downloads/<package>.zip
```

Commit and push only after review:

```bash
git status --short
git add README.md AGENTS.md docs/README.md docs/DOCS_AUDIT.md docs/PATCH_WORKFLOW.md docs/CODEX_PROMPTS.md docs/CHATGPT_HANDOFF_PROMPT.md docs/ROADMAP_PLAN.md
git commit -m "docs: establish agent handoff and patch workflow"
git push
```

## Safety gates

- Dirty working tree must be reported before apply.
- `git apply --check` must pass before apply.
- New source, tests, and docs must be listed in `changed-files.txt`.
- Package-local smoke tests should run before commit.
- Failed validation after mutation must roll back or report exact state.
- No direct manual patch application when the patch runner is explicitly requested.
- No auto-push.

## Revert commands

Before commit:

```bash
git restore README.md AGENTS.md docs/README.md
git clean -f docs/DOCS_AUDIT.md docs/PATCH_WORKFLOW.md docs/CODEX_PROMPTS.md docs/CHATGPT_HANDOFF_PROMPT.md docs/ROADMAP_PLAN.md
```

After commit:

```bash
git revert HEAD
```
