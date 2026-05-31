Use this as `INSTRUCTIONS.md`:

````markdown
# Repository Instructions

Read the repository documents before making changes.

The repository is managed through milestones, staged patches, and reviewable patch ZIPs. Do not commit until the patch has been applied, verified, tested, and approved.

## Normalize First

Before starting feature or documentation work, inspect the repository state.

If the repo is dirty, conflicted, partially patched, or has duplicated/generated files in the wrong place, prepare a normalization branch first.

Normalization work should:

1. inspect the current repo state
2. identify conflicts, untracked files, duplicate docs, nested repos, stale patch files, and misplaced ZIPs
3. clean or organize the repo before new patch work begins
4. leave the repo ready for the next branch

Useful commands:

```bash
git status --short
git diff --stat
git diff
find . -name .git -type d
rg -n "TODO|FIXME|deprecated|legacy|obsolete|conflict|<<<<<<<|======|>>>>>>>" .
````

## Repository Layout

```text
docs/                  Copy all active docs here.
data/patch/            Unzip patches here. Delete patch contents when done.
data/zip/              Copy all patch ZIPs from ~/Downloads or ../ into this folder.
roadmap/               Put roadmap plans here.
roadmap/milestones/    Put milestone plans here.
```

Do not create nested repositories inside this repo.

Do not leave extracted patch packages scattered around the repo.

Do not leave patch ZIPs in the repo root.

## Roadmap

The roadmap describes the project direction and milestone progress.

Use:

```text
roadmap/
roadmap/milestones/
```

The roadmap should contain:

1. project outline
2. active milestones
3. completed milestones
4. checked and unchecked work items
5. links or references to milestone plans

When a milestone is completed, update the roadmap and mark that milestone checked.

Look in `roadmap/milestones/` for completed plans before creating new ones.

## Docs

All active documentation belongs in:

```text
docs/
```

When a patch changes documentation, copy the complete updated document into the repo. Do not rely on partial documentation diffs as the only source of truth.

Docs should be consistent with:

1. the active runtime
2. the current CLI surface
3. the current lane model
4. the current patch workflow
5. the current roadmap

Archive or clearly label stale docs instead of leaving them mixed with active instructions.

## Milestones

Each milestone must have a plan in:

```text
roadmap/milestones/
```

A milestone plan should include:

1. Purpose
   Outline what the milestone does and what it will accomplish.

2. Audit / Inspect
   List the scripts, commands, and analysis needed before patching. Use `rg`, `grep`, `git`, tests, and any repo-specific tools needed.

3. Status
   Check the repo status and confirm it is ready for the next branch and patch.

4. Patch Plan
   List the files and behavior expected to change.

5. Verification
   List commands or checks that prove the patch worked.

6. Tests
   List smoke tests and full tests that should run before commit.

7. Cleanup
   List temporary files, extracted patches, or audit artifacts to remove after completion.

## Patch Instructions

For every patch:

1. create or update the milestone plan
2. put the plan in `roadmap/milestones/`
3. apply the patch in stages
4. verify the patch
5. run smoke tests
6. update the roadmap when the milestone is finished
7. mark completed milestone items checked

## General Patch Format

Package patches as ZIP files.

Patch ZIPs must extract flat into:

```text
data/patch/
```

A patch ZIP should contain:

```text
apply_patch.sh
changed-files.txt
README.md
<patch-name>.patch
stages/
```

The ZIP should not create an extra nested package directory.

Correct:

```text
data/patch/apply_patch.sh
data/patch/changed-files.txt
data/patch/<patch-name>.patch
data/patch/README.md
data/patch/stages/
```

Incorrect:

```text
data/patch/<package-name>/<package-name>/apply_patch.sh
```

ZIP files should be copied into:

```text
data/zip/
```

Use:

```bash
mkdir -p data/patch data/zip
cp ~/Downloads/*.zip data/zip/ 2>/dev/null || true
unzip data/zip/<patch-package>.zip -d data/patch
```

Clean `data/patch/` before extracting a new patch unless the current patch is still being reviewed.

```bash
rm -rf data/patch/*
```

## Install Stage

Install prepares the repo for patching.

Steps:

1. unzip the patch ZIP to `data/patch/`
2. copy ZIP files from `~/Downloads` or `../` to `data/zip/`
3. prepare the repo branch
4. confirm the patch package layout is correct

Example:

```bash
cd <repo-root>

mkdir -p data/patch data/zip
cp ~/Downloads/*.zip data/zip/ 2>/dev/null || true

rm -rf data/patch/*
unzip data/zip/<patch-package>.zip -d data/patch

git status --short
git switch -c <normalization-or-feature-branch>
```

## Apply Stage

Apply the patch.

Steps:

1. apply the patch
2. verify that the patch worked
3. if verification fails, run audit and inspection commands
4. run smoke tests before the commit stage

Example:

```bash
cd <repo-root>/data/patch
./apply_patch.sh
```

Then:

```bash
cd <repo-root>
git status --short
git diff --stat
git diff
```

## Verification

Verification confirms the patch applied cleanly and changed the intended files.

Use:

```bash
git status --short
git diff --stat
git diff
git apply --check data/patch/<patch-name>.patch
```

If verification fails, do not commit. Run audit commands and inspect the broken state.

## Audit / Inspect

Use audit and inspect scripts when:

1. the patch fails
2. tests fail
3. docs conflict
4. files appear in the wrong location
5. the repo has duplicate files or nested repositories
6. the runtime and docs disagree

Useful commands:

```bash
git status --short
git diff --stat
git diff
find . -name .git -type d
find . -maxdepth 4 -type f | sort
rg -n "TODO|FIXME|deprecated|legacy|obsolete" .
rg -n "<<<<<<<|=======|>>>>>>>" .
rg -n "codec|agent-cli|frontdoor|front_door|runtime_decoder|lane_invocation" .
rg -n "/question|/web|/scrape|/switch|/tool|semantic router|AgentSpec|AgentScript|plugin|plugins" .
```

## Tests

Run smoke tests before committing.

Preferred:

```bash
python -m pytest
```

If the repo has targeted tests, run those first, then the full suite.

Example:

```bash
python -m pytest tests/test_runtime_context.py
python -m pytest
```

Do not proceed to commit if tests fail unless the failure is expected and documented in the milestone plan.

## Commit Stage

Only begin the commit stage after the patch is verified and tests are complete.

Steps:

1. commit
2. push
3. create PR
4. review PR
5. merge PR

Commands:

```bash
git status --short
git diff --stat
git add <changed-files>
git commit -m "<commit message>"
git push -u origin <branch-name>
gh pr create --fill
gh pr view --web
```

Merge only after review and approval.

## Cleanup

After the patch is committed or abandoned:

1. remove temporary patch files
2. clean `data/patch/`
3. keep ZIP archives in `data/zip/`
4. put milestone and patch docs in `roadmap/milestones/`
5. update the roadmap

Example:

```bash
rm -rf data/patch/*
git status --short
```

## Patch Stages

Patch work is done in stages. Do not commit until the patch is approved.

### 1. Audit / Inspect Scripts

Scripts needed to audit the repo before patching.

Use:

```bash
rg
grep
git
find
python -m pytest
```

### 2. Status Script

Check that the repo is correct and ready to patch.

Use:

```bash
git status --short
git diff --stat
git diff
```

### 3. Install Script

Prepare the repo and branch for the patch.

Responsibilities:

1. create required folders
2. copy ZIPs to `data/zip/`
3. unzip patch into `data/patch/`
4. create or switch to the patch branch

### 4. Apply Script

Apply the patch and copy full docs into place.

Responsibilities:

1. run `git apply`
2. copy complete docs when needed
3. report changed files

### 5. Verify

Verify the patch worked.

Use:

```bash
git status --short
git diff --stat
git diff
```

### 6. Audit

If the patch breaks, run audit scripts to locate conflicts, bad diffs, missing files, duplicate files, or stale references.

### 7. Tests

Run smoke tests and full tests.

Use:

```bash
python -m pytest
```

### 8. Commit

Only after approval:

```bash
git add <changed-files>
git commit -m "<message>"
git push -u origin <branch>
gh pr create --fill
gh pr view --web
```

Then review and merge.

### 9. Cleanup

Remove temporary files and extracted patch contents.

```bash
rm -rf data/patch/*
```

### 10. Hard Reset

If something goes wrong and the work should be discarded:

```bash
git reset --hard HEAD
git clean -fd
```

Use this carefully. It deletes uncommitted tracked changes and untracked files.

### 99. Revert

If a committed patch must be undone:

```bash
git log --oneline
git revert <commit-sha>
python -m pytest
git push
```

## Patch ZIP Creation

When creating a patch ZIP for download, package it flat.

Expected contents:

```text
apply_patch.sh
changed-files.txt
README.md
<patch-name>.patch
stages/
```

Example:

```bash
mkdir -p package/stages

cp apply_patch.sh package/
cp changed-files.txt package/
cp README.md package/
cp <patch-name>.patch package/
cp stages/*.sh package/stages/

cd package
zip -r ../<patch-name>.zip .
```

The ZIP must extract directly into `data/patch/`.

Final check:

```bash
rm -rf /tmp/patch-check
mkdir -p /tmp/patch-check
unzip <patch-name>.zip -d /tmp/patch-check
find /tmp/patch-check -maxdepth 2 -type f | sort
```

The output should show files directly under `/tmp/patch-check`, not inside an extra nested package directory.

```
```
