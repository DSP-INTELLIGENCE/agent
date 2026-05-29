# Codec patcher work: read the repo first

Stop guessing. The patcher is already in the repo. Read the repo before proposing changes.

Work in:

```bash
cd ~/Downloads/codec
source .venv/bin/activate
```

Do **not** work from memory. Do **not** assume the Agent repo layout. Do **not** invent package formats. The current implementation is in the codec repo and must be inspected first.

## 1. First: inspect the actual repo

Run this before making any plan:

```bash
git status --short --untracked-files=all
git branch --show-current
git log --oneline --decorate -8

find . -maxdepth 3 \( \
  -name 'codec.py' \
  -o -name 'codec-patch.py' \
  -o -name 'agent-cli.py' \
  -o -name 'codec_patch_install.py' \
  -o -name 'PATCH.md' \
  -o -name 'HANDOFF.md' \
  -o -name 'README.md' \
\) -print | sort

sed -n '1,240p' codec-patch.py
sed -n '1,320p' scripts/codec_patch_install.py
sed -n '1,260p' codec.py
sed -n '1,260p' PATCH.md
sed -n '1,260p' HANDOFF.md
sed -n '1,220p' README.md

python codec-patch.py --help
python codec.py --help
python agent-cli.py install patch --help
python -m pytest -q
```

Only after that, explain what the repo actually does.

## 2. Current intended repo roles

The codec repo should be treated as the source of truth.

Expected roles:

```text
codec.py
  clean user/operator frontend

codec-patch.py
  patch package operator

scripts/codec_patch_install.py
  current patch workflow engine

agent-cli.py
  legacy compatibility / old CLI surface
```

Do not move files or create a new package skeleton unless explicitly asked.

## 3. Patcher workflow

The patcher workflow is:

```text
review -> inspect report -> publish -> merge-cleanup
```

Expanded:

```text
review:
  branch -> inspect -> preflight -> apply -> test -> report

publish:
  commit -> push

merge-cleanup:
  merge -> push -> cleanup
```

Never publish before review is clean.

Never edit directly on `main`.

Always use a temp branch:

```bash
git switch main
git status --short --untracked-files=all
git switch -c patch/<name>
```

## 4. How to use codec-patch.py

Start clean:

```bash
cd ~/Downloads/codec
source .venv/bin/activate

git status --short --untracked-files=all
git branch --show-current
```

Review first:

```bash
python codec-patch.py ~/Downloads/<patch-name>.zip \
  --repo . \
  --workflow review \
  --yes \
  --branch patch/<patch-name>
```

Stop after review.

Inspect:

```bash
git status --short --untracked-files=all
git diff --stat
git diff
git ls-files --others --exclude-standard
```

Publish only after clean review:

```bash
python codec-patch.py ~/Downloads/<patch-name>.zip \
  --repo . \
  --workflow publish \
  --yes \
  --message "<commit message>"
```

Merge and clean up only after publish succeeds:

```bash
python codec-patch.py ~/Downloads/<patch-name>.zip \
  --repo . \
  --workflow merge-cleanup \
  --yes \
  --branch patch/<patch-name>
```

## 5. Correct ZIP package shape

The ZIP must be flat-rooted.

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

Verify before handing it off:

```bash
unzip -l ~/Downloads/<patch-name>.zip | sed -n '1,120p'
```

If `change.patch` is under a top-level folder, the ZIP is wrong unless the runner explicitly supports nested roots.

## 6. Required package metadata

`changed-files.txt` must list every repo file changed or created.

Example:

```text
codec.py
tests/test_codec_frontend.py
```

`patch.json` must define the package boundary.

Example:

```json
{
  "name": "example-patch-v1",
  "target_branch": "main",
  "requires_live_llm": false,
  "allowed_paths": [
    "codec.py",
    "tests/test_codec_frontend.py"
  ],
  "does_not_modify": [
    "agent-cli.py",
    "core/",
    "scripts/"
  ],
  "workflows": [
    "review",
    "publish",
    "merge-cleanup"
  ],
  "publish_requires_clean_review": true,
  "ai_assistant_instructions": [
    "CODEX.md",
    "CHATGPT.md"
  ]
}
```

If the patch creates a file and it is missing from `changed-files.txt`, the package is bad.

## 7. Required report behavior

A review report is not clean unless it shows all changes.

If status says:

```text
 M codec.py
?? tests/test_codec_frontend.py
```

then report must account for both:

```text
codec.py
tests/test_codec_frontend.py
```

The patcher still needs hardening here. Report must eventually show:

```text
== git status ==
== git diff --stat ==
== git diff ==
== untracked files ==
== untracked file contents ==
```

Added text files should have bounded previews.

Binary or unreadable files should be labeled, not hidden.

## 8. `/tmp` cleanup rule

The patcher and package stage scripts must clean temp extraction/work dirs under `/tmp`.

Required behavior:

```text
success -> cleanup
failure -> cleanup
SystemExit -> cleanup
KeyboardInterrupt -> best-effort cleanup
```

Any shell script that creates a temp dir must use:

```bash
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
```

No stale `/tmp/codec-patch-*` or package extraction dirs should remain after the command exits.

## 9. Codex integration plan

Codex can be integrated into `codec-patch.py`, but only as a repair/package-generation helper.

Target future command:

```bash
python codec-patch.py repair <patch.zip> \
  --repo . \
  --with-codex \
  --codex-profile or-openai-gpt-oss-120b-free \
  --review-log logs/<review-log>.txt
```

or:

```bash
python codec-patch.py <patch.zip> \
  --repo . \
  --workflow repair \
  --yes \
  --with-codex \
  --codex-profile or-openai-gpt-oss-120b-free \
  --review-log logs/<review-log>.txt
```

Codex may:

```text
inspect failed package
inspect review log
read CODEX.md and CHATGPT.md from package
diagnose failure
create corrected v2 ZIP
write repair report
verify flat-root package shape
scan dangerous shell patterns
```

Codex must not:

```text
apply to main
commit
push
merge
delete branches
run sudo
install packages
run curl | sh
run wget | sh
hide failed tests
```

Codex should be called non-interactively:

```bash
codex exec --profile or-openai-gpt-oss-120b-free "<repair prompt>"
```

Do not launch the Codex TUI from inside the patcher.

## 10. Implementation milestones

### Milestone 1: codec-checkpoint-audit-v1

Read the repo. Confirm current files, help output, tests, branch, and patcher behavior.

No edits.

### Milestone 2: codec-patch-report-hardening-v1

Fix report so untracked added files are visible.

Likely files:

```text
scripts/codec_patch_install.py
tests/test_patch_report_added_files.py
```

### Milestone 3: codec-patch-package-validation-v1

Validate package shape and `changed-files.txt`.

Reject missing `change.patch`.

Reject or intentionally normalize nested ZIPs.

Catch changed-files mismatches.

### Milestone 4: codec-patch-temp-cleanup-v1

Ensure every temp extraction/work dir under `/tmp` is cleaned on success and failure.

### Milestone 5: codec-patch-codex-repair-v1

Add explicit Codex repair workflow.

No real Codex calls in tests.

Mock subprocess.

Repair must not publish, merge, or mutate `main`.

### Milestone 6: codec-patch-ai-instructions-v1

Standardize `CODEX.md` and `CHATGPT.md` inside patch packages.

### Milestone 7: codec-frontend-v2

Continue cleaning `codec.py` as frontend:

```bash
python codec.py status
python codec.py prompt "..."
python codec.py ground "..."
python codec.py patch review <zip> --yes --branch patch/<name>
```

## 11. What not to do

Do not work in the Agent repo.

Do not resurrect the reverted `codec/` package skeleton.

Do not edit `main`.

Do not manually apply `change.patch`.

Do not run heredoc patching.

Do not publish if review is incomplete.

Do not ignore untracked files.

Do not use root/sudo/install scripts.

Do not paste terminal output back into Bash.

## 12. Golden rule

Read the repo first.

Then:

```text
flat ZIP -> review -> inspect report -> publish -> merge-cleanup
```

Anything else is wrong unless explicitly approved.
