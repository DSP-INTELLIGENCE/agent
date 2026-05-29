# Patch Package Builder

`scripts/make_patch_package.py` builds patch ZIP packages from real `git diff` output.

Purpose:

- avoid hand-written corrupt patches
- generate `change.patch` from the worktree
- generate `changed-files.txt`
- generate `patch.json`
- generate `checksums.txt`
- include default package-local smoke and verify tests

## Usage

Package unstaged changes:

```bash
./scripts/agent_python.sh scripts/make_patch_package.py \
  --name example-change \
  --description "Example patch" \
  --risk low \
  --allowed-path docs/ \
  --output ~/Downloads/example-change.zip
```

Package staged changes:

```bash
./scripts/agent_python.sh scripts/make_patch_package.py \
  --name example-change \
  --description "Example patch" \
  --staged \
  --output ~/Downloads/example-change.zip
```

Then run the normal patch runner:

```bash
./scripts/agent_python.sh scripts/agent_patch_runner.py ~/Downloads/example-change.zip --dry-run
```

## Boundary

The builder packages a patch. It does not apply, commit, push, or bypass `agent_patch_runner.py`.
