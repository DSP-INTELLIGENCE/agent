# Codec Patcher Workflow

ZIP root must be flat:

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

Required operation:

```text
review -> inspect report -> publish -> merge-cleanup
```

Review command:

```bash
python codec-patch.py ~/Downloads/<package>.zip \
  --repo . \
  --workflow review \
  --yes \
  --branch patch/<name>
```

Publish:

```bash
python codec-patch.py ~/Downloads/<package>.zip \
  --repo . \
  --workflow publish \
  --yes \
  --message "<commit message>"
```

Merge cleanup:

```bash
python codec-patch.py ~/Downloads/<package>.zip \
  --repo . \
  --workflow merge-cleanup \
  --yes \
  --branch patch/<name>
```

Report requirements:

```text
git status --short --untracked-files=all
all paths in changed-files.txt
diff stat including new files
full diff including new files
test output
grep checks
```
