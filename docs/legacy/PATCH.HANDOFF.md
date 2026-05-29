We are working in the repo:

```bash
cd ~/Downloads/agent
```

Repository:

```text
https://github.com/DSP-INTELLIGENCE/agent
```

Important current context:

* Do **not** work in `~/Downloads/codec` anymore.
* The standalone `codec` repo is now only a checkpoint/source snapshot.
* Continue from the `agent` repo only.
* Use a temporary branch for every change.
* Do not generate or run patch ZIPs unless explicitly asked.
* Use normal Git diffs/manual patches first.
* Never publish/merge until review is clean and I explicitly approve.

Current agent repo audit showed these files already exist:

```text
agent-cli.py
codec.py
codec-patch.py
scripts/codec_patch_install.py
core/patch_install.py
```

The goal is to continue `/patch` integration in `agent` and make it cleanly available from `agent-cli.py`.

Target behavior:

```bash
python agent-cli.py install patch <patch.zip> --stage inspect
python agent-cli.py install patch <patch.zip> --stage preflight --yes
python agent-cli.py install patch <patch.zip> --stage apply --yes
python agent-cli.py install patch <patch.zip> --stage test --yes
python agent-cli.py install patch <patch.zip> --stage report --full-diff

python agent-cli.py install patch <patch.zip> --workflow review --yes --branch patch/<name>
python agent-cli.py install patch <patch.zip> --workflow publish --yes --message "..."
python agent-cli.py install patch <patch.zip> --workflow merge-cleanup --yes --branch patch/<name>
```

Also preserve:

```bash
python codec-patch.py --help
python codec.py --help
python agent-cli.py --help
```

Architecture direction:

```text
agent owns runtime intelligence:
  /prompt
  /ground
  EvidencePacket
  GroundingService/providers
  /sources
  /grounding
  sessions/personas/tools

codec pieces inside agent provide:
  clean CLI/frontend shape
  patch/package operator
  route/lane vocabulary where useful
```

Do not move Agent RAG or EvidencePacket runtime into codec. `/ground` belongs to Agent runtime.

Known issue from audit:

The full pytest suite is not clean right now. Failures appear to come from stale tests expecting removed/legacy lanes such as:

```text
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

The current active lane contract should be treated as:

```text
LLM answer lanes:
  /prompt = raw/direct LLM
  /ground = grounded/RAG/research LLM

Tool/control lanes:
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
  /tool
  /switch where still supported
```

First task:

1. Create a temp branch:

```bash
git switch main
git status --short --untracked-files=all
git switch -c patch/agent-cli-patch-integration-audit
```

2. Inspect current state:

```bash
git status --short --untracked-files=all
git log --oneline --decorate -8
python agent-cli.py --help
python agent-cli.py install patch --help || true
python codec-patch.py --help
python codec.py --help
python agent-cli.py run --text "/patch status" || true
python -m pytest -q tests -k "patch or codec" || true
```

3. Determine whether `agent-cli.py` already exposes `install patch`.

   * If yes, verify it delegates to the existing patch engine.
   * If no, add only the minimal argparse and dispatch wiring needed.
   * Prefer the already-present patch engine:

     * `core/patch_install.py` if that is the canonical current agent location.
     * `scripts/codec_patch_install.py` only if that is the current working implementation.
   * Do not create a second patch engine.

4. Add or update focused tests only for:

   * `agent-cli.py install patch --help`
   * workflow options: `review`, `publish`, `merge-cleanup`
   * stage options: `branch`, `inspect`, `preflight`, `apply`, `test`, `report`, `commit`, `push`, `merge`, `cleanup`
   * import/delegation path works
   * no live LLM/network calls

5. Do **not** attempt to fix the whole stale lane test suite in the same patch unless explicitly requested.
   If needed, report those failures separately as `agent-test-reconcile-active-lanes-v1`.

Patch discipline:

* Always show:

```bash
git status --short --untracked-files=all
git diff --stat
git diff
python -m py_compile agent-cli.py codec.py codec-patch.py core/patch_install.py scripts/codec_patch_install.py
python -m pytest -q tests -k "patch or codec"
```

* Do not push.
* Do not merge.
* Stop after review and report exactly what changed.

Expected first milestone name:

```text
agent-cli-patch-integration-v1
```

Expected scope:

```text
agent-cli.py
tests focused on patch CLI integration
possibly one compatibility import shim, only if needed
```

Non-goals:

```text
No codec repo work.
No patch ZIP generation.
No bulk core moves.
No EvidencePacket/RAG changes.
No legacy lane restoration unless explicitly requested.
No broad pytest cleanup in this same patch.
```
