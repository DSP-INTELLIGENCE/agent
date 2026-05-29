# Patch Runner

The patch runner applies packaged changes with validation, reporting, and rollback.

## Safety Rule

Invalid packages must fail before repository mutation.

Failed validation after mutation must roll back cleanly.

## Current Gates

- dirty repository blocking
- `changed-files.txt` enforcement
- forbidden-path enforcement
- `git apply --check`
- package-local smoke tests
- package-local verify tests
- rollback on post-apply failure
- per-run `summary.md`
