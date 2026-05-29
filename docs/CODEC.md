## Codec frontend roadmap outline

### 1. Purpose

The codec frontend should become the clean command surface for Agent:

```text
codec.py = clean user/operator frontend
agent-cli.py = batch/legacy compatibility frontend
codec-patch.py or /patch = patch/package operator
agent runtime = owns /prompt, /ground, tools, sessions, EvidencePacket
```

The frontend should hide clutter like:

```bash
python agent-cli.py run --text "/prompt Hello"
```

and expose:

```bash
python codec.py prompt "Hello"
python codec.py ground "What changed?"
python codec.py patch review patch.zip --branch patch/name
```

---

## 2. Command model

### LLM answer lanes

Only two answer lanes should be first-class:

```text
prompt = raw/direct LLM
ground = grounded/RAG/research LLM
```

CLI shape:

```bash
python codec.py prompt "write a short plan"
python codec.py ground "what does this repo say about patch workflow?"
```

Internal mapping:

```text
codec prompt -> Agent /prompt
codec ground -> Agent /ground
```

### Tool/control lanes

Everything else should be a tool/control command, not another LLM answer lane:

```text
patch
llm
codex
search
web
scrape
read
ls
tree
find
tool
switch/status
```

CLI shape:

```bash
python codec.py patch review foo.zip --branch patch/foo
python codec.py codex "inspect this repo"
python codec.py llm "summarize this report"
python codec.py read README.md
python codec.py search "patch workflow"
```

---

## 3. Milestone A — Frontend audit

Name:

```text
agent-codec-frontend-audit-v1
```

Goal:

```text
Inspect current codec.py inside agent.
Confirm command coverage.
Confirm whether it delegates to Agent runtime or duplicates behavior.
Confirm tests.
```

Commands:

```bash
cd ~/Downloads/agent
git switch main
git switch -c patch/agent-codec-frontend-audit-v1

git status --short --untracked-files=all
sed -n '1,220p' codec.py
python codec.py --help
python codec.py status
python codec.py prompt --help
python codec.py ground --help
python codec.py patch --help
python -m pytest -q tests -k "codec"
```

Deliverable:

```text
No code changes unless trivial.
Short report of current frontend gaps.
```

---

## 4. Milestone B — Prompt and ground delegation

Name:

```text
agent-codec-frontend-lanes-v1
```

Goal:

```text
Make codec prompt and codec ground delegate cleanly to Agent runtime.
```

Target behavior:

```bash
python codec.py prompt "Hello"
python codec.py ground "What is this repo?"
```

Must map to:

```text
/prompt Hello
/ground What is this repo?
```

Not:

```text
/question
/run --text
raw legacy alias soup
```

Expected files:

```text
codec.py
tests/test_codec_frontend.py
```

Tests:

```text
codec prompt builds /prompt command
codec ground builds /ground command
no live LLM call required
return code is propagated
stdout/stderr are preserved
```

Non-goals:

```text
No EvidencePacket implementation.
No provider changes.
No lane registry refactor.
```

---

## 5. Milestone C — Patch frontend

Name:

```text
agent-codec-patch-frontend-v1
```

Goal:

```text
Make codec.py patch commands wrap the canonical Agent patch engine.
```

Target commands:

```bash
python codec.py patch inspect patch.zip
python codec.py patch review patch.zip --yes --branch patch/foo
python codec.py patch publish patch.zip --yes --message "add foo"
python codec.py patch merge-cleanup patch.zip --yes --branch patch/foo
```

Mapping:

```text
codec patch inspect        -> patch engine --stage inspect
codec patch review         -> patch engine --workflow review
codec patch publish        -> patch engine --workflow publish
codec patch merge-cleanup  -> patch engine --workflow merge-cleanup
```

Expected files:

```text
codec.py
tests/test_codec_patch_frontend.py
```

Rules:

```text
No second patch engine.
No patch ZIP generation.
No publishing in tests.
```

---

## 6. Milestone D — Tool command namespace

Name:

```text
agent-codec-tool-frontend-v1
```

Goal:

```text
Expose common tool/control lanes from codec.py.
```

Target commands:

```bash
python codec.py llm status
python codec.py codex status
python codec.py search "repo docs"
python codec.py web fetch https://example.com
python codec.py scrape https://example.com
python codec.py read README.md
python codec.py ls docs
python codec.py tree docs
python codec.py find patch
```

Mapping:

```text
codec llm ...     -> /llm ...
codec codex ...   -> /codex ...
codec search ...  -> /search ...
codec web ...     -> /web ...
codec scrape ...  -> /scrape ...
codec read ...    -> /read ...
codec ls ...      -> /ls ...
codec tree ...    -> /tree ...
codec find ...    -> /find ...
```

Tests:

```text
Each command maps to expected slash command.
No live network/LLM required.
Unsupported command returns code 2.
```

---

## 7. Milestone E — Status and diagnostics

Name:

```text
agent-codec-status-v1
```

Goal:

```text
Make codec status show useful frontend/runtime state.
```

Target output:

```text
codec frontend version
active answer lanes:
  prompt
  ground
patch engine:
  available
tool lanes:
  llm, codex, search, web, scrape, read, ls, tree, find
agent runtime:
  importable / available
```

Commands:

```bash
python codec.py status
python codec.py status --json
```

Tests:

```text
text status contains prompt/ground/patch
json status is valid JSON
no live calls
```

---

## 8. Milestone F — Docs

Name:

```text
agent-codec-frontend-docs-v1
```

Goal:

```text
Document codec.py as the clean frontend.
```

Docs should state:

```text
codec prompt = raw LLM
codec ground = grounded LLM
codec patch = patch/package workflow
codec tool commands = wrappers over Agent slash commands
agent-cli.py remains batch/compatibility
```

Expected docs:

```text
CODEC.md
PATCH.md
HANDOFF.md
README.md if needed
```

---

## 9. Milestone G — Legacy surface cleanup

Name:

```text
agent-codec-legacy-surface-v1
```

Goal:

```text
Make legacy command expectations explicit.
```

Decision list:

```text
Keep:
  /prompt
  /ground
  /llm
  /codex
  /search
  /web
  /scrape
  /read
  /ls
  /tree
  /find
  /patch

Deprecate or remove:
  /write
  /generate
  /discuss
  /explain
  /describe
  /summarize
  /analyze
  /list
  /story
  /question
  /route
```

This milestone should update tests to match the active surface, but it should not be mixed with frontend implementation.

---

## 10. Safety rules

Every implementation patch:

```bash
git switch main
git status --short --untracked-files=all
git switch -c patch/<name>
```

Every review must show:

```bash
git status --short --untracked-files=all
git diff --stat
git diff
python -m py_compile agent-cli.py codec.py codec-patch.py
python -m pytest -q tests -k "codec or patch"
```

No generated ZIPs.

No push.

No merge.

No cleanup until review is explicitly approved.

---

## 11. Recommended next milestone

Start with:

```text
agent-codec-frontend-audit-v1
```

Then:

```text
agent-codec-frontend-lanes-v1
```

Do not start with broad legacy test cleanup or EvidencePacket work.

<!-- agent-codec-docs-tighten-v2-codec:start -->
## Active patch operator workflow

`codec-patch.py` is the active patch operator for staged patch packages in this repo.
Use this sequence:

```text
review -> inspect report -> publish -> merge-cleanup
```

`review` prepares the temporary patch branch, inspects the package, runs preflight,
applies the patch, runs tests, and prints a report. It must stop before commit,
push, merge, or cleanup.

A review is not clean if `git status --short --untracked-files=all` shows
untracked files that are not listed and displayed in the report. Added files
must be explicitly visible before publish.

`publish` commits and pushes only the temporary patch branch. `merge-cleanup`
fast-forwards `main`, pushes `main`, and deletes the patch branch.

Do not manually run `change.patch`, do not use heredocs for patching, and do not
edit directly on `main`.

`codec-patch.py` and package stage scripts must remove any temporary extraction
or work directories they create under `/tmp` on success, failure, and
interruption.
<!-- agent-codec-docs-tighten-v2-codec:end -->
