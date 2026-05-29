# Recovery and Reset Commands

## Reset repo to origin/main

Warning: deletes local tracked and untracked changes.

```bash
cd ~/Downloads/codec
source .venv/bin/activate 2>/dev/null || true

git status --short --untracked-files=all
git branch --show-current

git switch main
git fetch origin
git reset --hard origin/main
git clean -fd

git status --short --untracked-files=all
git branch --show-current
git log --oneline --decorate -5
```

## Recover from failed review branch

```bash
git status --short --untracked-files=all
git diff --stat
git diff

git restore .
git clean -fd
git switch main
git branch -D patch/<patch-name>

git status --short --untracked-files=all
```

## Revert a bad landed commit safely

Use `git revert`, not hard reset, when pushed:

```bash
git switch main
git status --short --untracked-files=all
git log --oneline --decorate -8

git branch backup/before-revert-$(date -u +%Y%m%dT%H%M%SZ)
git revert --no-edit <bad-commit>

python -m pytest -q
git push origin main
```
