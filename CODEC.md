# CODEC

## Overview

`codec` is the frontend and staged patch workflow system for the `agent` repository.

The codec layer separates:

1. frontend commands
2. answer lanes
3. repo inspection
4. patch workflows
5. staged patch execution
6. repository lifecycle operations

The codec layer is intended to provide a clean operational surface over the lower-level runtime and routing systems.

---

# Components

The codec system currently consists of:

```text
codec.py
codec-patch.py
```

## codec.py

`codec.py` is the frontend command surface.

Responsibilities:

1. expose user-facing commands
2. expose answer lanes
3. expose patch workflow entrypoints
4. expose repo diagnostics
5. provide stable frontend contracts
6. route patch operations to `codec-patch.py`

`codec.py` should be treated as the primary frontend tool.

## codec-patch.py

`codec-patch.py` is the staged patch operator.

Responsibilities:

1. inspect patch packages
2. prepare branches
3. apply patches
4. verify patch state
5. run tests
6. generate reports
7. commit changes
8. push branches
9. merge branches
10. cleanup temporary patch state

Patch execution is intentionally stage-based.

Stages do not automatically advance unless explicitly requested.

---

# Current Frontend Contract

The currently tested frontend contract is:

```text
codec.py
  -> frontend command surface

codec-patch.py
  -> staged patch execution engine
```

`codec.py patch` delegates patch execution behavior to `codec-patch.py`.

---

# codec.py

## Help Output

Current frontend surface:

```text
usage: codec.py [-h] {status,prompt,ground,patch} ...

Clean Codec frontend.
```

Available commands:

```text
status
prompt
ground
patch
```

---

# codec.py status

`status` shows codec and repository diagnostics.

Example:

```bash
python codec.py status
```

Example output:

```text
codec frontend: available
entrypoint: codec.py
answer lanes:
  prompt -> /prompt
  ground -> /ground
patch operator: codec-patch.py
patch workflow: review -> publish -> merge-cleanup
repo:
  branch: main
  head: d35bcb1
  clean: false
```

## Status Responsibilities

Status output should report:

1. codec frontend availability
2. frontend entrypoint
3. configured answer lanes
4. patch operator
5. patch workflow
6. current git branch
7. current HEAD
8. whether the repo is clean
9. optional diagnostics and warnings

---

# codec.py prompt

The `prompt` command maps to the raw or direct LLM lane.

Equivalent lane:

```text
/prompt
```

Purpose:

1. direct prompting
2. minimal routing
3. direct LLM interaction
4. lightweight execution

Example:

```bash
python codec.py prompt "hello"
```

Equivalent:

```text
/prompt hello
```

---

# codec.py ground

The `ground` command maps to the grounded or RAG answer lane.

Equivalent lane:

```text
/ground
```

Purpose:

1. grounded responses
2. evidence lookup
3. retrieval workflows
4. synthesis workflows
5. document-assisted reasoning

Example:

```bash
python codec.py ground "summarize this repository"
```

Equivalent:

```text
/ground summarize this repository
```

---

# codec.py patch

The `patch` command exposes patch package workflows.

Patch execution is delegated to:

```text
codec-patch.py
```

Purpose:

1. patch review
2. patch inspection
3. patch apply
4. staged patch execution
5. patch reporting
6. repo lifecycle operations

---

# codec-patch.py

## Overview

`codec-patch.py` is the staged patch workflow operator.

It manages repository mutation safely through explicit stages.

Stages are intentionally separated to prevent accidental mutation or merge behavior.

---

# Help Output

Current patch operator surface:

```text
usage: codec-patch.py [-h]
                      [--stage {branch,inspect,preflight,apply,test,report,commit,push,merge,cleanup}]
                      [--workflow {review,publish,merge-cleanup}]
                      [--repo REPO] [--yes] [--message MESSAGE]
                      [--branch BRANCH] [--allow-dirty] [--full-diff] [--live]
                      package
```

---

# Package Argument

The required `package` argument may be:

1. a patch ZIP file
2. an unpacked patch package directory

Examples:

```bash
python codec-patch.py data/zip/my-patch.zip --stage inspect
```

```bash
python codec-patch.py data/patch --stage apply --yes
```

---

# Patch Stages

Supported stages:

```text
branch
inspect
preflight
apply
test
report
commit
push
merge
cleanup
```

Stages do not automatically advance.

Mutating stages require explicit approval.

---

# Stage Definitions

## branch

Prepare or switch to the patch branch.

Responsibilities:

1. create branch
2. switch branch
3. normalize repo state
4. verify clean branch state

---

## inspect

Inspect the patch package and repository state.

Responsibilities:

1. inspect package contents
2. inspect patch layout
3. inspect repo cleanliness
4. inspect branch state
5. inspect file conflicts
6. inspect docs and roadmap changes

---

## preflight

Run safety checks before apply.

Responsibilities:

1. verify patch compatibility
2. verify repo status
3. verify required files
4. verify patch layout
5. verify clean apply conditions

---

## apply

Apply the patch.

Mutating stage.

Requires:

```bash
--yes
```

Responsibilities:

1. apply patch
2. copy docs
3. update roadmap files
4. update milestone files
5. update repo state

---

## test

Run smoke tests and full tests.

Responsibilities:

1. smoke tests
2. pytest
3. verification commands
4. runtime checks
5. frontend checks

Preferred:

```bash
python -m pytest
```

---

## report

Generate patch and repo reports.

Responsibilities:

1. git diff summary
2. changed file summary
3. patch verification summary
4. repo status
5. optional full diff output

Use:

```bash
--full-diff
```

to print the full diff.

---

## commit

Commit the patch after approval.

Mutating stage.

Requires:

```bash
--yes
```

Recommended:

```bash
--message "<commit message>"
```

Responsibilities:

1. stage files
2. commit files
3. validate commit state

---

## push

Push the patch branch.

Responsibilities:

1. push branch
2. verify remote branch
3. prepare PR workflow

---

## merge

Merge the patch branch.

Responsibilities:

1. review merge readiness
2. merge branch
3. verify merge state

---

## cleanup

Cleanup temporary patch state.

Responsibilities:

1. remove extracted patch files
2. cleanup temp directories
3. cleanup patch artifacts
4. cleanup repo state

---

# Workflows

Supported workflows:

```text
review
publish
merge-cleanup
```

---

# review Workflow

The `review` workflow runs patch review stages and stops before commit, push, merge, and cleanup.

Purpose:

1. inspect patch
2. preflight patch
3. apply patch
4. test patch
5. generate report
6. wait for approval

Example:

```bash
python codec-patch.py data/zip/my-patch.zip --workflow review
```

---

# publish Workflow

The `publish` workflow runs publication stages after review approval.

Purpose:

1. commit patch
2. push branch
3. prepare PR state

---

# merge-cleanup Workflow

The `merge-cleanup` workflow runs merge and cleanup stages.

Purpose:

1. merge branch
2. cleanup repo
3. cleanup temporary patch state

---

# Safety Rules

Patch stages do not auto-advance.

Mutating operations require explicit approval.

Use:

```bash
--yes
```

for mutating stages.

Use:

```bash
--allow-dirty
```

only when intentionally applying to a dirty repository.

Do not commit until:

1. inspect succeeds
2. preflight succeeds
3. apply succeeds
4. verification succeeds
5. tests succeed
6. patch approval is complete

---

# Repository Layout

Codec patch workflows assume:

```text
docs/
data/patch/
data/zip/
roadmap/
roadmap/milestones/
```

---

# Patch Package Layout

Patch ZIPs should extract flat into:

```text
data/patch/
```

Expected structure:

```text
apply_patch.sh
changed-files.txt
README.md
<patch-name>.patch
stages/
```

Incorrect:

```text
data/patch/<package>/<package>/
```

Correct:

```text
data/patch/apply_patch.sh
data/patch/<patch>.patch
data/patch/stages/
```

---

# Recommended Patch Flow

## Install

```bash
mkdir -p data/patch data/zip

cp ~/Downloads/*.zip data/zip/ 2>/dev/null || true

rm -rf data/patch/*

unzip data/zip/<patch>.zip -d data/patch
```

---

## Inspect

```bash
python codec-patch.py data/patch --stage inspect
```

---

## Preflight

```bash
python codec-patch.py data/patch --stage preflight
```

---

## Apply

```bash
python codec-patch.py data/patch --stage apply --yes
```

---

## Test

```bash
python codec-patch.py data/patch --stage test

python -m pytest
```

---

## Report

```bash
python codec-patch.py data/patch --stage report --full-diff
```

---

## Commit

```bash
python codec-patch.py data/patch \
  --stage commit \
  --yes \
  --message "patch message"
```

---

## Push

```bash
python codec-patch.py data/patch --stage push
```

---

## Cleanup

```bash
python codec-patch.py data/patch --stage cleanup --yes
```

---

# Relationship To Agent

The codec layer is the operational frontend.

The agent runtime is separate.

Codec should not define:

1. semantic controllers
2. embedding systems
3. semantic-router internals
4. endpoint implementations
5. adapter implementations

Codec is responsible for:

1. frontend routing
2. workflow control
3. patch lifecycle
4. repo operations
5. frontend lane access

---

# Legacy Components

## agent.py

`agent.py` is a legacy terminal entrypoint.

It should be treated as compatibility behavior unless promoted again.

## agent-cli.py

`agent-cli.py` is a legacy CLI entrypoint.

It should be treated as compatibility behavior unless promoted again.

---

# Design Separation

The repo should avoid mixing:

```text
frontend != runtime
runtime != semantic controller
lane != adapter
adapter != endpoint
patch operator != LLM endpoint
legacy CLI != canonical frontend
```

Documentation should clearly state which layer each file belongs to.
