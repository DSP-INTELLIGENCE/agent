# Staged Patch ZIP Package Specification

## ZIP must be flat-rooted

Correct:

```text
README.md
CODEX.md
CHATGPT.md
patch.json
package-manifest.json
changed-files.txt
change.patch
<patch-name>.patch
apply_patch.sh
tests/smoke.sh
tests/verify.py
stages/00_branch.sh
stages/00_inspect.sh
stages/01_preflight.sh
stages/02_apply.sh
stages/03_test.sh
stages/04_report.sh
stages/05_commit.sh
stages/06_push.sh
stages/07_merge.sh
stages/08_cleanup.sh
```

Wrong:

```text
patch-name/README.md
patch-name/change.patch
patch-name/stages/...
```

Verify:

```bash
unzip -l ~/Downloads/<patch-name>.zip | sed -n '1,120p'
```

## Required metadata

Example `patch.json`:

```json
{
  "name": "example-patch-v1",
  "target_branch": "main",
  "requires_live_llm": false,
  "allowed_paths": ["codec.py", "tests/test_codec_frontend.py"],
  "does_not_modify": ["agent-cli.py", "core/", "scripts/"],
  "workflows": ["review", "publish", "merge-cleanup"],
  "publish_requires_clean_review": true,
  "ai_assistant_instructions": ["CODEX.md", "CHATGPT.md"]
}
```

`changed-files.txt` must list every changed or created repo file.

## Stage script rules

Every stage script starts with:

```bash
#!/usr/bin/env bash
set -euo pipefail
```

Any temp dir must be cleaned:

```bash
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
```

## Dangerous command scan

```bash
unzip -p ~/Downloads/<patch-name>.zip '*.sh' 'tools/*' 'tests/*' 'CODEX.md' 'CHATGPT.md' 2>/dev/null \
  | grep -E 'sudo|curl .*\|.*sh|wget .*\|.*sh|dd if=|mkfs|docker run --privileged|rm -rf /|chmod 777 /' || true
```

Executable scripts must not contain dangerous commands. Policy text saying “do not run sudo” is acceptable.
