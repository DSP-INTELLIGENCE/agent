# Codec Roadmap

## Milestone 0 — codec-checkpoint-audit-v1

Confirm current branch, HEAD, clean working tree, help output, py_compile, and pytest. No code changes.

## Milestone 1 — codec-patch-report-hardening-v1

Fix report output so untracked/added files are visible before publish.

Required report sections:

```text
== git status ==
== git diff --stat ==
== git diff ==
== untracked files ==
== untracked file contents ==
```

Added text files should have bounded previews. Binary/unreadable files should be labeled, not hidden.

Likely files: `scripts/codec_patch_install.py`, `tests/test_patch_report_added_files.py`.

## Milestone 2 — codec-patch-package-validation-v1

Reject bad packages early. Validate required root files, flat-root shape, allowed paths, and changed-files.txt versus patch contents.

## Milestone 3 — codec-patch-temp-cleanup-v1

Ensure temp extraction/work dirs under `/tmp` are removed on success, failure, SystemExit, and KeyboardInterrupt.

Shell temp dirs must use:

```bash
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
```

## Milestone 4 — codec-patch-codex-repair-v1

Add Codex as a repair/package-generation helper only. It may create a corrected v2 ZIP and repair report. It must not apply, commit, push, merge, delete branches, sudo, or install packages.

Target command idea:

```bash
python codec-patch.py repair <patch.zip> \
  --repo . \
  --with-codex \
  --codex-profile or-openai-gpt-oss-120b-free \
  --review-log logs/<review-log>.txt
```

## Milestone 5 — codec-patch-ai-instructions-v1

Standardize CODEX.md and CHATGPT.md inside patch packages.

## Milestone 6 — codec-frontend-v2

Continue making codec.py the clean frontend: status, prompt, ground, patch review/publish/merge-cleanup.

## Milestone 7 — codec-docs-reset-v1

Make codec docs match current reality: codec independent, agent out of scope, codec-patch as operator, agent-cli legacy compatibility.
