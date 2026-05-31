Yes. That should be the workflow.

For every milestone:

```text
1. read roadmap
2. choose the next unchecked item
3. write milestone plan first
4. put plan in roadmap/milestones/
5. audit / inspect
6. check status
7. patch
8. verify
9. test
10. cleanup
11. update roadmap checked/unchecked
12. commit only after approval
```

And for docs:

```text
RULES.md applies:
- write full docs in chat
- you copy them
- no doc diffs
- no markdown heredocs
- no scripts generating markdown docs
```

Milestone plan template:

```markdown
# <Milestone Name>

## Purpose

<What this milestone does and what it will accomplish.>

## Audit / Inspect

Commands and checks:

    git status --short
    git diff --stat
    rg -n '<terms>' <paths>
    python -m pytest

## Status

- Branch:
- Repo clean before patch:
- Known conflicts:
- Untracked files:
- Ready for patch:

## Patch Plan

Files expected to change:

- <file>
- <file>

Expected behavior changes:

- <change>
- <change>

## Verification

Commands:

    git status --short
    git diff --stat
    rg -n '<verification terms>' <paths>

Expected result:

- <expected result>

## Tests

Commands:

    python -m pytest

Expected result:

- Tests pass.

## Cleanup

- Remove temporary files.
- Clean `data/patch/` if used.
- Keep ZIPs in `data/zip/`.
- Update roadmap checked/unchecked items.
```
