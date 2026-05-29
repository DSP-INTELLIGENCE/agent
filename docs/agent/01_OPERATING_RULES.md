# Operating Rules

Hard rules:

```text
No direct edits on main.
No heredocs for patching.
No manual change.patch unless explicitly recovering from a broken package.
No copy/pasted terminal output back into Bash.
No package apply on main.
No publish before review.
No merge before publish is verified.
No reset/clean/force-push unless explicitly approved.
Stop on dirty worktree.
Stop on failed preflight.
Stop on failed tests.
Stop on unexpected diff.
```

Patch operation:

```text
review -> inspect report -> publish -> merge-cleanup
```

Review means:

```text
branch -> inspect -> preflight -> apply -> test -> report
```

Publish means:

```text
commit -> push
```

Merge-cleanup means:

```text
merge -> push -> cleanup
```

Report acceptance criteria:

```text
preflight passed
apply passed
tests passed
changed files exactly match changed-files.txt / patch.json
no unrelated files
no hidden untracked files
no whitespace warnings unless accepted
```

If a package adds a new file, the report must show that new file. If it does not, fix the patcher/report stage first.
