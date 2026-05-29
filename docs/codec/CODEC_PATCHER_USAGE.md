# How to Use codec-patch.py Correctly

## Start clean

```bash
cd ~/Downloads/codec
source .venv/bin/activate

git status --short --untracked-files=all
git branch --show-current
```

Expected: `main` and no dirty files.

## Review first

```bash
python codec-patch.py ~/Downloads/<patch-name>.zip \
  --repo . \
  --workflow review \
  --yes \
  --branch patch/<patch-name>
```

This runs: `branch -> inspect -> preflight -> apply -> test -> report`. Stop after review.

## Inspect after review

```bash
git status --short --untracked-files=all
git diff --stat
git diff
git ls-files --others --exclude-standard
```

Review is clean only if tests passed, report shows all changed files, untracked files are accounted for, changed-files.txt matches actual changes, and no unexpected files changed.

## Publish only after clean review

```bash
python codec-patch.py ~/Downloads/<patch-name>.zip \
  --repo . \
  --workflow publish \
  --yes \
  --message "<commit message>"
```

## Merge and cleanup

```bash
python codec-patch.py ~/Downloads/<patch-name>.zip \
  --repo . \
  --workflow merge-cleanup \
  --yes \
  --branch patch/<patch-name>
```

## If review fails

```bash
git status --short --untracked-files=all
git diff --stat
git diff

git restore .
git clean -fd
git switch main
git branch -D patch/<patch-name>
```

Then create `<patch-name>-v2.zip`.

## Golden rule

```text
flat ZIP -> review -> inspect report -> publish -> merge-cleanup
```
