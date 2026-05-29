Here’s a clean outline.

## How to use `codec-patch.py` correctly

### 1. Start from a clean repo

```bash
cd ~/Downloads/agent
source .venv/bin/activate

git status --short --untracked-files=all
git branch --show-current
```

Do not continue unless the working tree is clean or you intentionally know why it is dirty.

---

### 2. Put the patch ZIP in `~/Downloads`

Example:

```text
~/Downloads/agent-codec-ground-route-v1.zip
```

The ZIP should be a staged patch package with a normal shape:

```text
README.md
package-manifest.json
patch.json
changed-files.txt
change.patch
apply_patch.sh
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

---

### 3. Always run `review` first

`review` must run on a temporary branch.

```bash
python codec-patch.py ~/Downloads/<patch-name>.zip \
  --repo . \
  --workflow review \
  --yes \
  --branch patch/<patch-name>
```

Example:

```bash
python codec-patch.py ~/Downloads/agent-codec-ground-route-v1.zip \
  --repo . \
  --workflow review \
  --yes \
  --branch patch/agent-codec-ground-route-v1
```

`review` runs:

```text
branch -> inspect -> preflight -> apply -> test -> report
```

It stops before commit, push, merge, or cleanup.

---

### 4. Inspect the review output

Before publishing, check:

```text
preflight passed
apply passed
tests passed
report looks correct
changed files are expected
no unrelated files changed
```

Also run:

```bash
git status --short --untracked-files=all
git diff --stat
git diff
```

Do not publish if anything looks wrong.

---

### 5. Publish only after review is approved

Publishing commits and pushes the temporary branch.

```bash
python codec-patch.py ~/Downloads/<patch-name>.zip \
  --repo . \
  --workflow publish \
  --yes \
  --message "<commit message>"
```

Example:

```bash
python codec-patch.py ~/Downloads/agent-codec-ground-route-v1.zip \
  --repo . \
  --workflow publish \
  --yes \
  --message "route codec ground through ground lane"
```

`publish` runs:

```text
commit -> push
```

It does not merge into `main`.

---

### 6. Merge and clean up separately

Only after publish succeeds:

```bash
python codec-patch.py ~/Downloads/<patch-name>.zip \
  --repo . \
  --workflow merge-cleanup \
  --yes \
  --branch patch/<patch-name>
```

Example:

```bash
python codec-patch.py ~/Downloads/agent-codec-ground-route-v1.zip \
  --repo . \
  --workflow merge-cleanup \
  --yes \
  --branch patch/agent-codec-ground-route-v1
```

`merge-cleanup` runs:

```text
merge -> push -> cleanup
```

It fast-forwards `main`, pushes `main`, and deletes the patch branch.

---

### 7. Final verification

```bash
git status --short --untracked-files=all
git branch --show-current
git log --oneline --decorate -5

python codec.py --help
python codec-patch.py --help
python agent-cli.py --help
python -m pytest -q tests -k "codec or patch"
```

Expected end state:

```text
main
working tree clean
patch branch deleted
main pushed
```

---

## Hard rules

```text
Always use a temp branch.
Always run review first.
Never apply directly on main.
Never skip preflight or tests.
Never publish if report looks wrong.
Never paste terminal output back into Bash.
Never manually run change.patch unless recovering from a broken package on purpose.
Do not use heredocs for patching.
Do not mix unrelated fixes in one patch.
```

## Recovery if review fails

If review fails before commit:

```bash
git status --short --untracked-files=all
git branch --show-current

git switch main
git branch -D patch/<patch-name>
```

If files were applied but not committed:

```bash
git restore .
git clean -fd
git switch main
git branch -D patch/<patch-name>
```

Only use destructive cleanup after checking `git status`.
